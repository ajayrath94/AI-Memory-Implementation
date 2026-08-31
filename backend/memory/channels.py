"""
CHANNELS — getting an alert to a caregiver, by whatever route suits its weight.

One seam, three channels, so adding the next one is a function and a key rather
than surgery on the alert engine.

WHAT EACH CHANNEL CAN CARRY

  email     Everything. Model-written, personal, quotes what she actually said,
            and framed for who is reading it — a daughter abroad needs "she may
            need a call", a son downstairs needs "worth looking in on her".

  whatsapp  A fixed template. Meta approves the wording in advance and only
            variable slots may be filled, so nothing here can be generated.
  sms       The same, via DLT. TRAI approves the text; a model cannot write it.

That constraint turns out to be right rather than merely tolerable. Neither
channel is private — a WhatsApp preview appears on a lock screen, an SMS sits
in a thread anyone might read — so health information about someone's mother
does not belong in either. They carry a nudge; the email carries the substance.

WHICH CHANNEL, BY SEVERITY

  low / medium   email
  high           email + whatsapp
  acute          email + whatsapp + sms

Rising urgency buys a more intrusive channel, and SMS is reserved for the case
where data might be unavailable — a text arrives on a 2G signal in a village
where WhatsApp will not.

A caregiver may switch a channel off entirely. Severity chooses; she consents.

QUIET HOURS
Nothing below acute wakes anyone between 22:00 and 07:00. A text at 2am about a
mood decline, to a daughter three cities away who can do nothing until morning,
is cruel rather than useful — it holds the alert until breakfast instead.
"""
import os
import json
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

# Which channels each level earns.
BY_SEVERITY = {
    "low":      ["email"],
    "medium":   ["email"],
    "high":     ["email", "whatsapp"],
    "critical": ["email", "whatsapp", "sms"],
    "acute":    ["email", "whatsapp", "sms"],
}

QUIET_START, QUIET_END = 22, 7


def _in_quiet_hours(tz_name: str = "Asia/Kolkata") -> bool:
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        return False
    return h >= QUIET_START or h < QUIET_END


def _post(url: str, payload: dict, headers: dict, timeout: int = 20) -> bool:
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={**headers, "Content-Type": "application/json",
                     # Several of these providers sit behind Cloudflare, which
                     # 403s urllib's default user agent with error 1010.
                     "User-Agent": "NancyAI/1.0"},
            method="POST")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
        print(f"[Channels] POST {url.split('/')[2]} failed: {e} {body}")
        return False


# ── whatsapp ──────────────────────────────────────────────────────────────────

def send_whatsapp(to_phone: str, user_name: str, bot_name: str = "Nancy") -> bool:
    """A fixed approved template with the name filled in.

    Deliberately says nothing about what was noticed. The preview appears on a
    lock screen, and whose knee hurts is not for whoever glances at it.
    """
    key = os.getenv("MSG91_AUTH_KEY")
    template = os.getenv("MSG91_WHATSAPP_TEMPLATE")
    number = os.getenv("MSG91_WHATSAPP_NUMBER")
    if not (key and template and number):
        # Not configured is not a failure. It should read differently on a
        # dashboard from "tried and the provider rejected it".
        return None
    if not to_phone:
        return False

    return _post(
        "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/",
        {
            "integrated_number": number,
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": "en", "policy": "deterministic"},
                    "to_and_components": [{
                        "to": [to_phone],
                        "components": {"body_1": {"type": "text", "value": user_name}},
                    }],
                },
            },
        },
        {"authkey": key})


# ── sms ───────────────────────────────────────────────────────────────────────

def send_sms(to_phone: str, user_name: str) -> bool:
    """Acute only. A text reaches a phone with no data, which is the whole
    reason to keep it — and the reason it must stay content-free."""
    key = os.getenv("MSG91_AUTH_KEY")
    template = os.getenv("MSG91_SMS_TEMPLATE_ID")
    sender = os.getenv("MSG91_SENDER_ID")
    if not (key and template and sender):
        # Not configured is not a failure. It should read differently on a
        # dashboard from "tried and the provider rejected it".
        return None
    if not to_phone:
        return False

    phone = to_phone if to_phone.startswith("91") else f"91{to_phone.lstrip('+')}"
    return _post(
        "https://control.msg91.com/api/v5/flow/",
        {"template_id": template, "sender": sender,
         "recipients": [{"mobiles": phone, "name": user_name}]},
        {"authkey": key})


# ── the seam ──────────────────────────────────────────────────────────────────

def deliver(alert: dict, relationship: dict, user_name: str,
            email_fn=None, tz: str = "Asia/Kolkata") -> Dict:
    """Send one alert by every channel its severity earns and the caregiver allows.

    email_fn is passed in rather than imported so this module does not depend on
    the alert engine that calls it.
    """
    severity = (alert.get("severity") or "medium").lower()
    wanted = BY_SEVERITY.get(severity, ["email"])
    sent, skipped = [], []

    # Below acute, nothing intrudes at night. The email still goes — it waits in
    # an inbox, which is what an inbox is for.
    if severity not in ("critical", "acute") and _in_quiet_hours(tz):
        wanted = [c for c in wanted if c == "email"]
        skipped.append("quiet_hours")

    for channel in wanted:
        # Severity chooses the channel; the caregiver consents to it.
        if relationship.get(f"allow_{channel}") is False:
            skipped.append(f"{channel}_off")
            continue

        if channel == "email":
            to = relationship.get("alert_email")
            if to and email_fn and email_fn(to):
                sent.append("email")
            elif not to:
                skipped.append("no_email")
        elif channel in ("whatsapp", "sms"):
            fn = send_whatsapp if channel == "whatsapp" else send_sms
            got = fn(relationship.get("alert_phone") or "", user_name)
            if got:
                sent.append(channel)
            else:
                skipped.append(f"{channel}_" +
                               ("unconfigured" if got is None else "failed"))

    print(f"[Channels] {severity} alert -> sent {sent or 'nothing'}"
          + (f", skipped {skipped}" if skipped else ""))
    return {"sent": sent, "skipped": skipped}
