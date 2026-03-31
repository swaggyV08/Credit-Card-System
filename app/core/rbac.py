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
    "admin:login":                {Role.ADMIN, Role.MANAGER, Role.SALES},
    "admin:create":               {Role.ADMIN},

    # ── Customer CIF & KYC ──────────────────────────────────────
    "cif:write":                  {Role.USER},
    "cif:read":                   {Role.USER, Role.MANAGER, Role.ADMIN},
    "kyc:conduct":                {Role.USER, Role.SALES},
    "customer:read":              {Role.USER, Role.SALES, Role.MANAGER, Role.ADMIN},
    "customer:set_pin":           {Role.USER},

    # ── Applications ────────────────────────────────────────────
    "application:submit":         {Role.USER, Role.SALES},
    "application:read":           {Role.USER, Role.SALES, Role.MANAGER, Role.ADMIN},
    "application:evaluate":       {Role.MANAGER, Role.ADMIN},
    "application:configure":      {Role.MANAGER, Role.ADMIN},
    "application:issue_card":     {Role.MANAGER, Role.ADMIN},

    # ── Credit Products ─────────────────────────────────────────
    "credit_product:create":      {Role.ADMIN},
    "credit_product:read":        {Role.ADMIN, Role.MANAGER, Role.SALES},
    "credit_product:status":      {Role.ADMIN},
    "credit_product:delete":      {Role.ADMIN},

    # ── Card Products ───────────────────────────────────────────
    "card_product:create":        {Role.ADMIN},
    "card_product:read":          {Role.ADMIN, Role.MANAGER, Role.SALES},
    "card_product:approve":       {Role.ADMIN},
    "card_product:delete":        {Role.ADMIN},

    # ── User Management (admin) ──────────────────────────────────
    "user:list":                  {Role.ADMIN, Role.MANAGER},
    "user:detail":                {Role.ADMIN, Role.MANAGER, Role.SALES},
    "credit_account:list":        {Role.ADMIN, Role.MANAGER},
    "credit_account:detail":      {Role.ADMIN, Role.MANAGER, Role.SALES},
    "credit_account:update":      {Role.ADMIN, Role.MANAGER},

    # ── Cards ────────────────────────────────────────────────────
    "card:activate":              {Role.USER},
    "card:lifecycle":             {Role.USER, Role.ADMIN, Role.MANAGER},
    "card:read":                  {Role.USER, Role.MANAGER, Role.ADMIN},
    "card:issue":                 {Role.ADMIN, Role.MANAGER},

    # ── Transactions ─────────────────────────────────────────────
    "transaction:initiate":       {Role.USER},
    "transaction:read":           {Role.USER, Role.MANAGER, Role.ADMIN},
    "transaction:state":          {Role.ADMIN, Role.MANAGER},

    # ── Settlement ───────────────────────────────────────────────
    "settlement:run":             {Role.ADMIN},

    # ── Disputes ─────────────────────────────────────────────────
    "dispute:raise":              {Role.USER},
    "dispute:manage":             {Role.ADMIN, Role.MANAGER},

    # ── Refunds ──────────────────────────────────────────────────
    "refund:process":             {Role.ADMIN, Role.MANAGER},

    # ── Statements ───────────────────────────────────────────────
    "statement:read":             {Role.USER, Role.MANAGER, Role.ADMIN},

    # ── Fees ─────────────────────────────────────────────────────
    "fee:apply":                  {Role.ADMIN, Role.MANAGER},

    # ── Payments ─────────────────────────────────────────────────
    "payment:make":               {Role.USER},
    "payment:read":               {Role.USER, Role.MANAGER, Role.ADMIN},

    # ── Card Controls ────────────────────────────────────────────
    "controls:read":              {Role.USER, Role.MANAGER, Role.ADMIN},
    "controls:update":            {Role.USER, Role.ADMIN},
}


# ─── Dependency Factory ───────────────────────────────────────────

def _resolve_role(payload: dict) -> Role:
    """
    Resolve the Role from JWT payload.
    Admin tokens have type=ADMIN; their role comes from the 'role' claim.
    User tokens have type=USER; role is always USER.
    """
    token_type = payload.get("type", "USER")
    role_claim = payload.get("role", "USER")

    if token_type == "ADMIN":
        # Map old SUPERADMIN values to ADMIN
        if role_claim == "SUPERADMIN":
            return Role.ADMIN
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
    6. Raises HTTP 403 with message if role not in allowed set
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

        role = _resolve_role(payload)
        token_type = payload.get("type", "USER")
        jti = payload.get("jti")

        allowed = ROLE_PERMISSIONS.get(permission, set())
        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FORBIDDEN",
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

    return _dependency
