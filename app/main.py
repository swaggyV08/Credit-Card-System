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
from app.schemas.responses import HealthCheckResponse
from app.schemas.base import envelope_success
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
    transactions, statements,
    payments, billing,
    jobs, fees,
    credit_products as user_credit_products
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
    
    # Run seeder (skip if testing)
    if os.getenv("TESTING") != "true":
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

from app.core.app_error import AppError, RefactoredException
from app.schemas.responses import ErrorResponse
from datetime import datetime, timezone

def _format_error(code: str, message: str, status_code: int, request: Request) -> dict:
    return {
        "error_code": code,
        "message": message,
        "status_code": status_code,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": request.url.path
    }

@app.exception_handler(RefactoredException)
async def refactored_error_handler(request: Request, exc: RefactoredException):
    logger.error(f"RefactoredException: {exc.error_code} - {exc.message}")
    response = _format_error(exc.error_code, exc.message, exc.status_code, request)
    return JSONResponse(status_code=exc.status_code, content=response)

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError: {exc.code} - {exc.message}")
    status = getattr(exc, "status_code", 400)
    response = _format_error(exc.code, exc.message, status, request)
    return JSONResponse(status_code=status, content=response)

@app.exception_handler(BankGradeException)
async def bank_grade_exception_handler(request: Request, exc: BankGradeException):
    logger.error(f"BankGradeException: {exc.code} - {exc.message}")
    status = getattr(exc, "status_code", 400)
    response = _format_error(exc.code, exc.message, status, request)
    return JSONResponse(status_code=status, content=response)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error = errors[0] if errors else {}
    field = ".".join(str(loc) for loc in error.get("loc", []) if loc != "body")
    msg = error.get("msg", "Validation error")
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
        
    full_msg = f"{field}: {msg}" if field else msg
    response = _format_error("VALIDATION_ERROR", full_msg, 422, request)
    logger.warning(f"Validation Error: {response}")
    return JSONResponse(status_code=422, content=response)

@app.exception_handler(IdempotencyConflictError)
async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError):
    logger.error(f"Idempotency Conflict: {exc.message}")
    response = _format_error("DUPLICATE_IDEMPOTENCY_KEY", exc.message, 409, request)
    return JSONResponse(status_code=409, content=response)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = exc.status_code
    message = str(exc.detail)
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message", str(exc.detail))
    logger.warning(f"HTTPException [{code}]: {message}")
    
    # Map 404/403 directly if there isn't a specific code supplied
    error_code = "NOT_FOUND" if code == 404 else "FORBIDDEN" if code == 403 else "HTTP_ERROR"
    response = _format_error(error_code, message, code, request)
    return JSONResponse(status_code=code, content=response, headers=exc.headers)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Internal Server Error")
    response = _format_error("INTERNAL_ERROR", "An unhandled internal error occurred.", 500, request)
    return JSONResponse(status_code=500, content=response)


app.include_router(new_auth.router)
app.include_router(new_auth.admin_router)
app.include_router(customer.router)
app.include_router(application.router)
app.include_router(credit_product.router)

# user-facing product catalog routers
app.include_router(user_credit_products.router)
app.include_router(card_products.router)

# admin management routers
app.include_router(admin_users.router)
app.include_router(credit_accounts.router)
app.include_router(cards.router)
app.include_router(cards.issue_router)

# transaction processing routers
app.include_router(transactions.router)
app.include_router(payments.router)
app.include_router(billing.router)
app.include_router(statements.router)
app.include_router(jobs.router)
app.include_router(fees.router)

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

@app.get("/", response_model=HealthCheckResponse)
def root():
    return envelope_success({
        "application": "ZBANQUe Credit Card System",
        "version": "1.0.0",
        "status": "running"
    })