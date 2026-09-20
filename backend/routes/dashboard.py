"""
THE DASHBOARD — what the memory actually holds.

A developer tool, not a product feature. Seven stores with things moving
between them on seven, fourteen and thirty day rules, and until now the only
way to see any of it was a railway run python3 -c in a terminal. Half the bugs
this week were invisible until someone printed a table: four false alerts about
a cheerful woman, a Janmashtami line recalled twenty-eight times a fortnight
after the festival, the companion's own greetings stored as her memories.

    GET /dashboard/{user_id}          the page
    GET /dashboard/{user_id}/data     what it reads

One page, no build step, no auth beyond the API key the rest of the backend
uses. Read-only: the delete buttons can come once it is clear what gets
reached for.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import date, datetime, timezone, timedelta

router = APIRouter()


def _db():
    from supabase_store import get_client
    return get_client()


def _count(table: str, user_id: str) -> int:
    try:
        return len((_db().table(table).select("id")
                    .eq("user_id", user_id).limit(1000).execute()).data or [])
    except Exception:
        return -1


@router.get("/{user_id}/data")
def data(user_id: str):
    """Everything the page shows, in one call."""
    db = _db()
    out = {"user_id": user_id, "today": date.today().isoformat()}

    # ── the stores, and whether any is unexpectedly empty ────────────────
    out["stores"] = {t: _count(t, user_id) for t in (
        "memory_cache", "memory_stm", "memory_ltm", "subject_mentions",
        "interest_clusters", "entity_relations", "sessions",
        "stm_clusters", "ltm_patterns",
    )}

    # ── the thread, most recent first ────────────────────────────────────
    try:
        out["thread"] = (db.table("memory_stm")
                         .select("happened_on,text,tags,untagged,last_recalled")
                         .eq("user_id", user_id)
                         .order("happened_on", desc=True)
                         .limit(20).execute()).data or []
    except Exception as e:
        out["thread"] = [{"error": str(e)[:120]}]

    try:
        out["months"] = (db.table("memory_ltm").select("period,text,tags")
                         .eq("user_id", user_id)
                         .order("period", desc=True).limit(12).execute()).data or []
    except Exception:
        out["months"] = []

    # ── what it knows ────────────────────────────────────────────────────
    try:
        rows = (db.table("interest_clusters")
                .select("id,label,kind,pillar,strength,event_count,"
                        "attributes,happened_on,first_seen,last_event")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(80).execute()).data or []
        for r in rows:
            a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
            r["category"] = a.get("category")
            r["source"] = a.get("source")
            r["relation"] = a.get("relation")
            r.pop("attributes", None)
        out["clusters"] = [r for r in rows if r.get("kind") != "event"]
        out["events"] = [r for r in rows if r.get("kind") == "event"]
    except Exception as e:
        out["clusters"] = [{"error": str(e)[:120]}]
        out["events"] = []

    # ── what is building toward being knowledge ──────────────────────────
    try:
        from memory.mentions import recurring
        out["building"] = recurring(user_id, min_days=1, window=30,
                                    unresolved_only=True)[:30]
    except Exception as e:
        out["building"] = [{"error": str(e)[:120]}]

    try:
        from memory.promotion import habits
        out["would_promote"] = habits(user_id)
    except Exception:
        out["would_promote"] = []

    # ── the graph ────────────────────────────────────────────────────────
    try:
        edges = (db.table("entity_relations").select("*")
                 .eq("user_id", user_id).limit(60).execute()).data or []
        ids = {e["from_id"] for e in edges} | {e["to_id"] for e in edges}
        names = {}
        if ids:
            for c in (db.table("interest_clusters").select("id,label")
                      .in_("id", list(ids)).execute()).data or []:
                names[c["id"]] = c["label"]
        out["edges"] = [{
            "from": names.get(e["from_id"], "?"),
            "type": e.get("type"),
            "to": names.get(e["to_id"], "?"),
            "since": str(e.get("first_seen") or "")[:10],
            "ended": str(e.get("ended_at") or "")[:10] or None,
        } for e in edges]
    except Exception:
        out["edges"] = []

    # ── how she has been, per subject ────────────────────────────────────
    try:
        from memory.topics import by_pillar, declining
        out["pillars"] = by_pillar(user_id, days=30)
        out["declining"] = declining(user_id, days=30)
    except Exception:
        out["pillars"], out["declining"] = {}, []

    # ── today ────────────────────────────────────────────────────────────
    try:
        from memory.day import events as day_events
        out["day"] = day_events(user_id)
    except Exception:
        out["day"] = []

    try:
        from memory.suggestions import _decided_today
        out["settled"] = sorted(_decided_today(user_id))
    except Exception:
        out["settled"] = []

    return out


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>memory · {uid}</title>
<style>
  :root {{ --bg:#0f1115; --fg:#d8dde5; --dim:#7d8799; --line:#242a35;
           --warm:#c9a227; --cold:#4a7ebb; --bad:#b4544a; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:13px/1.55
          ui-monospace,SFMono-Regular,Menlo,monospace; padding:24px 28px 60px }}
  h1 {{ font-size:15px; font-weight:600; margin:0 0 2px }}
  .sub {{ color:var(--dim); margin-bottom:22px }}
  h2 {{ font-size:12px; font-weight:600; color:var(--dim); margin:26px 0 8px;
        text-transform:uppercase; letter-spacing:.09em }}
  table {{ border-collapse:collapse; width:100%; margin-bottom:6px }}
  td,th {{ text-align:left; padding:5px 12px 5px 0; border-bottom:1px solid var(--line);
           vertical-align:top }}
  th {{ color:var(--dim); font-weight:500; font-size:11px }}
  .n {{ color:var(--dim) }}
  .warm {{ color:var(--warm) }}
  .cold {{ color:var(--cold) }}
  .bad {{ color:var(--bad) }}
  .empty {{ color:var(--dim); font-style:italic }}
  .stores span {{ display:inline-block; margin-right:20px; margin-bottom:4px }}
  .stores b {{ font-weight:600 }}
  button {{ background:#1a1f28; color:var(--fg); border:1px solid var(--line);
            padding:5px 12px; border-radius:4px; cursor:pointer; font:inherit }}
  .wide {{ max-width:640px }}
</style></head>
<body>
<h1>memory · {uid}</h1>
<div class="sub"><span id="today"></span> &nbsp; <button onclick="load()">refresh</button></div>
<div id="out">reading…</div>

<script>
const UID = {uid_js};
const KEY = new URLSearchParams(location.search).get('key') || '';

const esc = s => String(s ?? '').replace(/[<>&]/g, c =>
  ({{'<':'&lt;','>':'&gt;','&':'&amp;'}})[c]);

function table(rows, cols) {{
  if (!rows || !rows.length) return '<div class="empty">nothing</div>';
  const head = cols.map(c => `<th>${{c[0]}}</th>`).join('');
  const body = rows.map(r =>
    '<tr>' + cols.map(c => `<td>${{c[1](r)}}</td>`).join('') + '</tr>').join('');
  return `<table><tr>${{head}}</tr>${{body}}</table>`;
}}

function sentiment(v) {{
  if (v === null || v === undefined) return '<span class="n">—</span>';
  const cls = v > 0.2 ? 'warm' : v < -0.2 ? 'bad' : 'n';
  return `<span class="${{cls}}">${{v > 0 ? '+' : ''}}${{v.toFixed(2)}}</span>`;
}}

async function load() {{
  const r = await fetch(`/dashboard/${{UID}}/data`, {{headers: {{'X-API-Key': KEY}}}});
  const d = await r.json();
  document.getElementById('today').textContent = d.today;

  let h = '';

  h += '<h2>stores</h2><div class="stores">';
  for (const [k, v] of Object.entries(d.stores || {{}})) {{
    const cls = v === 0 ? 'n' : v < 0 ? 'bad' : '';
    h += `<span class="${{cls}}">${{k}} <b>${{v < 0 ? 'err' : v}}</b></span>`;
  }}
  h += '</div>';

  if ((d.settled || []).length)
    h += `<h2>already decided today</h2><div class="warm">${{d.settled.join(', ')}}</div>`;

  h += '<h2>today</h2>' + table(d.day, [
    ['at', r => esc(r.due_at)],
    ['', r => esc(r.label || r.kind)],
    ['', r => r.status === 'confirmed' ? '<span class="warm">confirmed</span>'
            : r.status === 'denied' ? '<span class="bad">denied</span>'
            : `<span class="n">${{esc(r.status)}}</span>`],
  ]);

  h += '<h2>the thread</h2>' + table(d.thread, [
    ['day', r => esc(r.happened_on)],
    ['', r => `<div class="wide">${{esc(r.text)}}</div>`],
    ['untagged', r => `<span class="n">${{esc((r.untagged || []).join(', '))}}</span>`],
  ]);

  if ((d.months || []).length)
    h += '<h2>earlier months</h2>' + table(d.months, [
      ['', r => esc(r.period)],
      ['', r => `<div class="wide">${{esc(r.text)}}</div>`],
    ]);

  h += '<h2>what it knows</h2>' + table(d.clusters, [
    ['', r => esc(r.label)],
    ['', r => `<span class="n">${{esc(r.kind)}}</span>`],
    ['', r => esc(r.category || r.relation || '')],
    ['str', r => `<span class="n">${{Number(r.strength || 0).toFixed(1)}}</span>`],
    ['n', r => `<span class="n">${{r.event_count ?? ''}}</span>`],
    ['from', r => `<span class="n">${{esc(r.source || '')}}</span>`],
  ]);

  h += '<h2>building — not yet knowledge</h2>' + table(d.building, [
    ['', r => esc(r.subject)],
    ['days', r => r.days],
    ['', r => `<span class="n">${{esc((r.dates || []).join(' '))}}</span>`],
    ['feeling', r => sentiment(r.feeling)],
  ]);

  if ((d.would_promote || []).length)
    h += '<h2 class="warm">would promote now</h2>' + table(d.would_promote, [
      ['', r => `<span class="warm">${{esc(r.subject)}}</span>`],
      ['days', r => r.days],
      ['', r => `<span class="n">${{esc(r.rhythm || '')}}</span>`],
    ]);

  h += '<h2>what happened</h2>' + table(d.events, [
    ['on', r => esc(r.happened_on || '')],
    ['', r => `<div class="wide">${{esc(r.label)}}</div>`],
  ]);

  h += '<h2>the graph</h2>' + table(d.edges, [
    ['', r => esc(r.from)],
    ['', r => `<span class="cold">${{esc(r.type)}}</span>`],
    ['', r => esc(r.to)],
    ['since', r => `<span class="n">${{esc(r.since)}}</span>`],
    ['', r => r.ended ? `<span class="bad">ended ${{esc(r.ended)}}</span>` : ''],
  ]);

  const pil = Object.entries(d.pillars || {{}}).map(([k, v]) => ({{k, ...v}}));
  h += '<h2>how each part of her life is going</h2>' + table(pil, [
    ['', r => esc(r.k)],
    ['mean', r => sentiment(r.mean)],
    ['n', r => `<span class="n">${{r.mentions}}</span>`],
    ['lowest', r => `<span class="n">${{esc(r.lowest || '')}}</span>`],
  ]);

  if ((d.declining || []).length)
    h += '<h2 class="bad">she has soured on</h2>' + table(d.declining, [
      ['', r => `<span class="bad">${{esc(r.subject)}}</span>`],
      ['was', r => sentiment(r.was)],
      ['now', r => sentiment(r.now)],
      ['n', r => `<span class="n">${{r.mentions}}</span>`],
    ]);

  document.getElementById('out').innerHTML = h;
}}
load();
</script>
</body></html>"""


@router.get("/{user_id}", response_class=HTMLResponse)
def page(user_id: str):
    import json
    return PAGE.format(uid=user_id, uid_js=json.dumps(user_id))
