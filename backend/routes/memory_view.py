from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone

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


@router.get("/memory/{user_id}", response_class=HTMLResponse)
def memory_view(user_id: str):
    from supabase_store import get_client
    from memory.interest_scores import get_interest_scores
    db = get_client()

    clusters = (db.table("interest_clusters").select("*")
                .eq("user_id", user_id).order("strength", desc=True).execute()).data or []
    enjoys    = get_interest_scores(user_id, mode="enjoy")
    attention = get_interest_scores(user_id, mode="attention")

    by_pillar = {}
    for cl in clusters:
        by_pillar.setdefault(cl.get("pillar") or "GENERAL", []).append(cl)

    blocks = []
    for pillar, cls in by_pillar.items():
        blocks.append('<div class="pillar"><h2>' + pillar.replace("_", " ").title() + '</h2>')
        for cl in cls:
            evs = (db.table("user_behavioral_events")
                   .select("surface_form,event_type,sentiment,created_at")
                   .eq("cluster_id", cl["id"]).order("created_at", desc=False).execute()).data or []
            status = cl.get("status", "active")
            blocks.append('<div class="concern"><div class="chead">'
                          '<span class="label">' + str(cl.get("label")) + '</span>'
                          '<span class="badge ' + status + '">' + status + '</span>'
                          '<span class="meta">' + str(cl.get("event_count")) + ' events · last '
                          + _ago(cl.get("last_event")) + '</span></div><div class="timeline">')
            for e in evs:
                s = e.get("sentiment")
                klass = "pos" if (s or 0) > 0.6 else ("neg" if (s is not None and s < 0.5) else "neu")
                blocks.append('<div class="event"><span class="dot ' + klass + '"></span>'
                              '<span class="ev-what">' + str(e.get("event_type", "")) + '</span>'
                              '<span class="ev-said">"' + str(e.get("surface_form", "")) + '"</span>'
                              '<span class="ev-when">' + _ago(e.get("created_at")) + '</span></div>')
            blocks.append('</div></div>')
        blocks.append('</div>')

    def rows_enjoy(items):
        return "".join(
            '<tr><td>' + str(i["entity"]) + '</td><td>' + i["pillar"].replace("_", " ").title()
            + '</td><td class="' + ("pos" if i["score"] > 0 else "neg") + '">'
            + format(i["score"], "+.2f") + '</td><td>' + str(i["mentions"]) + '</td></tr>'
            for i in items[:12])

    def rows_attn(items):
        return "".join(
            '<tr><td>' + str(i["entity"]) + '</td><td>' + i["pillar"].replace("_", " ").title()
            + '</td><td class="attn">' + format(i["attention"], ".2f") + '</td><td>'
            + str(i["mentions"]) + '</td></tr>'
            for i in items[:12])

    enjoy_rows = rows_enjoy(enjoys)
    attn_rows  = rows_attn(attention)

    body = "".join(blocks) or '<p style="color:#999">No concerns yet.</p>'
    return (_PAGE.replace("{{USER}}", user_id).replace("{{N}}", str(len(clusters)))
                 .replace("{{BODY}}", body)
                 .replace("{{ENJOY}}", enjoy_rows)
                 .replace("{{ATTN}}", attn_rows))


_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Nancy memory</title><style>
body{font-family:-apple-system,system-ui,sans-serif;background:#f6f5f1;color:#2c2c2a;margin:0;padding:32px;line-height:1.5}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{color:#888;margin-bottom:28px}
.cols{display:flex;gap:32px;align-items:flex-start;flex-wrap:wrap}
.main{flex:2;min-width:420px}.side{flex:1;min-width:280px}
.pillar{margin-bottom:24px}
.pillar h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#999;font-weight:600;margin:0 0 10px}
.concern{background:#fff;border:1px solid #e5e3dc;border-radius:12px;padding:14px 16px;margin-bottom:12px}
.chead{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.label{font-weight:600;font-size:16px}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;background:#eee;color:#666;text-transform:uppercase}
.badge.active{background:#e1f0e6;color:#1d7a4d}
.meta{margin-left:auto;color:#999;font-size:12px}
.timeline{border-left:2px solid #eee;padding-left:14px;margin-left:4px}
.event{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%;flex:none;margin-left:-19px;background:#bbb;border:2px solid #f6f5f1}
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
<h1>What Nancy remembers</h1><div class="sub">{{USER}} · {{N}} concerns tracked</div>
<div class="cols"><div class="main">{{BODY}}</div>
<div class="side">
<h2>What she enjoys</h2>
<table><tr><th>Thing</th><th>Pillar</th><th>Score</th><th>x</th></tr>{{ENJOY}}</table>
<p class="note">Higher = enjoys more · Nancy draws on these</p>
<h2 style="margin-top:28px">Needs attention</h2>
<table><tr><th>Concern</th><th>Pillar</th><th>Weight</th><th>x</th></tr>{{ATTN}}</table>
<p class="note">Ranked by how much it matters — a trigger for Nancy to act, not to recommend</p>
</div></div></body></html>"""
