from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Dict, Any, List
import random
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from app.models.enums import (
    ApplicationStatus, ApplicationStage, AccountStatus, CardStatus, CardType,
    AMLRiskCategory, InternalRiskRating, AutoPayType, EmploymentType, Country
)
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card, CardActivationOTP
from app.admin.models.credit_product import CreditProductInformation
from app.admin.models.card_product import CardProductCore
from app.models.customer import CustomerProfile
from app.services.engines.bureau_engine import simulate_bureau_score
from app.services.engines.fraud_engine import detect_fraud_anomalies
from app.services.engines.risk_engine import calculate_risk_assessment
from app.models.credit import BureauReport, RiskAssessment, FraudFlag, CreditDecision
from app.models.audit import AuditLog
from app.core.security import hash_value
from app.core.otp import generate_otp, hash_otp, verify_otp, get_expiry_time
from app.admin.schemas.card_issuance import (
    AdminKYCReviewRequest, CreditAccountManualConfig, IssueCardRequest, CardActivationRequest, SetPinRequest
)

class CardIssuanceService:
    @staticmethod
    def run_engines_pre_assessment(db: Session, cif: CustomerProfile, data: Any, credit_product: CreditProductInformation) -> Dict[str, Any]:
        """
        Run assessments BEFORE persisting the application to avoid 'rejected' junk in database.
        """
        # 1. Age calculation
        from datetime import date
        today = date.today()
        age = today.year - cif.date_of_birth.year - (
            (today.month, today.day) < (cif.date_of_birth.month, cif.date_of_birth.day)
        )

        employment_type_str = (data.employment_status or "UNEMPLOYED").upper()
        employment_type = EmploymentType(employment_type_str) if employment_type_str in [e.value for e in EmploymentType] else EmploymentType.UNEMPLOYED

        # 2. Bureau Engine
        bureau_data = simulate_bureau_score(
            age=age,
            annual_income=float(data.declared_income or 0.0),
            employment_type=employment_type,
            country=Country.INDIA, # Default for bureau simulation
            is_kyc_completed=True
        )

        # 3. Fraud Engine
        fraud_rules = detect_fraud_anomalies(
            declared_country="India",
            ip_country="India",
            declared_income=float(data.declared_income or 0.0),
            verified_income=float(cif.financial_information.net_annual_income) if cif.financial_information else 0.0,
            application_velocity_count=db.query(CreditCardApplication).filter(CreditCardApplication.user_id == cif.user_id).count()
        )

        # 4. Risk Engine
        risk_band, confidence_score, explanation = calculate_risk_assessment(
            bureau_score=bureau_data["bureau_score"],
            fraud_flags=fraud_rules,
            declared_income=float(data.declared_income or 0.0)
        )

        # 5. Eligibility Decision (Dynamic)
        eligibility = credit_product.eligibility_rules
        if bureau_data["bureau_score"] < eligibility.min_credit_score:
            return {"status": "REJECTED", "reason": f"Bureau score {bureau_data['bureau_score']} is below minimum {eligibility.min_credit_score}"}
        
        if float(data.declared_income) < float(eligibility.min_income_required):
            return {"status": "REJECTED", "reason": f"Declared income {data.declared_income} is below minimum {eligibility.min_income_required}"}

        if any(f.severity == "CRITICAL" for f in fraud_rules):
            return {"status": "REJECTED", "reason": "Application flagged for high fraud risk"}

        return {
            "status": "APPROVED",
            "bureau_data": bureau_data,
            "fraud_rules": fraud_rules,
            "risk_assessment": {
                "band": risk_band,
                "confidence": confidence_score,
                "explanation": explanation
            }
        }

    @staticmethod
    def review_kyc(db: Session, application_id: UUID, admin_id: UUID) -> dict:
        """
        Transition application from SUBMITTED to KYC_REVIEW.
        """
        app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        
        if app.application_status != ApplicationStatus.SUBMITTED:
            raise HTTPException(status_code=400, detail=f"Cannot move to KYC_REVIEW from {app.application_status}")
        
        app.application_status = ApplicationStatus.KYC_REVIEW
        app.reviewed_by = admin_id
        
        audit_log = AuditLog(
            action_type="KYC_REVIEW_START",
            actor_type="ADMIN",
            actor_id=admin_id,
            resource_id=app.id,
            previous_state={"status": ApplicationStatus.SUBMITTED.value},
            new_state={"status": ApplicationStatus.KYC_REVIEW.value}
        )
        db.add(audit_log)
        db.commit()
        db.refresh(app)
        return {"message": "Application moved to KYC_REVIEW", "application_id": app.id, "status": app.application_status}

    @staticmethod
    def evaluate_application(db: Session, application_id: UUID, user_id: str) -> dict:
        """
        Automated credit decision flow mimicking real banking engines.
        Procures bureau score, runs fraud checks, risk rules and derives decision.
        If APPROVED, provisions credit account + virtual card.
        """
        app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        # Reject if already processed
        if app.application_status in [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]:
            return CardIssuanceService.review_application(db, application_id, user_id, app.application_status)

        # 1. Ensure engines have been run
        bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
        if not bureau_report:
            cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == app.user_id).first()
            assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, app, app.credit_product)
            
            new_bureau = BureauReport(
                application_id=app.id,
                bureau_score=assessment["bureau_data"]["bureau_score"],
                report_reference_id=assessment["bureau_data"]["report_reference_id"],
                bureau_snapshot=assessment["bureau_data"]["snapshot"]
            )
            db.add(new_bureau)
            for rule in assessment["fraud_rules"]:
                f_flag = FraudFlag(application_id=app.id, flag_code=rule.code, flag_description=rule.description, severity=rule.severity)
                db.add(f_flag)
                
            new_risk = RiskAssessment(
                application_id=app.id,
                risk_band=assessment["risk_assessment"]["band"],
                confidence_score=assessment["risk_assessment"]["confidence"],
                assessment_explanation=assessment["risk_assessment"]["explanation"]
            )
            db.add(new_risk)
            db.commit()

        # Re-fetch populated assessments
        bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
        risk_assessment = db.query(RiskAssessment).filter(RiskAssessment.application_id == app.id).first()
        fraud_rules = db.query(FraudFlag).filter(FraudFlag.application_id == app.id).all()

        # Guardrails based on credit product rules
        min_score = app.credit_product.eligibility_rules.min_credit_score if app.credit_product else 700
        min_income = app.credit_product.eligibility_rules.min_income_required if app.credit_product else 20000

        # Run automated evaluation
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


        # Track decision
        if app.application_status == ApplicationStatus.REJECTED:
            cooling_days = app.credit_product.governance.cooling_period_days if app.credit_product else 90
            app.cooling_period_until = datetime.now(timezone.utc) + timedelta(days=cooling_days)

        app.reviewed_by = user_id
        app.reviewed_at = datetime.now(timezone.utc)

        decision_record = CreditDecision(
            application_id=app.id,
            admin_id=user_id,
            decision=app.application_status.value,
            override_flag=False,
            notes=risk_assessment.assessment_explanation
        )
        db.add(decision_record)

        # Audit Logger implementation
        audit_log = AuditLog(
            action_type="APPLICATION_EVALUATE",
            actor_type="SYSTEM",
            actor_id=user_id,
            resource_id=app.id,
            previous_state={"status": ApplicationStatus.SUBMITTED.value},
            new_state={"status": app.application_status.value, "risk_band": risk_assessment.risk_band.value, "bureau_score": bureau_report.bureau_score},
            metadata_fields={"automated": True}
        )
        db.add(audit_log)
        db.commit()
        db.refresh(app)

        if app.application_status == ApplicationStatus.APPROVED:
            return {
                "application_id": app.id,
                "application_status": "APPROVED",
                "message": "Application automatically evaluated and APPROVED. Ready for manual configuration."
            }


        return {
            "application_status": "REJECTED",
            "rejection_reason": app.rejection_reason,
            "message": "Application automatically evaluated and REJECTED."
        }

    @staticmethod
    def review_application(db: Session, application_id: UUID, user_id: str, override_status: ApplicationStatus = None, rejection_reason: Optional[str] = None) -> dict:
        app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
            
        if app.application_status in [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]:
            # IDEMPOTENCY: Only return existing if the command matches the current state
            if app.application_status == override_status:
                if app.application_status == ApplicationStatus.APPROVED:
                    account = db.query(CreditAccount).filter(CreditAccount.application_id == app.id).first()
                    if account:
                        cif_profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == app.user_id).first()
                        return {
                            "credit_account_id": account.id,
                            "application_status": "APPROVED",
                            "account_details": {
                                "application_id": app.id,
                                "user_id": str(app.user_id),
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
        bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
        if not bureau_report:
            cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == app.user_id).first()
            assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, app, app.credit_product)
            
            new_bureau = BureauReport(
                application_id=app.id,
                bureau_score=assessment["bureau_data"]["bureau_score"],
                report_reference_id=assessment["bureau_data"]["report_reference_id"],
                bureau_snapshot=assessment["bureau_data"]["snapshot"]
            )
            db.add(new_bureau)
            for rule in assessment["fraud_rules"]:
                f_flag = FraudFlag(application_id=app.id, flag_code=rule.code, flag_description=rule.description, severity=rule.severity)
                db.add(f_flag)
                
            new_risk = RiskAssessment(
                application_id=app.id,
                risk_band=assessment["risk_assessment"]["band"],
                confidence_score=assessment["risk_assessment"]["confidence"],
                assessment_explanation=assessment["risk_assessment"]["explanation"]
            )
            db.add(new_risk)
            db.commit()
        
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
            cif_profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == app.user_id).first()
            return {
                "credit_account_id": account.id,
                "application_status": "APPROVED",
                "account_details": {
                    "application_id": app.id,
                    "user_id": str(app.user_id),
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
    def configure_and_create_account(db: Session, application_id: UUID, config: CreditAccountManualConfig, admin_id: UUID) -> CreditAccount:
        app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        
        if app.application_status != ApplicationStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Application must be in APPROVED state for configuration")
            
        existing_acc = db.query(CreditAccount).filter(CreditAccount.application_id == app.id).first()
        if existing_acc:
            return existing_acc
            
        account = CreditAccount(
            user_id=app.user_id,
            credit_product_id=app.credit_product_id,
            card_product_id=app.card_product_id,
            application_id=app.id,
            account_currency=app.card_product.default_card_currency if app.card_product else "INR",
            
            credit_limit=config.credit_limit,
            available_limit=config.credit_limit,
            cash_advance_limit=config.cash_advance_limit,
            outstanding_amount=0.0,
            
            billing_cycle_id=config.billing_cycle_id,
            
            overlimit_allowed=config.overlimit_allowed,
            overlimit_percentage=config.overlimit_percentage,
            
            autopay_enabled=config.autopay_enabled,
            autopay_type=config.autopay_type,
            
            created_by=admin_id,
            approved_by=admin_id
        )
        db.add(account)
        
        # Update application status
        app.application_status = ApplicationStatus.ACCOUNT_CREATED
        
        audit_log = AuditLog(
            action_type="ACCOUNT_CONFIGURED",
            actor_type="ADMIN",
            actor_id=admin_id,
            resource_id=account.id,
            previous_state={"status": ApplicationStatus.PENDING.value},
            new_state={"status": ApplicationStatus.ACCOUNT_CREATED.value, "account_id": str(account.id)}
        )
        db.add(audit_log)
        
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
    def issue_card_manual(db: Session, credit_account_id: UUID, request: IssueCardRequest, admin_id: UUID) -> Card:
        account = db.query(CreditAccount).filter(CreditAccount.id == credit_account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Credit account not found")
        
        card_product = db.query(CardProductCore).filter(CardProductCore.id == request.card_product_id).first()
        if not card_product:
            raise HTTPException(status_code=404, detail="Card product not found")
        
        # Validate that the requested card product is linked to the same credit product as the account
        if card_product.credit_product_id != account.credit_product_id:
            raise HTTPException(status_code=400, detail="Card product does not match the credit account's product")
            
        # IDEMPOTENCY: Check if card already exists for this account and type
        existing_card = db.query(Card).filter(
            Card.credit_account_id == account.id,
            Card.card_type == request.card_type
        ).first()
        if existing_card:
            return existing_card
            
        pan = CardIssuanceService.generate_random_pan(card_product.card_bin_range)
        
        encrypted_pan = f"encrypt({pan})" # Placeholder for real encryption
        masked_pan = f"{str(pan)[:6]}XXXXXX{str(pan)[-4:]}"
        
        expiry_date = (datetime.now() + timedelta(days=5*365)).strftime("%m/%y")
        expiry_date_masked = f"XX/{expiry_date.split('/')[1]}"
        
        cvv = str(random.randint(100, 999))
        cvv_encrypted = f"encrypt({cvv})"
        cvv_masked = "***"
        
        card = Card(
            credit_account_id=account.id,
            card_product_id=card_product.id,
            card_type=request.card_type,
            pan_encrypted=encrypted_pan,
            pan_masked=masked_pan,
            expiry_date=expiry_date,
            expiry_date_masked=expiry_date_masked,
            cvv_encrypted=cvv_encrypted,
            cvv_masked=cvv_masked,
            card_status=CardStatus.INACTIVE,
            international_usage_enabled=False,
            ecommerce_enabled=True,
            atm_enabled=True
        )
        db.add(card)
        
        audit_log = AuditLog(
            action_type="CARD_ISSUED",
            actor_type="ADMIN",
            actor_id=admin_id,
            resource_id=card.id,
            previous_state={"status": "NONE"},
            new_state={"status": CardStatus.INACTIVE.value, "pan_masked": masked_pan}
        )
        db.add(audit_log)
        
        db.commit()
        db.refresh(card)
        return card

    @staticmethod
    def validate_card_activation(db: Session, card_id: UUID) -> dict:
        """
        Phase 1: Validate card exists, is INACTIVE, and generate OTP.
        """
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        
        if card.card_status != CardStatus.INACTIVE:
            raise HTTPException(status_code=400, detail=f"Card is already {card.card_status}")
            
        # Generate OTP
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        
        # Deactivate old OTPs for this card
        db.query(CardActivationOTP).filter(
            CardActivationOTP.card_id == card_id,
            CardActivationOTP.is_verified == False
        ).delete()
        
        activation_otp = CardActivationOTP(
            card_id=card.id,
            otp_hash=otp_hash,
            expires_at=get_expiry_time()
        )
        db.add(activation_otp)
        db.commit()
        
        # In real life, send SMS. For now, returned or logged.
        print(f"DEBUG: Activation OTP for card {card_id}: {otp}")
        
        return {
            "message": "Step 1: Card validated. OTP generated and sent to registered mobile.",
            "card_id": str(card.id),
            "status": "OTP_SENT"
        }

    @staticmethod
    def finalize_card_activation(db: Session, card_id: UUID, request: CardActivationRequest) -> dict:
        """
        Phase 2: Verify OTP, set PIN, and transition to ACTIVE.
        """
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
            
        if card.card_status != CardStatus.INACTIVE:
             raise HTTPException(status_code=400, detail="Card is not in an inactive state")
             
        otp_record = db.query(CardActivationOTP).filter(
            CardActivationOTP.card_id == card.id,
            CardActivationOTP.is_verified == False,
            CardActivationOTP.expires_at > datetime.now(timezone.utc)
        ).order_by(CardActivationOTP.created_at.desc()).first()
        
        if not otp_record or not verify_otp(request.otp, otp_record.otp_hash):
             raise HTTPException(status_code=400, detail="Invalid or expired OTP")
             
        # Activate card (PIN is set separately via set-pin endpoint)
        card.card_status = CardStatus.ACTIVE
        card.activation_date = datetime.now(timezone.utc)
        otp_record.is_verified = True
        
        audit_log = AuditLog(
            action_type="CARD_ACTIVATED",
            actor_type="USER",
            actor_id=card.credit_account.user_id,
            resource_id=card.id,
            previous_state={"status": CardStatus.INACTIVE.value},
            new_state={"status": CardStatus.ACTIVE.value}
        )
        db.add(audit_log)
        db.commit()
        
        return {
            "message": "Card activated successfully. Please set your PIN using the set-pin endpoint.",
            "card_id": str(card.id),
            "status": "ACTIVE",
            "activation_date": card.activation_date
        }

    @staticmethod
    def set_card_pin(db: Session, card_id: UUID, request: SetPinRequest) -> dict:
        """
        Set or update PIN for an active credit card.
        """
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        
        if card.card_status != CardStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Card must be active to set PIN")
        
        card.pin_hashed = hash_value(request.pin)
        
        audit_log = AuditLog(
            action_type="PIN_SET",
            actor_type="USER",
            actor_id=card.credit_account.user_id,
            resource_id=card.id,
            previous_state={"pin_set": card.pin_hashed is not None},
            new_state={"pin_set": True}
        )
        db.add(audit_log)
        db.commit()
        
        return {
            "message": "PIN has been set successfully.",
            "card_id": str(card.id)
        }

