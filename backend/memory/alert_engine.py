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

_MODEL = "claude-haiku-4-5-20251001"


def detect_decline_pattern(user_id: str, db) -> List[dict]:
    """Hybrid decline detection over a 7-day window — the early-warning brain.

    RULES pre-filter (cheap, no LLM): tally soft_flags + valence across recent
    sessions. Soft signals (fatigue, withdrawal, ...) matter only as PATTERNS —
    a one-off "tired" is nothing; the same flag across several sessions, or
    several flags clustering, or a sustained low mood, is a candidate.

    LLM confirms (only on candidates): judges whether the pattern is genuinely
    concerning + writes the caregiver message. This is what stops the "grandma
    said she's tired once → email family" false positive while still catching
    real early decline.

    ACUTE sessions bypass everything → immediate critical alert.
    """
    from collections import Counter
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=7)).isoformat()
    try:
        sessions = (db.table("sessions")
                    .select("valence,soft_flags,acute,created_at,summary")
                    .eq("user_id", user_id).gte("created_at", since)
                    .order("created_at", desc=True).limit(20).execute()).data or []
    except Exception as e:
        print(f"[AlertEngine] decline query failed: {e}")
        return []
    if not sessions:
        return []

    alerts = []

    # ── ACUTE — any acute session in the window → immediate critical ────────────
    if any(s.get("acute") for s in sessions):
        return [{
            "alert_type": "emergency", "severity": "critical",
            "message": "An acute concern was detected in a recent conversation. Please check on them right away.",
            "pillar": "HEALTH_WELLNESS",
        }]

    # ── RULES pre-filter — is there a candidate pattern worth the LLM? ──────────
    flag_counter = Counter()
    for s in sessions:
        for f in (s.get("soft_flags") or []):
            flag_counter[f] += 1
    vals = [float(s["valence"]) for s in sessions if s.get("valence") is not None]
    avg_valence = sum(vals) / len(vals) if vals else 0.0

    persistent = any(ct >= 3 for ct in flag_counter.values())        # same flag in 3+ sessions
    clustered  = len([f for f, ct in flag_counter.items() if ct >= 2]) >= 2  # 2+ flags recurring
    low_mood   = avg_valence <= -0.3 and len(vals) >= 2              # sustained low

    if not (persistent or clustered or low_mood):
        return []   # no candidate → no LLM call, no alert

    # ── LLM confirm — is this genuinely a concerning decline pattern? ──────────
    flag_summary = ", ".join(f"{f}×{ct}" for f, ct in flag_counter.most_common()) or "none"
    val_summary = ", ".join(
        f"{float(s['valence']):+.1f}" for s in reversed(sessions) if s.get("valence") is not None
    ) or "n/a"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = f"""You watch over an elderly person's wellbeing for their family.

Over the last 7 days ({len(sessions)} conversations), these early-warning signals
appeared:
  soft signals (state × how many sessions): {flag_summary}
  mood trajectory (oldest→newest valence, -1 low .. +1 good): {val_summary}

Is this a CONCERNING pattern of decline a caregiver should be told about — e.g.
persistent fatigue, growing withdrawal or loneliness, a steady mood drop, several
signals clustering? Or is it normal ups-and-downs not worth alarming family over?

A single bad day is NOT concerning. Persistence or a worsening trend IS.

Return ONLY JSON:
{{"concerning": <true/false>, "severity": "low"|"medium"|"high", "message": "one warm, specific sentence for the caregiver about what you're noticing and a gentle suggestion"}}
No prose, only JSON."""
        resp = client.messages.create(model=_MODEL, max_tokens=200,
                                      messages=[{"role": "user", "content": prompt}])
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].replace("json", "", 1).strip()
        d = json.loads(raw)
        if d.get("concerning"):
            alerts.append({
                "alert_type": "sadness",
                "severity": d.get("severity", "medium"),
                "message": d.get("message") or "A pattern of declining wellbeing has been noticed. A check-in may help.",
                "pillar": "SADNESS",
            })
    except Exception as e:
        print(f"[AlertEngine] decline LLM confirm failed: {e}")
        # fail toward informing: if we had a candidate but the LLM broke, raise a soft flag
        if persistent or low_mood:
            alerts.append({
                "alert_type": "sadness", "severity": "medium",
                "message": "Recent conversations suggest a possible dip in wellbeing. A check-in may help.",
                "pillar": "SADNESS",
            })
    return alerts


def detect_alerts(user_id: str) -> List[dict]:
    """
    Detect caregiver-alert conditions from signals that actually work:
      1. ACUTE + soft-decline PATTERNS (detect_decline_pattern, 7-day hybrid)
      2. A single strongly-negative session (immediate distress)
    Eldercare errs toward informing early; 24h dedup prevents spam. Soft signals
    (tired, withdrawn) alert only as PATTERNS, never one-offs.
    """
    from memory.profile_store import get_user_profile
    from supabase_store import get_client
    profile = get_user_profile(user_id) or {}
    db = get_client()

    conditions = (profile.get("health", {}) or {}).get("conditions", []) or []
    living     = ((profile.get("life_context", {}) or {}).get("living_situation") or "").lower()
    lonely     = "alone" in living

    try:
        from memory.pillar_weights import get_pillar_weights
        weights = get_pillar_weights(user_id)
    except Exception:
        weights = {}
    def weighted_ok(pillar):
        return weights.get(pillar, 1.0) >= 0.5

    alerts = []

    # 1. Acute + soft-decline patterns (the early-warning brain)
    alerts += detect_decline_pattern(user_id, db)

    # 2. A single strongly-negative recent session → immediate distress signal
    try:
        recent = (db.table("sessions").select("valence,created_at")
                  .eq("user_id", user_id).not_.is_("valence", "null")
                  .order("created_at", desc=True).limit(3).execute()).data or []
    except Exception:
        recent = []
    vals = [float(s["valence"]) for s in recent if s.get("valence") is not None]
    if vals:
        latest = vals[0]
        if weighted_ok("STRESS") and latest <= -0.8 and not any(a["severity"] == "critical" for a in alerts):
            alerts.append({
                "alert_type": "emergency", "severity": "critical",
                "message": f"A recent conversation showed significant emotional distress. Please reach out soon.{(' Noted conditions: ' + ', '.join(conditions[:2])) if conditions else ''}",
                "pillar": "STRESS",
            })
        elif weighted_ok("SADNESS") and latest <= -0.6 and not any(a["alert_type"] in ("sadness", "emergency") for a in alerts):
            alerts.append({
                "alert_type": "sadness", "severity": "high" if lonely else "medium",
                "message": f"A recent conversation showed low mood{' — and they appear to live alone' if lonely else ''}. Emotional support or a call from family may help.",
                "pillar": "SADNESS",
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
