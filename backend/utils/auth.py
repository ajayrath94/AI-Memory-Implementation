"""
API Key Authentication
All endpoints require a valid X-API-Key header.
Keys are defined in .env as a comma-separated list:
  API_KEYS=key1,key2,key3

Generate a key:
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
"""

import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def _get_valid_keys() -> set:
    raw = os.getenv("API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


async def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    valid_keys = _get_valid_keys()

    if not valid_keys:
        # No keys configured — allow in dev mode but warn loudly
        print("⚠️  WARNING: No API_KEYS set in .env — endpoint is unprotected!")
        return "dev-mode"

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    return api_key
