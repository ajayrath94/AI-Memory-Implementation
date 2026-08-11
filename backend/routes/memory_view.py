from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
import html as _html

router = APIRouter()


def _ago(ts):
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        d = (datetime.now(timezone.utc) - dt).days
        return "today" if d == 0 else f"{d}d ago"
    except Exception:
        return ""


def _esc(x):
    return _html.escape(str(x)) if x is not None else ""


@router.get("/memory/{user_id}", response_class=HTMLResponse)
def memory_view(user_id: str):
    from supabase_store import get_client
    from memory.interest_scores import get_interest_scores
    db = get_client()

    um = (db.table("user_memory").select("*")
          .eq("user_id", user_id).limit(1).execute()).data
    um = um[0] if um else {}
    summary       = um.get("summary") or ""
    key_facts     = um.get("key_facts") or []
    if isinstance(key_facts, str):
        try:
            import json as _j; key_facts = _j.loads(key_facts)
        except Exception:
            key_facts = [key_facts]
    session_count = um.get("session_count", 0)

    sessions = (db.table("sessions").select("id,summary,created_at,updated_at")
                .eq("user_id", user_id).order("created_at", desc=True).execute()).data or []
    sess_ids = [s["id"] for s in sessions]

    stm_n = 0
    for sid in sess_ids:
        try:
            stm_n += (db.table("stm_clusters").select("id", count="exact")
                      .eq("session_id", sid).execute()).count or 0
        except Exception:
            pass
    ltm_n = 0
    try:
        ltm_n = (db.table("ltm_patterns").select("id", count="exact")
                 .eq("user_id", user_id).execute()).count or 0
    except Exception:
        pass

    clusters = (db.table("interest_clusters").select("*")
                .eq("user_id", user_id).order("strength", desc=True).execute()).data or []
    enjoys    = get_interest_scores(user_id, mode="enjoy")
    attention = get_interest_scores(user_id, mode="attention")

    facts_html = "".join('<span class="chip">' + _esc(f) + '</span>' for f in key_facts) \
                 or '<span class="empty">no facts yet</span>'

    sess_html = ""
    for s in sessions:
        summ = s.get("summary")
        sess_html += ('<div class="sess"><div class="sess-when">' + _ago(s.get("created_at")) +
                      '</div><div class="sess-sum">' +
                      (_esc(summ) if summ else '<span class="empty">not summarized yet</span>') +
                      '</div></div>')
    if not sess_html:
        sess_html = '<span class="empty">no sessions</span>'

    track1 = (
        '<div class="t1">'
        '<div class="summary-card"><div class="sec-label">Compounded summary</div>'
        '<div class="summary">' + (_esc(summary) if summary else '<span class="empty">no summary yet — needs a completed session</span>') + '</div></div>'
        '<div class="sec-label">Key facts</div><div class="chips">' + facts_html + '</div>'
        '<div class="sec-label">Sessions (' + str(len(sessions)) + ')</div><div class="sessions">' + sess_html + '</div>'
        '</div>'
    )

    tiers = (
        '<div class="tiers">'
        '<div class="tier"><div class="tn">Cache</div><div class="tv">~</div><div class="td">raw · fast decay</div></div>'
        '<div class="arrow">&rarr;</div>'
        '<div class="tier"><div class="tn">STM</div><div class="tv">' + str(stm_n) + '</div><div class="td">fused · 7d</div></div>'
        '<div class="arrow">&rarr;</div>'
        '<div class="tier"><div class="tn">LTM</div><div class="tv">' + str(ltm_n) + '</div><div class="td">distilled · promote@3</div></div>'
        '<div class="arrow">&rarr;</div>'
        '<div class="tier narrative"><div class="tn">Summary</div><div class="tv">' + ('yes' if summary else 'no') + '</div><div class="td">permanent narrative</div></div>'
        '</div>'
    )

    by_pillar = {}
    for cl in clusters:
        by_pillar.setdefault(cl.get("pillar") or "GENERAL", []).append(cl)

    blocks = []
    max_str = max([c.get("strength", 0) or 0 for c in clusters], default=1) or 1
    for pillar, cls in by_pillar.items():
        blocks.append('<div class="pillar"><h2>' + pillar.replace("_", " ").title() + '</h2>')
        for cl in cls:
            evs = (db.table("user_behavioral_events")
                   .select("surface_form,event_type,sentiment,created_at")
                   .eq("cluster_id", cl["id"]).order("created_at", desc=False).execute()).data or []
            status = cl.get("status", "active")
            strength = cl.get("strength", 0) or 0
            pct = int(100 * strength / max_str)
            trend = cl.get("trend")
            trend_html = ""
            if trend == "improving":
                trend_html = '<span class="trend up">&uarr; improving</span>'
            elif trend == "worsening":
                trend_html = '<span class="trend down">&darr; worsening</span>'
            blocks.append('<div class="concern"><div class="chead">'
                          '<span class="label">' + _esc(cl.get("label")) + '</span>' + trend_html +
                          '<span class="badge ' + status + '">' + status + '</span>'
                          '<span class="meta">' + str(cl.get("event_count")) + ' events · last '
                          + _ago(cl.get("last_event")) + '</span></div>'
                          '<div class="strbar"><div class="strfill" style="width:' + str(pct) + '%"></div></div>'
                          '<div class="strval">strength ' + format(strength, ".2f") + '</div><div class="timeline">')
            for e in evs:
                s = e.get("sentiment")
                klass = "pos" if (s or 0) > 0.6 else ("neg" if (s is not None and s < 0.5) else "neu")
                blocks.append('<div class="event"><span class="dot ' + klass + '"></span>'
                              '<span class="ev-what">' + _esc(e.get("event_type", "")) + '</span>'
                              '<span class="ev-said">"' + _esc(e.get("surface_form", "")) + '"</span>'
                              '<span class="ev-when">' + _ago(e.get("created_at")) + '</span></div>')
            blocks.append('</div></div>')
        blocks.append('</div>')

    def rows_enjoy(items):
        return "".join(
            '<tr><td>' + _esc(i["entity"]) + '</td><td>' + i["pillar"].replace("_", " ").title()
            + '</td><td class="' + ("pos" if i["score"] > 0 else "neg") + '">'
            + format(i["score"], "+.2f") + '</td><td>' + str(i["mentions"]) + '</td></tr>'
            for i in items[:12])

    def rows_attn(items):
        return "".join(
            '<tr><td>' + _esc(i["entity"]) + '</td><td>' + i["pillar"].replace("_", " ").title()
            + '</td><td class="attn">' + format(i["attention"], ".2f") + '</td><td>'
            + str(i["mentions"]) + '</td></tr>'
            for i in items[:12])

    enjoy_rows = rows_enjoy(enjoys)
    attn_rows  = rows_attn(attention)
    body = "".join(blocks) or '<p style="color:#999">No facts yet.</p>'

    return (_PAGE.replace("{{USER}}", _esc(user_id))
                 .replace("{{N}}", str(len(clusters)))
                 .replace("{{SC}}", str(session_count))
                 .replace("{{TRACK1}}", track1)
                 .replace("{{TIERS}}", tiers)
                 .replace("{{BODY}}", body)
                 .replace("{{ENJOY}}", enjoy_rows)
                 .replace("{{ATTN}}", attn_rows))


