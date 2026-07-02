"""
ALERT ENGINE
Detects stress/health/sadness/emergency patterns from memory + trends
and notifies caregivers via email.

Alert types:
  health     — HEALTH_WELLNESS rising + condition in profile
  stress     — STRESS rising for 2+ sessions
  sadness    — SADNESS HIGH + lives alone
  emergency  — FEAR HIGH + health concern + no recent contact

Triggered:
  1. After every session end (process_session_end)
  2. On demand via POST /alerts/check/{user_id}

Delivery:
  Phase 1 — Email via SendGrid (today)
  Phase 2 — Push notification via FCM (later)
  Phase 3 — Voice call via Twilio (later)
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional


# ── Alert detection ────────────────────────────────────────────────────────────

def detect_alerts(user_id: str) -> List[dict]:
    """
    Scan memory + profile for alert conditions.
    Returns list of alert dicts ready to send.
    """
    from memory.user_memory_store import get_user_memory
    from memory.profile_store import get_user_profile

    memory  = get_user_memory(user_id) or {}
    profile = get_user_profile(user_id) or {}

    alerts  = []
    trend   = memory.get("pillar_trend", {})
    pillar_trends = trend.get("pillar_trends", {}) if isinstance(trend, dict) else {}
    trend_alerts  = trend.get("alerts", []) if isinstance(trend, dict) else []

    health    = profile.get("health", {})
    conditions = health.get("conditions", [])
    concerns   = health.get("concerns", [])
    family     = profile.get("family", {})
    life       = profile.get("life_context", {})
    living     = life.get("living_situation", "")
    personality = profile.get("personality", {})
    emotion_state = personality.get("emotional_state", "")

    # Apply pillar weights to alert sensitivity
    try:
        from memory.pillar_weights import get_pillar_weights
        weights = get_pillar_weights(user_id)
    except Exception:
        weights = {}

    def is_alert_active(pillar, base_condition):
        """Check if alert should fire considering user weights."""
        w = weights.get(pillar, 1.0)
        if w < 0.5:
            return False  # User explicitly de-prioritized this pillar
        return base_condition

    # ── HEALTH alert ──────────────────────────────────────────────────────────
    if is_alert_active("HEALTH_WELLNESS", pillar_trends.get("HEALTH_WELLNESS") == "rising" and conditions):
        alerts.append({
            "alert_type": "health",
            "severity":   "high",
            "message":    f"Health concerns increasing across recent sessions. Reported: {', '.join(conditions[:3])}. Consider checking in or scheduling a doctor visit.",
            "pillar":     "HEALTH_WELLNESS",
        })

    # ── STRESS alert ──────────────────────────────────────────────────────────
    if is_alert_active("STRESS", pillar_trends.get("STRESS") == "rising"):
        alerts.append({
            "alert_type": "stress",
            "severity":   "medium",
            "message":    f"Stress levels rising across recent sessions. Emotional state: {emotion_state or 'elevated'}. A call from family might help.",
            "pillar":     "STRESS",
        })

    # ── SADNESS alert ─────────────────────────────────────────────────────────
    if is_alert_active("SADNESS", pillar_trends.get("SADNESS") == "rising"):
        lonely = "lives alone" in living.lower() if living else False
        severity = "high" if lonely else "medium"
        alerts.append({
            "alert_type": "sadness",
            "severity":   severity,
            "message":    f"Sadness increasing across sessions{' — user appears to live alone' if lonely else ''}. Emotional support recommended.",
            "pillar":     "SADNESS",
        })

    # ── EMERGENCY alert ───────────────────────────────────────────────────────
    if any("distress" in a.lower() or "3 consecutive" in a.lower() for a in trend_alerts):
        alerts.append({
            "alert_type": "emergency",
            "severity":   "critical",
            "message":    f"Repeated emotional distress detected across 3+ consecutive sessions. Immediate family contact recommended. Conditions: {', '.join(conditions[:2]) if conditions else 'unknown'}.",
            "pillar":     "STRESS",
        })

    # ── Consecutive session check from trend alerts ────────────────────────────
    for ta in trend_alerts:
        if "health" in ta.lower() and "consecutive" in ta.lower():
            if not any(a["alert_type"] == "health" for a in alerts):
                alerts.append({
                    "alert_type": "health",
                    "severity":   "medium",
                    "message":    ta,
                    "pillar":     "HEALTH_WELLNESS",
                })

    return alerts


# ── Caregiver lookup ───────────────────────────────────────────────────────────

def get_caregivers_for_user(user_id: str) -> List[dict]:
    """Get all active caregivers linked to this user."""
    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("care_relationships")\
            .select("*, caregivers(*)")\
            .eq("user_id", user_id)\
            .eq("active", True)\
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[AlertEngine] Failed to get caregivers: {e}")
        return []


def should_notify(relationship: dict, alert_type: str) -> bool:
    """Check if this caregiver wants this alert type."""
    mapping = {
        "health":    "notify_health",
        "stress":    "notify_stress",
        "sadness":   "notify_sadness",
        "emergency": "notify_emergency",
    }
    field = mapping.get(alert_type, "notify_health")
    return relationship.get(field, True)


def was_recently_notified(user_id: str, alert_type: str, hours: int = 24) -> bool:
    """Prevent duplicate alerts within X hours."""
    try:
        from supabase_store import get_client
        db        = get_client()
        cutoff    = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        result    = db.table("care_alerts")\
            .select("id")\
            .eq("user_id", user_id)\
            .eq("alert_type", alert_type)\
            .gte("sent_at", cutoff)\
            .limit(1)\
            .execute()
        return bool(result.data)
    except Exception:
        return False


# ── Email delivery via SendGrid ────────────────────────────────────────────────

def send_email_alert(
    to_email: str,
    caregiver_name: str,
    user_name: str,
    alerts: list,
) -> bool:
    """Send ONE consolidated email covering all alerts via SendGrid."""
    api_key = os.getenv("SENDGRID_API_KEY")

    # Highest severity across all alerts determines subject emoji + color
    severity_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    top_alert     = max(alerts, key=lambda a: severity_rank.get(a["severity"], 0))

    if not api_key:
        print("[AlertEngine] No SENDGRID_API_KEY — logging alert instead")
        print(f"  TO: {to_email}")
        for a in alerts:
            print(f"  ALERT: {a['alert_type']} ({a['severity']}) — {a['message']}")
        return True

    severity_emoji = {
        "critical": "🚨",
        "high":     "⚠️",
        "medium":   "💛",
        "low":      "💙",
    }.get(top_alert["severity"], "ℹ️")

    subject = f"{severity_emoji} Nancy Alert: {user_name} needs attention"

    alert_blocks = ""
    for a in alerts:
        color = "#E24B4A" if a["severity"] in ("critical", "high") else "#BA7517"
        alert_blocks += f"""
        <div style="background:white;border-left:4px solid {color};
             padding:16px;border-radius:4px;margin:12px 0">
          <p style="margin:0 0 6px;color:#999;font-size:11px;text-transform:uppercase;letter-spacing:0.05em">
            {a['alert_type']} · {a['severity']}
          </p>
          <p style="margin:0;color:#333;font-size:15px">{a['message']}</p>
        </div>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:24px;border-radius:12px 12px 0 0">
        <h1 style="color:white;margin:0;font-size:22px">Nancy — Care Alert</h1>
        <p style="color:#aaa;margin:8px 0 0">Automated notification from Nancy AI</p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border-radius:0 0 12px 12px;border:1px solid #eee">
        <p style="color:#333">Hi <strong>{caregiver_name}</strong>,</p>
        <p style="color:#333">Nancy has detected the following about <strong>{user_name}</strong>:</p>
        {alert_blocks}
        <div style="background:#f0f0f0;padding:12px;border-radius:8px;margin:16px 0">
          <p style="margin:0;font-size:13px;color:#666">
            <strong>Detected:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
          </p>
        </div>
        <p style="color:#333">Consider reaching out to {user_name} today.</p>
        <p style="color:#888;font-size:12px;margin-top:24px">
          This alert was generated by Nancy AI based on conversation patterns.
          Nancy does not share conversation contents — only detected emotional and health signals.
        </p>
      </div>
    </div>
    """

    try:
        import urllib.request

        payload = json.dumps({
            "personalizations": [{"to": [{"email": to_email, "name": caregiver_name}]}],
            "from": {"email": os.getenv("SENDGRID_FROM_EMAIL", "nancy@nancyai.co"), "name": "Nancy AI"},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        }).encode()

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data    = payload,
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            method = "POST",
        )
        urllib.request.urlopen(req)
        print(f"[AlertEngine] Consolidated email sent to {to_email} ({len(alerts)} alerts)")
        return True

    except Exception as e:
        print(f"[AlertEngine] Email failed: {e}")
        return False


# ── Log alert to Supabase ──────────────────────────────────────────────────────

def log_alert(user_id: str, caregiver_id: str, alert: dict, sent: bool):
    try:
        from supabase_store import get_client
        db = get_client()
        db.table("care_alerts").insert({
            "user_id":      user_id,
            "caregiver_id": caregiver_id,
            "alert_type":   alert["alert_type"],
            "severity":     alert["severity"],
            "message":      alert["message"],
            "pillar":       alert.get("pillar", ""),
            "sent_via":     "email" if sent else "failed",
            "sent_at":      datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[AlertEngine] Failed to log alert: {e}")


# ── Main runner ────────────────────────────────────────────────────────────────

def run_alert_engine(user_id: str) -> dict:
    """
    Full alert cycle for a user.
    Called after session end + on demand.
    Returns summary of what was detected and sent.
    """
    print(f"[AlertEngine] Running for user: {user_id}")

    alerts       = detect_alerts(user_id)
    relationships = get_caregivers_for_user(user_id)

    if not alerts:
        print(f"[AlertEngine] No alerts for {user_id}")
        return {"alerts_detected": 0, "sent": 0}

    if not relationships:
        print(f"[AlertEngine] No caregivers linked to {user_id}")
        return {"alerts_detected": len(alerts), "sent": 0, "reason": "no_caregivers"}

    # Get user name from profile
    from memory.profile_store import get_user_profile
    profile   = get_user_profile(user_id) or {}
    user_name = profile.get("name") or user_id

    # Filter out alerts that were recently notified (24h cooldown)
    fresh_alerts = []
    for alert in alerts:
        if was_recently_notified(user_id, alert["alert_type"]):
            print(f"[AlertEngine] Skipping {alert['alert_type']} — notified within 24h")
            continue
        fresh_alerts.append(alert)

    if not fresh_alerts:
        print(f"[AlertEngine] All alerts on cooldown for {user_id}")
        return {"alerts_detected": len(alerts), "sent": 0, "reason": "cooldown"}

    sent_count = 0

    # Group: one consolidated email per caregiver, covering all their relevant alerts
    for rel in relationships:
        caregiver = rel.get("caregivers", {})
        if not caregiver:
            continue

        # Filter to alerts this caregiver actually wants
        caregiver_alerts = [a for a in fresh_alerts if should_notify(rel, a["alert_type"])]
        if not caregiver_alerts:
            continue

        email          = rel.get("alert_email") or caregiver.get("email")
        caregiver_name = caregiver.get("name", "Caregiver")
        caregiver_id   = caregiver.get("id")

        if not email:
            continue

        sent = send_email_alert(email, caregiver_name, user_name, caregiver_alerts)

        # Log each alert type individually for history, but only one email was sent
        for alert in caregiver_alerts:
            log_alert(user_id, caregiver_id, alert, sent)

        if sent:
            sent_count += 1
            try:
                from supabase_store import get_client
                get_client().table("user_profile").update({
                    "caregiver_notified_at": datetime.now(timezone.utc).isoformat()
                }).eq("user_id", user_id).execute()
            except Exception:
                pass

    print(f"[AlertEngine] Sent {sent_count} consolidated email(s) for {user_id}")
    return {
        "alerts_detected": len(alerts),
        "alerts":          [a["alert_type"] for a in fresh_alerts],
        "sent":            sent_count,
    }
