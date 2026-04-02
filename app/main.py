import os
import platform
import collections

# Fix for platform.uname() hang on some Windows environments
# N.B. We use os.name == 'nt' instead of platform.system() because platform.system() calls uname()!
if os.name == 'nt':
    try:
        UnameResult = collections.namedtuple('uname_result', ['system', 'node', 'release', 'version', 'machine', 'processor'])
        platform.uname = lambda: UnameResult('Windows', 'local-node', '10', '10.0.19041', 'AMD64', 'Intel64 Family 6 Model 158 Stepping 10')
    except Exception:
        pass

from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.core.middleware.request_id import RequestIDMiddleware
from app.core.middleware.timing import TimingMiddleware
from app.routers import auth as new_auth
from app.api import customer, application
from app.admin.api import credit_product
from app.routers import (
    card_products, admin_users, credit_accounts, cards,
    transactions, holds, disputes, clearing, settlement,
    statements, fees, payments, controls, refunds
)
from app.core.exceptions import BankGradeException
from app.core.app_error import AppError

description = """
This REST API provides complete Credit Card Management functionality.

### Core Modules:
- **Customer Registration & Profile Management:** Handles new customer onboarding and personal/financial data.
- **Credit Card Application Processing:** Manages the end-to-end application lifecycle.
- **Underwriting & Risk Evaluation:** Automated scoring and decision-making for credit limits.
- **Credit Card Account Management:** Administration of active credit accounts and cards.
- **Transactions & Billing:** Real-time transaction ledgering and statement generation.
- **Payments Processing:** Handling of repayments and account adjustments.
- **Fraud & Compliance Monitoring:** KYC, FATCA, and risk logging.

### Authentication Flow:
1. **Registration:** Create a session using `/auth/registrations`.
2. **OTP Verification:** Verify the session via `/auth/otp/{user_id}` with `command=verify`.
3. **Login:** Obtain a JWT access token via `/auth/sessions/email`.
4. **Authorize:** 
    - Click the **Authorize** button in Swagger UI.
    - Enter the token in the format: `Bearer <your_jwt_token>`.
5. **Access Secured Endpoints:** All subsequent requests will include the Authorization header.

*Note: All secured endpoints require a valid JWT token with appropriate role permissions.*
"""

app = FastAPI(
    title="ZBANQUe Credit Card System",
    description=description,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
    allow_headers=["*", "Idempotency-Key", "X-Request-ID"]
)

def _envelope_error(status_code: int, message: str, code: str | None = None, errors: list | None = None):
    """Build a ResponseEnvelope-shaped error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "data": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "errors": errors or [
                {
                    "code": code or f"HTTP_{status_code}",
                    "message": message,
                }
            ],
        },
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return _envelope_error(
        status_code=exc.status_code,
        message=exc.message,
        code=exc.code,
    )


@app.exception_handler(BankGradeException)
async def bank_grade_exception_handler(request: Request, exc: BankGradeException):
    return _envelope_error(
        status_code=exc.status_code,
        message=exc.message,
        code=exc.code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        msg = error["msg"]
        error_details.append({"code": "VALIDATION_ERROR", "message": f"Field '{field}': {msg}"})
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "data": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            "errors": error_details,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = None
    message = str(exc.detail)
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        message = exc.detail.get("message", str(exc.detail))
    return _envelope_error(
        status_code=exc.status_code,
        message=message,
        code=code,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    import traceback
    print(traceback.format_exc())
    return _envelope_error(
        status_code=500,
        message="An unhandled internal error occurred.",
        code="INTERNAL_ERROR",
    )

app.include_router(new_auth.router)
app.include_router(new_auth.admin_router)
app.include_router(customer.router)
app.include_router(application.router)
app.include_router(credit_product.router)

# newly refactored routers
app.include_router(card_products.router)
app.include_router(admin_users.router)
app.include_router(credit_accounts.router)
app.include_router(cards.router)
app.include_router(cards.issue_router)

# refactored transaction processing routers
app.include_router(transactions.router)
app.include_router(holds.router)
app.include_router(disputes.router)
app.include_router(clearing.router)
app.include_router(settlement.router)
app.include_router(statements.router)
app.include_router(fees.router)
app.include_router(payments.router)
app.include_router(controls.router)
app.include_router(refunds.router)

@app.get("/")
def root():
    return {"message": "ZBANQUe Credit Card System Running"}