_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Nancy memory</title><style>
body{font-family:-apple-system,system-ui,sans-serif;background:#f6f5f1;color:#2c2c2a;margin:0;padding:32px;line-height:1.5}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{color:#888;margin-bottom:24px}
.sec-label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#999;font-weight:600;margin:18px 0 8px}
.t1{background:#fff;border:1px solid #e5e3dc;border-radius:14px;padding:20px 22px;margin-bottom:24px}
.summary-card .summary{font-size:15px;line-height:1.65;color:#33322f}
.empty{color:#bbb;font-style:italic}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:#eef3ee;color:#2c5a3d;border:1px solid #d6e5da;border-radius:20px;padding:4px 12px;font-size:13px}
.sessions{display:flex;flex-direction:column;gap:8px}
.sess{display:flex;gap:14px;padding:8px 0;border-bottom:1px solid #f0efe9}
.sess-when{color:#aaa;font-size:12px;min-width:70px;flex:none}
.sess-sum{font-size:13px;color:#555}
.tiers{display:flex;align-items:center;gap:6px;margin-bottom:26px;flex-wrap:wrap}
.tier{background:#fff;border:1px solid #e5e3dc;border-radius:10px;padding:10px 16px;text-align:center;min-width:92px}
.tier.narrative{background:#f2ede4;border-color:#e0d6c4}
.tn{font-size:11px;text-transform:uppercase;color:#999;letter-spacing:.05em;font-weight:600}
.tv{font-size:22px;font-weight:600;color:#2c2c2a;margin:2px 0}
.td{font-size:10px;color:#aaa}
.arrow{color:#ccc;font-size:18px}
.cols{display:flex;gap:32px;align-items:flex-start;flex-wrap:wrap}
.main{flex:2;min-width:420px}.side{flex:1;min-width:280px}
.pillar{margin-bottom:24px}
.pillar h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#999;font-weight:600;margin:0 0 10px}
.concern{background:#fff;border:1px solid #e5e3dc;border-radius:12px;padding:14px 16px;margin-bottom:12px}
.chead{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.label{font-weight:600;font-size:16px}
.trend{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.trend.up{background:#e1f0e6;color:#1d7a4d}.trend.down{background:#f6e2dc;color:#c0492a}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;background:#eee;color:#666;text-transform:uppercase}
.badge.active{background:#e1f0e6;color:#1d7a4d}
.meta{margin-left:auto;color:#999;font-size:12px}
.strbar{height:5px;background:#f0efe9;border-radius:3px;overflow:hidden;margin-bottom:3px}
.strfill{height:100%;background:#7ea885;border-radius:3px}
.strval{font-size:11px;color:#aaa;margin-bottom:8px}
.timeline{border-left:2px solid #eee;padding-left:14px;margin-left:4px}
.event{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%;flex:none;margin-left:-19px;background:#bbb;border:2px solid #fff}
.dot.pos{background:#3b9c5f}.dot.neg{background:#d05538}.dot.neu{background:#bbb}
.ev-what{color:#666;min-width:70px}.ev-said{color:#2c2c2a}.ev-when{margin-left:auto;color:#aaa;font-size:12px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e3dc;border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;font-size:13px;border-bottom:1px solid #f0efe9}
th{background:#faf9f5;color:#999;font-size:11px;text-transform:uppercase}
td.pos{color:#1d7a4d;font-weight:600}td.neg{color:#c0492a;font-weight:600}
.attn{color:#7a5a1d;font-weight:600}
.note{color:#aaa;font-size:12px;margin-top:8px}
.side h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#999;font-weight:600;margin:0 0 10px}
</style></head><body>
<h1>What Nancy remembers</h1><div class="sub">{{USER}} · {{SC}} sessions · {{N}} facts tracked</div>
{{TIERS}}
{{TRACK1}}
<div class="cols"><div class="main">{{BODY}}</div>
<div class="side">
<h2>What she enjoys</h2>
<table><tr><th>Thing</th><th>Pillar</th><th>Score</th><th>x</th></tr>{{ENJOY}}</table>
<p class="note">Higher = enjoys more · Nancy draws on these</p>
<h2 style="margin-top:28px">Needs attention</h2>
<table><tr><th>Concern</th><th>Pillar</th><th>Weight</th><th>x</th></tr>{{ATTN}}</table>
<p class="note">Ranked by how much it matters</p>
</div></div></body></html>"""
