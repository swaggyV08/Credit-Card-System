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

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.api import auth, customer, application, billing
from app.api import legacy_transactions as transactions
from app.api.v1.endpoints import card_management
from app.admin.api import auth as admin_auth, credit_product, card_product, user_mgmt as admin_user_mgmt, credit_account_admin, transactions_admin
from app.core.exceptions import BankGradeException

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

@app.exception_handler(BankGradeException)
async def bank_grade_exception_handler(request: Request, exc: BankGradeException):
    # Ensure banking-grade errors are human readable
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": f"{exc.message} (Code: {exc.code})"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Detailed human-readable validation error
    error_details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        msg = error["msg"]
        error_details.append(f"Field '{field}' {msg}")
    
    human_message = "Validation Error: " + "; ".join(error_details)
    return JSONResponse(
        status_code=422,
        content={"message": human_message}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    import traceback
    print(traceback.format_exc()) # Log it for internal use
    return JSONResponse(
        status_code=500,
        content={"message": f"An unhandled internal error occurred: {str(exc)}"}
    )

app.include_router(auth.router)
app.include_router(admin_auth.router, prefix="/admin")
app.include_router(customer.router)
app.include_router(application.router)
app.include_router(credit_product.router)
app.include_router(card_product.router)
app.include_router(admin_user_mgmt.router)
app.include_router(credit_account_admin.router)
app.include_router(transactions_admin.router, prefix="/admin/transactions", tags=["Admin Transactions"])
app.include_router(card_management.router, prefix="/cards", tags=["Cards"])
app.include_router(card_management.issue_router, prefix="/card_product", tags=["Card Issuance"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])

# =====================================================
# TRANSACTION PROCESSING SYSTEM (v1 API)
# =====================================================
from app.api.transactions.transaction_routes import (
    txn_router, hold_router, clearing_router, dispute_router, refund_router
)
from app.api.transactions.operations_routes import (
    stmt_router, fee_router, payment_router, controls_router, risk_router, recon_router
)

app.include_router(txn_router)      # Group 1: Transactions
app.include_router(hold_router)     # Group 2: Holds
app.include_router(clearing_router) # Group 3: Clearing & Settlement
app.include_router(dispute_router)  # Group 4: Disputes
app.include_router(refund_router)   # Group 5: Refunds
app.include_router(stmt_router)     # Group 6: Statements
app.include_router(fee_router)      # Group 7: Fees & Interest
app.include_router(payment_router)  # Group 8: Payments
app.include_router(controls_router) # Group 9: Card Controls
app.include_router(risk_router)     # Group 10: Fraud & Risk
app.include_router(recon_router)    # Group 11: Reconciliation & Audit

@app.get("/")
def root():
    return {"message": "ZBANQUe Credit Card System Running"}