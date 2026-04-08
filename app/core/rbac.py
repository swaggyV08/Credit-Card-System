"""
Server-level RBAC — the single source of truth for permission enforcement.

Usage in routers:
    from app.core.rbac import require, AuthenticatedPrincipal

    @router.post(
        "",
        dependencies=[Depends(require("transaction:initiate"))],
    )
    async def initiate_transaction(
        principal: AuthenticatedPrincipal = Depends(require("transaction:initiate")),
        db: Session = Depends(get_db),
    ): ...
"""
from __future__ import annotations

from uuid import UUID
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.roles import Role
from app.core.config import settings
from app.core.jwt import decode_access_token

oauth2_scheme = HTTPBearer()

# ─── AuthenticatedPrincipal ────────────────────────────────────────

class AuthenticatedPrincipal(BaseModel):
    user_id: str
    role: Role
    jti: str | None = None
    token_type: str = "USER"   # "USER" | "ADMIN"

    model_config = {"arbitrary_types_allowed": True}


# ─── Permission → Allowed Roles Map ───────────────────────────────

ROLE_PERMISSIONS: dict[str, set[Role]] = {

    # ── Authentication ──────────────────────────────────────────
    "auth:register":              {Role.USER},
    "auth:login":                 {Role.USER},
    "auth:password_reset":        {Role.USER},
    "auth:otp":                   {Role.USER},
    "admin:login":                {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.SALES},
    "admin:create":               {Role.SUPERADMIN},

    # ── Customer CIF & KYC ──────────────────────────────────────
    "cif:write":                  {Role.USER},
    "cif:read":                   {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "kyc:conduct":                {Role.USER, Role.SALES},
    "customer:read":              {Role.USER, Role.SALES, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "customer:set_pin":           {Role.USER},

    # ── Applications ────────────────────────────────────────────
    "application:submit":         {Role.USER, Role.SALES},
    "application:read":           {Role.SALES, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "application:evaluate":       {Role.MANAGER},
    "application:configure":      {Role.MANAGER},
    "application:issue_card":     {Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},

    # ── Credit Products ─────────────────────────────────────────
    "credit_product:create":      {Role.ADMIN, Role.SUPERADMIN},
    "credit_product:read":        {Role.ADMIN, Role.MANAGER, Role.SALES, Role.SUPERADMIN},
    "credit_product:status":      {Role.MANAGER},
    "credit_product:delete":      {Role.MANAGER},

    # ── Card Products ───────────────────────────────────────────
    "card_product:create":        {Role.ADMIN, Role.SUPERADMIN},
    "card_product:read":          {Role.ADMIN, Role.MANAGER, Role.SALES, Role.SUPERADMIN},
    "card_product:approve":       {Role.MANAGER},
    "card_product:delete":        {Role.MANAGER},

    # ── User Management (admin) ──────────────────────────────────
    "user:list":                  {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},
    "user:detail":                {Role.ADMIN, Role.MANAGER, Role.SALES, Role.SUPERADMIN},
    "credit_account:list":        {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},
    "credit_account:detail":      {Role.ADMIN, Role.MANAGER, Role.SALES, Role.SUPERADMIN},
    "credit_account:update":      {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Cards ────────────────────────────────────────────────────
    "card:activate":              {Role.USER},
    "card:lifecycle":             {Role.USER, Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},
    "card:read":                  {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "card:issue":                 {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Transactions ─────────────────────────────────────────────
    "transaction:initiate":       {Role.USER},
    "transaction:read":           {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "transaction:state":          {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Settlement ───────────────────────────────────────────────
    "settlement:run":             {Role.ADMIN, Role.SUPERADMIN},

    # ── Disputes ─────────────────────────────────────────────────
    "dispute:raise":              {Role.USER},
    "dispute:manage":             {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Refunds ──────────────────────────────────────────────────
    "refund:process":             {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Statements ───────────────────────────────────────────────
    "statement:read":             {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},

    # ── Fees ─────────────────────────────────────────────────────
    "fee:apply":                  {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},

    # ── Payments ─────────────────────────────────────────────────
    "payment:make":               {Role.USER},
    "payment:read":               {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},

    # ── Card Controls ────────────────────────────────────────────
    "controls:read":              {Role.USER, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "controls:update":            {Role.USER, Role.ADMIN, Role.SUPERADMIN},

    # ── Billing ──────────────────────────────────────────────────
    "billing:generate":           {Role.ADMIN, Role.SUPERADMIN},

    # ── Fraud ────────────────────────────────────────────────────
    "fraud:read":                 {Role.ADMIN, Role.MANAGER, Role.SUPERADMIN},
    # ── Bureau ───────────────────────────────────────────────────
    "bureau:read_own":            {Role.USER, Role.SALES, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "bureau:read_any":            {Role.SALES, Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
    "bureau:trigger":             {Role.MANAGER, Role.ADMIN, Role.SUPERADMIN},
}


# ─── Dependency Factory ───────────────────────────────────────────

def _resolve_role(payload: dict) -> Role:
    """
    Resolve the Role from JWT payload.
    Admin tokens have type=ADMIN; their role comes from the 'role' claim.
    User tokens have type=USER; role is always USER.

    Legacy compatibility: maps old 'SUPER_ADMIN' claim values to SUPERADMIN.
    """
    token_type = str(payload.get("token_type") or payload.get("type", "USER")).upper()
    role_claim = payload.get("role", "USER")

    if token_type == "ADMIN":
        # Legacy compat: SUPER_ADMIN in old tokens → SUPERADMIN
        if role_claim == "SUPER_ADMIN":
            return Role.SUPERADMIN
        try:
            return Role(role_claim)
        except ValueError:
            return Role.ADMIN
    else:
        return Role.USER


def require(permission: str):
    """
    Returns a FastAPI dependency that:
    1. Extracts Bearer token from Authorization header
    2. Decodes JWT — validates exp, iat, signature
    3. Reads role claim from payload
    4. Checks role is in ROLE_PERMISSIONS[permission]
    5. Raises HTTP 401 if token is invalid/expired
    6. Raises HTTP 403 with INSUFFICIENT_PERMISSIONS if role not in allowed set
    7. Returns AuthenticatedPrincipal downstream
    """
    def _dependency(
        credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    ) -> AuthenticatedPrincipal:
        token = credentials.credentials
        payload = decode_access_token(token)

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Token missing subject"},
            )

        jti = payload.get("jti")
        if jti:
            from app.models.token_blacklist import BlacklistedToken
            from app.db.session import get_db
            db_gen = get_db()
            db = next(db_gen)
            blacklisted = db.query(BlacklistedToken).filter(BlacklistedToken.jti == jti).first()
            db_gen.close()
            if blacklisted:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "ACCOUNT_BLOCKED", "message": "Session invalidated. Your account is blocked."}
                )

        role = _resolve_role(payload)
        token_type = str(payload.get("token_type") or payload.get("type", "USER")).upper()
        jti = payload.get("jti")

        allowed = ROLE_PERMISSIONS.get(permission, set())
        if role not in allowed and role != Role.SUPERADMIN:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": (
                        f"Role {role.value} is not authorised "
                        f"to perform '{permission}'"
                    ),
                },
            )

        return AuthenticatedPrincipal(
            user_id=sub,
            role=role,
            jti=jti,
            token_type=token_type,
        )

    _dependency.permission_name = permission
    return _dependency
