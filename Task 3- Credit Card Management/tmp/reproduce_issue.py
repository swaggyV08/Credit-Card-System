import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from datetime import date

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.base import Base # This imports all models
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_issuance import CreditCardApplication
from app.admin.models.credit_product import CreditProductInformation
from app.admin.models.card_product import CardProductCore
from app.admin.services.issuance_svc import CardIssuanceService
from app.models.enums import ApplicationStatus, ApplicationStage, EmploymentType, Country

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def reproduce():
    try:
        # 1. Create a dummy user
        user = User(
            email=f"test_{uuid4().hex[:6]}@example.com",
            country_code="+91",
            phone_number="1234567890",
            is_active=True,
            is_cif_completed=True,
            is_kyc_completed=True
        )
        db.add(user)
        db.flush()

        # 2. Create a dummy customer profile
        cif = CustomerProfile(
            user_id=user.id,
            first_name="Test",
            last_name="User",
            cif_number=f"CIF{uuid4().hex[:6].upper()}",
            date_of_birth=date(1990, 1, 1),
            country_of_residence=Country.INDIA
        )
        db.add(cif)
        db.flush()

        # 3. Get or create a credit product
        credit_product = db.query(CreditProductInformation).first()
        if not credit_product:
            print("No credit product found. Please seed the database first.")
            return

        # 4. Get or create a card product
        card_product = db.query(CardProductCore).filter(CardProductCore.credit_product_id == credit_product.id).first()
        if not card_product:
            print("No card product found for credit product.")
            return

        # 5. Create application
        app = CreditCardApplication(
            user_id=user.id,
            cif_id=cif.id,
            credit_product_id=credit_product.id,
            card_product_id=card_product.id,
            application_status=ApplicationStatus.SUBMITTED,
            current_stage=ApplicationStage.KYC,
            declared_income=500000,
            employment_status="SALARIED"
        )
        db.add(app)
        db.flush()

        print(f"Created application: {app.id}")
        print(f"Initial bureau_score: {app.bureau_score}")
        print(f"Initial risk_band: {app.risk_band}")

        # 6. Run engines
        print("Running engines...")
        CardIssuanceService.run_engines(db, app)

        # 7. Check results
        db.refresh(app)
        print(f"After refresh - bureau_score: {app.bureau_score}")
        print(f"After refresh - risk_band: {app.risk_band}")

        # 8. Check if records exist in BureauReport and RiskAssessment
        from app.models.credit import BureauReport, RiskAssessment
        b_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
        r_assessment = db.query(RiskAssessment).filter(RiskAssessment.application_id == app.id).first()

        print(f"BureauReport record: {b_report.bureau_score if b_report else 'None'}")
        print(f"RiskAssessment record: {r_assessment.risk_band if r_assessment else 'None'}")

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.rollback()
        db.close()

if __name__ == "__main__":
    reproduce()
