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

from contextlib import asynccontextmanager
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
    transactions, disputes, settlement,
    statements, payments, controls, billing
)
from app.core.exceptions import BankGradeException
from app.core.app_error import AppError
from app.core.exceptions import IdempotencyConflictError

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start asyncio billing scheduler on startup."""
    from app.jobs.billing_jobs import start_billing_scheduler
    from app.db.seeder import seed_super_admin
    from app.db.session import SessionLocal
    
    # Run seeder
    try:
        db = SessionLocal()
        seed_super_admin(db)
        db.close()
    except Exception as e:
        print(f"[WARN] Seeder failed: {e}")
        
    try:
        await start_billing_scheduler()
    except Exception as e:
        import traceback
        print(f"[WARN] Billing scheduler not started: {e}")
        traceback.print_exc()
    yield
    # Shutdown: asyncio tasks are cancelled automatically when the process ends


app = FastAPI(
    title="ZBANQUe Credit Card System",
    description=description,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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

import logging
logger = logging.getLogger("zbanque_api")

from app.schemas.base import envelope_error, ErrorDetail

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError: {exc.code} - {exc.message}")
    error = ErrorDetail(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=envelope_error([error], exc.status_code))


@app.exception_handler(BankGradeException)
async def bank_grade_exception_handler(request: Request, exc: BankGradeException):
    logger.error(f"BankGradeException: {exc.code} - {exc.message}")
    error = ErrorDetail(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=envelope_error([error], exc.status_code))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        msg = error["msg"]
        errors.append(ErrorDetail(code="VALIDATION_ERROR", message=msg, field=field))
    logger.warning(f"Validation Error: {errors}")
    return JSONResponse(status_code=422, content=envelope_error(errors, 422))


@app.exception_handler(IdempotencyConflictError)
async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError):
    logger.error(f"Idempotency Conflict: {exc.message}")
    error = ErrorDetail(code=exc.code, message=exc.message)
    return JSONResponse(status_code=409, content=envelope_error([error], 409))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = "HTTP_ERROR"
    message = str(exc.detail)
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", "HTTP_ERROR")
        message = exc.detail.get("message", str(exc.detail))
    logger.warning(f"HTTPException [{exc.status_code}]: {message}")
    error = ErrorDetail(code=code, message=message)
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope_error([error], exc.status_code),
        headers=exc.headers
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Internal Server Error")
    error = ErrorDetail(code="SERVER_ERROR", message="An unhandled internal error occurred.")
    return JSONResponse(status_code=500, content=envelope_error([error], 500))


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
app.include_router(disputes.router)
app.include_router(settlement.router)
app.include_router(statements.router)
app.include_router(payments.router)
app.include_router(controls.router)
app.include_router(billing.router)

# ── Scheduler is started in the lifespan context manager above ────────────

from app.core.rbac import ROLE_PERMISSIONS
from fastapi.routing import APIRoute

def _enhance_route_descriptions():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
            
        permission = None
        for dep in route.dependencies:
            if hasattr(dep.dependency, "permission_name"):
                permission = dep.dependency.permission_name
                break
                
        if permission:
            roles = ROLE_PERMISSIONS.get(permission, set())
            roles_list = list(roles)
            role_order = ["SUPERADMIN", "ADMIN", "MANAGER", "SALES", "USER"]
            sorted_roles = sorted(roles_list, key=lambda x: role_order.index(x.value if hasattr(x, 'value') else x) if (x.value if hasattr(x, 'value') else x) in role_order else 99)
            
            roles_str = f"[{','.join(r.value if hasattr(r, 'value') else str(r) for r in sorted_roles)}]"
            access_text = f"\n\n**ROLES THAT CAN ACCESS THE ENDPOINT:** `{roles_str}`"
            
            if route.description:
                if "ROLES THAT CAN ACCESS THE ENDPOINT" not in route.description:
                    route.description += access_text
            else:
                route.description = access_text

_enhance_route_descriptions()

@app.get("/")
def root():
    return {"message": "ZBANQUe Credit Card System Running"}