from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Dict, Any, List
import random
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from app.models.enums import ApplicationStatus, ApplicationStage, AccountStatus, CardStatus, CardType
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.admin.models.credit_product import CreditProductInformation
from app.models.customer import CustomerProfile
from app.services.engines.bureau_engine import simulate_bureau_score
from app.services.engines.fraud_engine import detect_fraud_anomalies
from app.services.engines.risk_engine import calculate_risk_assessment
from app.models.enums import EmploymentType, Country
from app.models.credit import BureauReport, RiskAssessment, FraudFlag, CreditDecision
from app.models.audit import AuditLog

class CardIssuanceService:
    @staticmethod
    def run_engines(db: Session, app: CreditCardApplication) -> None:
        """
        Run all assessment engines (Bureau, Fraud, Risk) and persist their reports.
        """
        # Avoid redundant runs if already assessed
        if db.query(BureauReport).filter(BureauReport.application_id == app.id).first():
            return

        cif = db.query(CustomerProfile).filter(CustomerProfile.id == app.cif_id).first()
        
        # 1. Bureau Engine
        employment_type_str = app.employment_status or "UNEMPLOYED"
        employment_type = EmploymentType(employment_type_str) if employment_type_str in [e.value for e in EmploymentType] else EmploymentType.UNEMPLOYED

        country_obj = Country.INDIA
        if cif and cif.addresses and hasattr(cif.addresses[0], 'country'):
            cif_country = cif.addresses[0].country
            if isinstance(cif_country, Country):
                country_obj = cif_country
            elif isinstance(cif_country, str):
                try:
                    country_obj = Country(cif_country)
                except ValueError:
                    country_obj = Country.INDIA

        is_kyc = True if cif and getattr(cif, 'kyc_state', None) and getattr(cif.kyc_state, 'value', None) == "COMPLETED" else False

        bureau_data = simulate_bureau_score(
            age=30,
            annual_income=float(app.declared_income or 0.0),
            employment_type=employment_type,
            country=country_obj,
            is_kyc_completed=is_kyc
        )
        
        bureau_report = BureauReport(
            application_id=app.id,
            bureau_score=bureau_data["bureau_score"],
            report_reference_id=bureau_data["report_reference_id"],
            bureau_snapshot=bureau_data["snapshot"]
        )
        db.add(bureau_report)
        
        # 2. Fraud Engine
        fraud_rules = detect_fraud_anomalies(
            declared_country=country_obj.value if isinstance(country_obj, Country) else str(country_obj),
            ip_country="India",
            declared_income=float(app.declared_income or 0.0),
            verified_income=float(app.declared_income or 0.0),
            application_velocity_count=db.query(CreditCardApplication).filter(CreditCardApplication.user_id == app.user_id).count()
        )
        
        for f_rule in fraud_rules:
            flag = FraudFlag(
                application_id=app.id,
                flag_code=f_rule.code,
                flag_description=f_rule.description,
                severity=f_rule.severity
            )
            db.add(flag)
            
        # 3. Risk Engine
        risk_band, confidence_score, explanation = calculate_risk_assessment(
            bureau_score=bureau_data["bureau_score"],
            fraud_flags=fraud_rules,
            declared_income=float(app.declared_income or 0.0)
        )
        
        risk_assessment = RiskAssessment(
            application_id=app.id,
            risk_band=risk_band,
            confidence_score=confidence_score,
            assessment_explanation=explanation
        )
        db.add(risk_assessment)
        db.commit()
        db.refresh(app)

    @staticmethod
    def review_application(db: Session, application_id: UUID, user_id: UUID, override_status: ApplicationStatus = None, rejection_reason: Optional[str] = None) -> dict:
        app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
            
        if app.application_status in [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]:
            # IDEMPOTENCY: Only return existing if the command matches the current state
            if app.application_status == override_status:
                if app.application_status == ApplicationStatus.APPROVED:
                    account = db.query(CreditAccount).filter(CreditAccount.application_id == app.id).first()
                    if account:
                        cif_profile = db.query(CustomerProfile).filter(CustomerProfile.id == app.cif_id).first()
                        return {
                            "credit_account_id": account.id,
                            "application_status": "APPROVED",
                            "account_details": {
                                "application_id": app.id,
                                "cif_id": cif_profile.cif_number if cif_profile else str(app.cif_id),
                                "credit_product_id": account.credit_product_id,
                                "card_product_id": account.card_product_id,
                                "account_currency": account.account_currency,
                                "sanctioned_limit": account.sanctioned_limit,
                                "available_limit": account.available_limit,
                                "outstanding_amount": account.outstanding_amount,
                                "account_status": account.account_status,
                                "opened_at": account.opened_at,
                                "created_by": account.created_by,
                                "approved_by": account.approved_by
                            },
                            "message": "Application has already been verified as APPROVED"
                        }
                return {
                    "application_status": "REJECTED",
                    "rejection_reason": app.rejection_reason,
                    "message": "Application has already been verified as REJECTED"
                }
            # If override_status is different, we proceed to re-process (OVERRIDE logic)
            
        # Ensure engines have been run
        CardIssuanceService.run_engines(db, app)
        
        # Fetch data for decision logic
        bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
        risk_assessment = db.query(RiskAssessment).filter(RiskAssessment.application_id == app.id).first()
        fraud_rules = db.query(FraudFlag).filter(FraudFlag.application_id == app.id).all()
        
        # Guardrails based on credit product rules
        min_score = app.credit_product.eligibility_rules.min_credit_score if app.credit_product else 700
        min_income = app.credit_product.eligibility_rules.min_income_required if app.credit_product else 20000
        
        prev_status = app.application_status.value
        
        if override_status:
            if override_status == ApplicationStatus.REJECTED and not rejection_reason:
                raise HTTPException(status_code=400, detail="Rejection reason is mandatory for rejection command")
            app.application_status = override_status
            if rejection_reason:
                app.rejection_reason = rejection_reason
        else:
            if bureau_report.bureau_score < min_score or risk_assessment.risk_band.value == "VERY_HIGH" or any(f.severity == "CRITICAL" for f in fraud_rules):
                app.application_status = ApplicationStatus.REJECTED
                app.rejection_reason_code = "RISK_POLICY_DECLINE"
                app.rejection_reason = "Risk policy decline based on bureau score or fraud flags"
            elif float(app.declared_income or 0) < min_income:
                app.application_status = ApplicationStatus.REJECTED
                app.rejection_reason_code = "INCOME_TOO_LOW"
                app.rejection_reason = "Declared income is below the minimum required for this product"
            else:
                app.application_status = ApplicationStatus.APPROVED
                
        if app.application_status == ApplicationStatus.REJECTED:
            cooling_days = app.credit_product.governance.cooling_period_days if app.credit_product else 90
            app.cooling_period_until = datetime.now(timezone.utc) + timedelta(days=cooling_days)

        app.reviewed_by = user_id
        app.reviewed_at = datetime.now(timezone.utc)
        
        decision_record = CreditDecision(
            application_id=app.id,
            admin_id=user_id,
            decision=app.application_status.value,
            override_flag=bool(override_status),
            notes=rejection_reason or risk_assessment.assessment_explanation
        )
        db.add(decision_record)
        
        # 4. Audit Log
        audit_log = AuditLog(
            action_type="APPLICATION_DECISION",
            actor_type="ADMIN",
            actor_id=user_id,
            resource_id=app.id,
            previous_state={"status": prev_status},
            new_state={"status": app.application_status.value, "risk_band": risk_assessment.risk_band.value, "bureau_score": bureau_report.bureau_score},
            metadata_fields={"override": bool(override_status)}
        )
        db.add(audit_log)

        db.commit()
        db.refresh(app)
        
        # If successfully approved, trigger account creation workflow automatically
        if app.application_status == ApplicationStatus.APPROVED:
            account = CardIssuanceService.create_credit_account_for_application(db, app, user_id)
            # PROACTIVE: Auto-issue the primary card immediately
            CardIssuanceService.issue_card(db, account.id, CardType.PRIMARY)
            
            # Map account to response dict with extra fields
            cif_profile = db.query(CustomerProfile).filter(CustomerProfile.id == app.cif_id).first()
            return {
                "credit_account_id": account.id,
                "application_status": "APPROVED",
                "account_details": {
                    "application_id": app.id,
                    "cif_id": cif_profile.cif_number if cif_profile else str(app.cif_id),
                    "credit_product_id": account.credit_product_id,
                    "card_product_id": account.card_product_id,
                    "account_currency": account.account_currency,
                    "sanctioned_limit": account.sanctioned_limit,
                    "available_limit": account.available_limit,
                    "outstanding_amount": account.outstanding_amount,
                    "account_status": "ACTIVE",
                    "opened_at": account.opened_at,
                    "created_by": account.created_by,
                    "approved_by": account.approved_by
                },
                "message": "Application APPROVED successfully"
            }
        
        return {
            "application_status": "REJECTED",
            "rejection_reason": app.rejection_reason,
            "message": "Application REJECTED successfully"
        }

    @staticmethod
    def create_credit_account_for_application(db: Session, app: CreditCardApplication, admin_id: UUID) -> CreditAccount:
        if app.application_status != ApplicationStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Cannot create account: Application not approved")
            
        existing_acc = db.query(CreditAccount).filter(
            CreditAccount.cif_id == app.cif_id,
            CreditAccount.credit_product_id == app.credit_product_id
        ).first()
        if existing_acc:
            return existing_acc
            
        # Derive sanctioned limit based on product config -> could limit based on limits table
        max_limit = app.credit_product.limits.max_credit_limit if app.credit_product else 50000
        min_limit = app.credit_product.limits.min_credit_limit if app.credit_product else 10000
        
        # Mocking an engine that grants limit based on income/cibil.
        granted_limit = min(max_limit, max(min_limit, (app.declared_income or 0) * 1.5))
        
        account = CreditAccount(
            cif_id=app.cif_id,
            credit_product_id=app.credit_product_id,
            card_product_id=app.card_product_id,
            application_id=app.id,
            account_currency=app.card_product.default_card_currency if app.card_product else "INR",
            sanctioned_limit=granted_limit,
            available_limit=granted_limit,
            outstanding_amount=0.0,
            created_by=admin_id,
            approved_by=admin_id
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def generate_random_pan(bin_range: str) -> str:
        # A mock 16-digit generator using the first 6 digits of bin
        prefix = str(bin_range).replace("X", "0")[:6]
        suffix = "".join([str(random.randint(0, 9)) for _ in range(10)])
        return prefix + suffix

    @staticmethod
    def issue_card(db: Session, credit_account_id: UUID, card_type: CardType = CardType.PRIMARY) -> Card:
        account = db.query(CreditAccount).filter(CreditAccount.id == credit_account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Credit account not found")
        if account.account_status != AccountStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Cannot issue a card to an inactive account")
            
        # IDEMPOTENCY: Check if card already exists
        existing_card = db.query(Card).filter(
            Card.credit_account_id == credit_account_id,
            Card.card_type == card_type
        ).first()
        if existing_card:
            return existing_card
            
        # Typically fetched from CardProduct mapping
        # Here we mock getting back to the card_product via app record or manual pass
        # For simplicity in MVP, we just generate mock pan
        app = db.query(CreditCardApplication).filter(CreditCardApplication.cif_id == account.cif_id, CreditCardApplication.credit_product_id == account.credit_product_id).first()
        pan = CardIssuanceService.generate_random_pan(app.card_product.card_bin_range if app and app.card_product else "400000")
        
        # PAN encryption logic placeholder
        encrypted_pan = f"encrypt({pan})"
        masked_pan = f"{str(pan)[:6]}XXXXXX{str(pan)[-4:]}"
        
        # Issue 5 year validity placeholder
        expiry_date = (datetime.now() + timedelta(days=5*365)).strftime("%m/%y")
        expiry_date_masked = f"XX/{expiry_date.split('/')[1]}"
        
        cvv = str(random.randint(100, 999))
        cvv_encrypted = f"encrypt({cvv})"
        cvv_masked = "***"
        
        card = Card(
            credit_account_id=account.id,
            card_type=card_type,
            pan_encrypted=encrypted_pan,
            pan_masked=masked_pan,
            expiry_date=expiry_date,
            expiry_date_masked=expiry_date_masked,
            cvv_encrypted=cvv_encrypted,
            cvv_masked=cvv_masked
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        return card
