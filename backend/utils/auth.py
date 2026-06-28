"""
API Key Authentication
All endpoints require a valid X-API-Key header.
OPTIONS requests (CORS preflight) are always allowed through.
Keys are defined in .env as a comma-separated list:
  API_KEYS=key1,key2,key3
"""

import os
from fastapi import Security, HTTPException, status, Request
from fastapi.security.api_key import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def _get_valid_keys() -> set:
    raw = os.getenv("API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


async def require_api_key(
    request: Request,
    api_key: str = Security(_api_key_header)
) -> str:
    # Always allow CORS preflight
    if request.method == "OPTIONS":
        return "preflight"

    valid_keys = _get_valid_keys()

    if not valid_keys:
        print("WARNING: No API_KEYS set in .env — endpoint is unprotected!")
        return "dev-mode"

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    return api_key
