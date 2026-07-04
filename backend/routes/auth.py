"""
AUTH ROUTES
Caregiver authentication via Supabase Auth.

Supabase handles:
  - Password hashing
  - JWT token generation
  - Email verification
  - Password reset OTP

We just proxy the calls and link to our caregivers table.

Endpoints:
  POST /auth/caregiver/signup       → create account
  POST /auth/caregiver/login        → sign in
  POST /auth/caregiver/logout       → sign out
  POST /auth/caregiver/reset-request → send OTP
  POST /auth/caregiver/reset-confirm → reset password
  GET  /auth/caregiver/me           → get current caregiver profile
  POST /auth/user/otp-request       → send OTP to elderly user phone
  POST /auth/user/otp-verify        → verify OTP, create user session
"""

import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────────────────

class CaregiverSignup(BaseModel):
    name:     str
    email:    str
    password: str
    phone:    Optional[str] = None
    org_type: Optional[str] = "family"
    org_name: Optional[str] = None

class CaregiverLogin(BaseModel):
    email:    str
    password: str

class ResetRequest(BaseModel):
    email: str

class ResetConfirm(BaseModel):
    email:        str
    otp:          str
    new_password: str

class OTPRequest(BaseModel):
    phone: str  # e.g. "+919876543210"

class OTPVerify(BaseModel):
    phone: str
    token: str


# ── Supabase Auth client ───────────────────────────────────────────────────────

def get_supabase_auth():
    """Get Supabase client for auth operations."""
    from supabase_store import get_client
    return get_client()


# ── Caregiver auth ─────────────────────────────────────────────────────────────

@router.post("/caregiver/signup")
async def caregiver_signup(req: CaregiverSignup):
    """
    Create a new caregiver account.
    1. Create Supabase Auth user
    2. Insert into caregivers table with auth_id
    """
    db = get_supabase_auth()

    try:
        # Step 1: Create Supabase Auth user
        auth_response = db.auth.sign_up({
            "email":    req.email.lower().strip(),
            "password": req.password,
            "options": {
                "data": {
                    "name":     req.name,
                    "org_type": req.org_type or "family",
                }
            }
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create account")

        auth_id = auth_response.user.id

        # Step 2: Insert into caregivers table
        caregiver = db.table("caregivers").insert({
            "name":     req.name.strip(),
            "email":    req.email.lower().strip(),
            "phone":    req.phone,
            "org_type": req.org_type or "family",
            "org_name": req.org_name,
            "auth_id":  auth_id,
        }).execute()

        return {
            "status":       "ok",
            "message":      "Account created successfully",
            "caregiver_id": caregiver.data[0]["id"] if caregiver.data else None,
            "session":      auth_response.session.model_dump() if auth_response.session else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg or "already exists" in error_msg:
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=400, detail=error_msg)


@router.post("/caregiver/login")
async def caregiver_login(req: CaregiverLogin):
    """Sign in caregiver and return session token."""
    db = get_supabase_auth()

    try:
        auth_response = db.auth.sign_in_with_password({
            "email":    req.email.lower().strip(),
            "password": req.password,
        })

        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Get caregiver profile
        caregiver = db.table("caregivers")\
            .select("*")\
            .eq("auth_id", auth_response.user.id)\
            .limit(1)\
            .execute()

        return {
            "status":    "ok",
            "session":   auth_response.session.model_dump() if auth_response.session else None,
            "caregiver": caregiver.data[0] if caregiver.data else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/caregiver/logout")
async def caregiver_logout(authorization: str = Header(None)):
    """Sign out caregiver."""
    db = get_supabase_auth()
    try:
        db.auth.sign_out()
        return {"status": "ok"}
    except Exception:
        return {"status": "ok"}  # Always return ok on logout


@router.post("/caregiver/reset-request")
async def reset_request(req: ResetRequest):
    """Send password reset OTP to caregiver email."""
    db = get_supabase_auth()
    try:
        db.auth.reset_password_email(req.email.lower().strip())
        return {
            "status":  "ok",
            "message": "Reset code sent to your email",
        }
    except Exception as e:
        # Always return ok to prevent email enumeration
        return {"status": "ok", "message": "If this email exists, a reset code was sent"}


@router.post("/caregiver/reset-confirm")
async def reset_confirm(req: ResetConfirm):
    """Confirm password reset with OTP."""
    db = get_supabase_auth()
    try:
        # Verify OTP and update password
        response = db.auth.verify_otp({
            "email": req.email.lower().strip(),
            "token": req.otp,
            "type":  "recovery",
        })

        if not response.user:
            raise HTTPException(status_code=400, detail="Invalid or expired code")

        # Update password
        db.auth.update_user({"password": req.new_password})

        return {"status": "ok", "message": "Password updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired code")


@router.get("/caregiver/me")
async def get_caregiver_me(authorization: str = Header(None)):
    """
    Get current caregiver profile from JWT token.
    Frontend sends: Authorization: Bearer <access_token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.replace("Bearer ", "")
    db    = get_supabase_auth()

    try:
        user = db.auth.get_user(token)
        if not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        caregiver = db.table("caregivers")\
            .select("*, care_relationships(*, user_profile(*))")\
            .eq("auth_id", user.user.id)\
            .limit(1)\
            .execute()

        return {
            "status":    "ok",
            "caregiver": caregiver.data[0] if caregiver.data else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Elderly user auth (phone OTP) ──────────────────────────────────────────────

@router.post("/user/otp-request")
async def user_otp_request(req: OTPRequest):
    """
    Send OTP to elderly user's phone number.
    user_id will be their phone number.
    """
    db = get_supabase_auth()

    # Normalize phone number
    phone = req.phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    try:
        db.auth.sign_in_with_otp({"phone": phone})
        return {
            "status":  "ok",
            "message": "OTP sent",
            "phone":   phone,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/user/otp-verify")
async def user_otp_verify(req: OTPVerify):
    """
    Verify OTP and create/get user profile.
    user_id = phone number.
    """
    db = get_supabase_auth()

    phone = req.phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    try:
        response = db.auth.verify_otp({
            "phone": phone,
            "token": req.token,
            "type":  "sms",
        })

        if not response.user:
            raise HTTPException(status_code=400, detail="Invalid OTP")

        # Ensure user_profile exists
        existing = db.table("user_profile")\
            .select("user_id")\
            .eq("user_id", phone)\
            .execute()

        if not existing.data:
            db.table("user_profile").insert({
                "user_id": phone,
                "phone":   phone,
            }).execute()
            print(f"[Auth] Created user_profile for {phone}")

        return {
            "status":  "ok",
            "user_id": phone,
            "session": response.session.model_dump() if response.session else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
