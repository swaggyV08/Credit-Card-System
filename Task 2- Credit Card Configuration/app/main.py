from fastapi import FastAPI
from app.api import auth
from app.api import customer
from app.api import application
from app.admin.api import auth as admin_auth, credit_product, card_product, issuance

app = FastAPI(title="ZBANQUe Credit Card System")

app.include_router(auth.router)
app.include_router(admin_auth.router)
app.include_router(customer.router)
app.include_router(application.router)
app.include_router(credit_product.router)
app.include_router(card_product.router)
app.include_router(issuance.router)

@app.get("/")
def root():
    return {"message": "ZBANQUe Credit Card System Running"}