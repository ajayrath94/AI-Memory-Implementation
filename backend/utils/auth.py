"""
Authentication Module — Nancy AI
Supports two auth methods:

1. JWT (Supabase) — for real users (elderly + caregivers)
   Header: Authorization: Bearer <jwt_token>
   Extracts user_id from JWT automatically

2. API Key — for internal services + testing
   Header: X-API-Key: <api_key>
   Used during development and server-to-server calls

Priority: JWT > API Key
"""

import os
import jwt as pyjwt
from fastapi import Security, HTTPException, status, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
from typing import Optional

# ── Security schemes ───────────────────────────────────────────────────────────
_bearer_scheme  = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── JWT Config ─────────────────────────────────────────────────────────────────
def _get_jwt_secret() -> str:
    """Get Supabase JWT secret for verification."""
    return os.getenv("SUPABASE_JWT_SECRET", "")

def _get_valid_keys() -> set:
    """Get valid API keys from environment."""
    raw = os.getenv("API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}

# ── Token verification ─────────────────────────────────────────────────────────
def _verify_jwt(token: str) -> Optional[dict]:
    """
    Verify Supabase JWT token and extract claims.
    Returns payload dict or None if invalid.
    """
    secret = _get_jwt_secret()
    if not secret:
        return None
    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms  = ["HS256"],
            audience    = "authenticated",
            options     = {"verify_exp": True},
        )
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Token expired — please login again",
        )
    except pyjwt.InvalidTokenError as e:
        return None

# ── User context ───────────────────────────────────────────────────────────────
class UserContext:
    """Authenticated user context passed to route handlers."""
    def __init__(
        self,
        user_id:   str,
        auth_type: str,  # 'jwt' | 'api_key'
        email:     Optional[str] = None,
        phone:     Optional[str] = None,
        role:      str = "user",  # 'user' | 'caregiver' | 'service'
    ):
        self.user_id   = user_id
        self.auth_type = auth_type
        self.email     = email
        self.phone     = phone
        self.role      = role

    def __repr__(self):
        return f"UserContext(user_id={self.user_id}, role={self.role}, auth={self.auth_type})"

# ── Main auth dependency ───────────────────────────────────────────────────────
async def require_auth(
    request:     Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    api_key:     Optional[str] = Security(_api_key_header),
) -> UserContext:
    """
    Main auth dependency — accepts JWT or API key.
    Returns UserContext with user_id and role.
    """
    # Always allow CORS preflight
    if request.method == "OPTIONS":
        return UserContext(user_id="preflight", auth_type="preflight")

    # ── Try JWT first (priority) ───────────────────────────────────────────────
    if credentials and credentials.credentials:
        token   = credentials.credentials
        payload = _verify_jwt(token)

        if payload:
            user_id = payload.get("sub", "")
            email   = payload.get("email")
            phone   = payload.get("phone")
            role    = payload.get("role", "authenticated")

            # Determine role
            user_role = "caregiver" if email else "user"

            return UserContext(
                user_id   = user_id,
                auth_type = "jwt",
                email     = email,
                phone     = phone,
                role      = user_role,
            )

    # ── Try API key (fallback for dev/testing) ─────────────────────────────────
    if api_key:
        valid_keys = _get_valid_keys()
        if valid_keys and api_key in valid_keys:
            return UserContext(
                user_id   = "service",
                auth_type = "api_key",
                role      = "service",
            )

    # ── No valid auth ──────────────────────────────────────────────────────────
    raise HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail      = "Authentication required — provide JWT token or API key",
        headers     = {"WWW-Authenticate": "Bearer"},
    )

# ── Backward compatible alias ──────────────────────────────────────────────────
# Keeps existing routes working without changes
async def require_api_key(
    request:     Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    api_key:     Optional[str] = Security(_api_key_header),
) -> str:
    """
    Backward compatible wrapper — accepts JWT or API key.
    Returns user_id string for use in existing routes.
    """
    ctx = await require_auth(request, credentials, api_key)
    return ctx.user_id

# ── Caregiver-only routes ──────────────────────────────────────────────────────
async def require_caregiver(
    request:     Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    api_key:     Optional[str] = Security(_api_key_header),
) -> UserContext:
    """Only caregivers (email auth) can access these routes."""
    ctx = await require_auth(request, credentials, api_key)
    if ctx.role not in ("caregiver", "service"):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "Caregiver access required",
        )
    return ctx

# ── Extract user_id from JWT (utility) ────────────────────────────────────────
def extract_user_id_from_token(token: str) -> Optional[str]:
    """Extract user_id from JWT without full validation — for internal use."""
    try:
        payload = pyjwt.decode(token, options={"verify_signature": False})
        return payload.get("sub")
    except Exception:
        return None
