from sqlalchemy.orm import Session
from app.models.auth import User
from app.core.app_error import AppError

class CIFService:
    @staticmethod
    def assert_cif_kyc_complete(user: User) -> None:
        """
        Enforce CIF and KYC completion gate for the service layer.
        Raises domain-level AppErrors if the checks fail.
        """
        if not user.is_cif_completed:
            raise AppError(
                code="CIF_INCOMPLETE",
                message="Customer Information File (CIF) must be completed before proceeding.",
                http_status=403
            )
            
        if not user.is_kyc_completed:
            raise AppError(
                code="KYC_INCOMPLETE",
                message="KYC verification must be completed before proceeding.",
                http_status=403
            )
