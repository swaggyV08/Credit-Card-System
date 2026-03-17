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
from app.api import auth
from app.api import customer
from app.api import application
from app.api.v1.endpoints import card_management
from app.admin.api import auth as admin_auth, credit_product, card_product, user_mgmt as admin_user_mgmt, credit_account_admin
from app.core.exceptions import BankGradeException

app = FastAPI(title="ZBANQUe Credit Card System")

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
app.include_router(card_management.router, prefix="/cards", tags=["Cards"])
app.include_router(card_management.issue_router, prefix="/card_product", tags=["Card Issuance"])

@app.get("/")
def root():
    return {"message": "ZBANQUe Credit Card System Running"}