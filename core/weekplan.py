"""'Plan for next week' (calendar button).

1. Research: Claude Opus 5.5 with web search + web fetch reads the last 7 days of LinkedIn, Instagram/Meta,
   AI and marketing news, and checks it against the Studio's own context (results, competitors, ideas,
   series, festivals, what already went out).
2. Plan: a second call writes scripts for every empty slot next week (LinkedIn rhythm, Instagram reels
   Mon/Wed/Fri + image/carousel Tue/Thu), as structured JSON. The Studio saves them as drafts (scripts only,
   no media: script before media), adds the Galvor page reposts, and writes a report with sources.

Runs in a background thread; status lives in data/weekplan/status.json. Every run is logged on Costs
(Claude tokens at list price + $0.01 per web search).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import traceback
from pathlib import Path

from . import ledger
from .config import DATA, FORMATS, PILLARS, RHYTHM, DISTRIBUTION, load_settings
from .store import all_posts, blank_post, now_iso, save_post

DIR = DATA / "weekplan"
STATUS = DIR / "status.json"
WHAT = "Plan for next week"
WEB_SEARCH_USD = 0.01          # $10 per 1,000 searches (Anthropic list price); web fetch has no extra fee
MAX_SEARCHES, MAX_FETCHES = 15, 6
DEFAULT_EST = (2.0, 5.0)       # USD range shown before the first real run
_lock = threading.Lock()

# The weekly slots (weekday 0 = Monday). LinkedIn page reposts are added by code, not planned by the model.
LI_SLOTS = [
    (0, "09:00", "sunil", "What I heard this week: one real client problem, nobody named"),
    (1, "12:30", "raj", "Brand Breakdown carousel: one non-client brand's public Meta ads"),
    (2, "09:00", "sunil", "Money, AI and the marketing team"),
    (3, "09:00", "shrutik", "New on Instagram this week"),
    (3, "16:00", "raj", "Creator data, measurement, how the AI works"),
    (4, "09:00", "sunil", "Galvor's view, a poll or a lesson"),
]
IG_SLOTS = [
    (0, "19:00", "reel"), (1, "13:00", "image or carousel"), (2, "19:00", "reel"),
    (3, "13:00", "carousel (New on Instagram, mirrors Shrutik's post)"), (4, "19:00", "reel"),
]
REPOST_AT = {"09:00": "13:00", "12:30": "16:30"}       # same day; Raj Thu 16:00 -> Fri 16:00


# ---------------------------------------------------------------- status
def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def status() -> dict:
    s = _read(STATUS, {})
    if s.get("state") == "running":
        started = s.get("started_at", "")
        try:
            age = (dt.datetime.now() - dt.datetime.fromisoformat(started[:19])).total_seconds()
        except ValueError:
            age = 0
        if age > 45 * 60:                       # the instance restarted mid-run
            s.update(state="error", message="The run stopped (the server restarted). Nothing was charged after that point. Try again.")
            _write(STATUS, s)
    return s


def _set(**kw) -> None:
    s = _read(STATUS, {})
    s.update(kw)
    _write(STATUS, s)


# ---------------------------------------------------------------- week and slots
def target_week(today: dt.date | None = None) -> dt.date:
    """Monday of next week."""
    t = today or dt.date.today()
    return t + dt.timedelta(days=7 - t.weekday())


def slots(monday: dt.date) -> list[dict]:
    posts = [p for p in all_posts() if monday.isoformat() <= p["date"] <= (monday + dt.timedelta(days=4)).isoformat()]
    out = []
    for wd, tm, voice, brief in LI_SLOTS:
        d = (monday + dt.timedelta(days=wd)).isoformat()
        have = next((p for p in posts if p["platform"] == "linkedin" and p["date"] == d and p.get("voice") == voice
                     and p.get("series") != "Page repost"), None)
        out.append({"id": f"li-{wd}-{voice}", "platform": "linkedin", "date": d, "time": tm, "voice": voice, "brief": brief,
                    "taken": bool(have), "existing": (have or {}).get("title", "")})
    for wd, tm, kind in IG_SLOTS:
        d = (monday + dt.timedelta(days=wd)).isoformat()
        want = "reel" if kind == "reel" else None
        have = next((p for p in posts if p["platform"] == "instagram" and p["date"] == d and p.get("format") != "story"
                     and (want is None or p.get("format") == want)), None)
        out.append({"id": f"ig-{wd}", "platform": "instagram", "date": d, "time": tm, "voice": "company", "brief": kind,
                    "taken": bool(have), "existing": (have or {}).get("title", "")})
    return out


def _decoded_in(monday: dt.date) -> dict | None:
    end = (monday + dt.timedelta(days=4)).isoformat()
    return next((p for p in all_posts("newsletter") if monday.isoformat() <= p["date"] <= end), None)


# ---------------------------------------------------------------- estimate
def _past_runs() -> list[dict]:
    return [e for e in ledger.entries() if e.get("what") == WHAT and e.get("usd")]


def estimate() -> dict:
    monday = target_week()
    sl = slots(monday)
    empty = [s for s in sl if not s["taken"]]
    past = _past_runs()[-3:]
    if past:
        avg = sum(e["usd"] for e in past) / len(past)
        lo, hi, basis = avg * 0.7, avg * 1.4, f"average of your last {len(past)} run(s): ${avg:.2f}"
    else:
        lo, hi, basis = DEFAULT_EST[0], DEFAULT_EST[1], "no runs yet, so this is a range from the planned work"
    month, cap = ledger.ai_spent_month(), ledger.ai_monthly_cap()
    return {"week_start": monday.isoformat(), "week_end": (monday + dt.timedelta(days=4)).isoformat(),
            "slots": len(sl), "empty": len(empty), "taken": len(sl) - len(empty),
            "searches": MAX_SEARCHES, "fetches": MAX_FETCHES, "low": round(lo, 2), "high": round(hi, 2), "basis": basis,
            "model": load_settings().get("anthropic_model") or "claude-opus-5-5",
            "ai_month": month, "ai_cap": cap, "over_cap": bool(cap) and month + hi > cap,
            "decoded": (_decoded_in(monday) or {}).get("title", ""), "running": status().get("state") == "running"}


# ---------------------------------------------------------------- context the model gets
def _context(monday: dt.date) -> str:
    from . import playbook
    parts = []
    spec = (DATA / "CONTENT_SPEC.md")
    if spec.exists():
        parts.append("## Galvor content rules (house style, CTAs, hooks, voices)\n" + spec.read_text(encoding="utf-8")[:16000])
    parts.append("## Voices\n" + "\n\n".join(playbook.voice_block(k) for k in ("sunil", "raj", "shrutik", "company")))
    parts.append("## Distribution rules\n" + "\n".join("- " + d for d in DISTRIBUTION))
    rp = DATA / "reel_playbook.md"
    if rp.exists():
        parts.append("## Instagram reel playbook (every reel script follows this)\n" + rp.read_text(encoding="utf-8")[:9000])
    series = _read(DATA / "series.json", {})
    if series:
        bb = series.get("brand_breakdown", {})
        parts.append("## Series state\n"
                     f"Brand Breakdown done: {', '.join(bb.get('done', []))}. Next in queue: "
                     + ", ".join(f"{q['brand']} ({q['market']})" for q in bb.get("queue", [])[:6])
                     + f"\nBrand Breakdown format: {bb.get('format', '')}\nSlides: " + " | ".join(bb.get("slides", []))
                     + "\n\nClient stories ready to use (anonymised, each from a real meeting; never add identifying detail):\n"
                     + "\n".join(f"- [{s['voice']}] {s['title']}: {s['hook'].replace(chr(10), ' / ')}" for s in series.get("client_stories", []))
                     + "\n\nMore client angles:\n" + "\n".join("- " + a for a in series.get("client_angles", []))
                     + "\n\nNEVER name these companies anywhere (clients, prospects, partners): " + ", ".join(series.get("never_name", [])))
    lo = (monday - dt.timedelta(days=21)).isoformat()
    recent = [p for p in all_posts() if lo <= p["date"] < monday.isoformat() and p["platform"] in ("linkedin", "instagram", "newsletter")]
    parts.append("## What went out (or is scheduled) in the last 3 weeks: do not repeat these topics\n"
                 + "\n".join(f"- {p['date']} {p['platform']} {p.get('voice')} {p.get('format')}: {p.get('title', '')[:90]}" for p in recent))
    dec = _decoded_in(monday)
    if dec:
        parts.append(f"## Decoded newsletter next week\n{dec['date']} 08:30 from the Galvor page: {dec['title']}. Posts that week can point to it in a first comment only once it is out.")
    fest = [f for f in _read(DATA / "festivals.json", []) if monday.isoformat() <= f.get("date", "") <= (monday + dt.timedelta(days=6)).isoformat()]
    if fest:
        parts.append("## Festivals and marketing dates next week\n" + "\n".join(f"- {f['date']}: {f['name']} ({f.get('category', '')}, {f.get('region', '')})" for f in fest))
    comp = _read(DATA / "competitors_research.json", {})
    if comp:
        parts.append("## Competitor notes (Studio research)\n" + json.dumps(comp.get("cross_cutting") or comp, ensure_ascii=False)[:5000])
    ideas = _read(DATA / "ideas.json", [])
    if isinstance(ideas, list) and ideas:
        parts.append("## Ideas bank\n" + "\n".join(f"- {i.get('title') or i.get('idea') or ''}" for i in ideas[:25] if isinstance(i, dict)))
    li = _read(DATA / "analytics" / "linkedin.json", {})
    rows = []
    for acct, a in (li.get("accounts") or {}).items():
        ps = a.get("posts") or []
        ps = list(ps.values()) if isinstance(ps, dict) else list(ps)
        ps = sorted([p for p in ps if isinstance(p, dict)], key=lambda p: str(p.get("date") or p.get("published") or ""))
        for p in ps[-12:]:
            if isinstance(p, dict):
                m = p.get("metrics") or p
                rows.append(f"- {acct} {p.get('date', '')} {p.get('post_type', '')}: {str(p.get('slug_text') or p.get('title') or p.get('url') or '')[:70]}"
                            f" · impressions {m.get('impressions')} · engagements {m.get('engagements')} · comments {m.get('comments')}")
    if rows:
        parts.append("## Recent LinkedIn results (from the Studio's imports)\n" + "\n".join(rows[:30]))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- Claude calls
def _usage_add(tot: dict, msg) -> None:
    u = msg.usage
    tot["in"] += u.input_tokens or 0
    tot["out"] += u.output_tokens or 0
    tot["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
    tot["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
    stu = getattr(u, "server_tool_use", None)
    if stu is not None:
        tot["searches"] += getattr(stu, "web_search_requests", 0) or 0
    tot["model"] = msg.model or tot.get("model", "")


def _stream(client, **kw):
    with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw) as s:
        return s.get_final_message()


def _research(client, model: str, monday: dt.date, context: str, tot: dict) -> tuple[str, list[dict]]:
    week = f"{monday:%a %d %b} to {(monday + dt.timedelta(days=4)):%a %d %b %Y}"
    today = dt.date.today()
    prompt = f"""Today is {today:%A %d %B %Y}. You are researching for Galvor's content plan for next week ({week}).
Galvor is an AI marketing company (creative analysis of ads and creators for D2C brands; Galvor Scout vets creators by
reading their reels and comments against a plain-language brief). Audience: D2C founders, growth and brand leads,
creator-marketing teams in India, the Gulf, South-East Asia, the US and UK.

Research what happened in the last 7 days (and anything announced for next week) that this audience will care about.
Cover all of these, searching each one:
1. LinkedIn: product, feed or algorithm changes, creator/video features, B2B marketing news.
2. Instagram and Meta: new features, Reels, creator tools, Edits, ads products (Advantage+, partnership/collab ads,
   Andromeda), measurement and policy changes. Confirm each on an official source (Mosseri, @creators, Meta newsroom,
   about.fb.com, business.facebook.com) where you can.
3. AI world: model and product launches, AI in marketing and advertising, AI video/creative tools, agents.
4. Creator economy and influencer marketing, especially India and the Gulf.
5. D2C and e-commerce marketing news, notable campaigns and ad trends (India first, then global).
6. Anything time-bound next week: events, sales, festivals, earnings, launches.

Rules: prefer primary sources; give every finding a URL and its publish date; drop anything older than 10 days unless it
is still unfolding; say plainly when something is a rumour or only reported by one blog. Do not invent numbers.

The Studio's own context follows (rules, voices, series, what already went out, results). Use it to judge what is new
and useful to Galvor, not to search.

{context[:60000]}

Finish with a research brief in markdown, with these sections:
## Top findings (8-14 items): for each, a one-line headline, 2-3 plain sentences, why it matters to this audience,
the best Galvor voice for it (Sunil / Raj / Shrutik / Galvor page / Instagram), and the source URL + date.
## Instagram changes worth a "New on Instagram" post (ranked)
## Timely hooks for next week
## What to avoid (stale, over-covered, or risky topics)"""
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": MAX_FETCHES}]
    msg, acc = None, []
    for _ in range(6):                              # pause_turn: re-send with the paused content, server resumes
        msg = _stream(client, model=model, max_tokens=32000, messages=messages, tools=tools,
                      output_config={"effort": "high"})
        _usage_add(tot, msg)
        acc += list(msg.content)
        _set(stage=f"Researching… {tot['searches']} searches so far")
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": acc}]
    if msg.stop_reason == "refusal":
        raise RuntimeError("The research step was declined by the model.")
    # the brief is the text after the last tool call
    last_tool = max((i for i, b in enumerate(acc) if getattr(b, "type", "").endswith("tool_result")), default=-1)
    text = "".join(b.text for b in acc[last_tool + 1:] if getattr(b, "type", "") == "text").strip() or         "".join(b.text for b in acc if getattr(b, "type", "") == "text").strip()
    sources = []
    for b in acc:
        if getattr(b, "type", "") == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                if getattr(r, "url", None):
                    sources.append({"title": getattr(r, "title", ""), "url": r.url, "age": getattr(r, "page_age", "")})
    return text, sources


SLIDE = {"type": "object", "additionalProperties": False, "required": ["layout", "headline"], "properties": {
    "layout": {"type": "string", "enum": ["cover", "statement", "text", "stat", "list", "compare", "poll", "cta"]},
    "kicker": {"type": "string"}, "headline": {"type": "string"}, "sub": {"type": "string"}, "body": {"type": "string"},
    "stat": {"type": "string"}, "source": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}},
    "left_title": {"type": "string"}, "left": {"type": "array", "items": {"type": "string"}},
    "right_title": {"type": "string"}, "right": {"type": "array", "items": {"type": "string"}},
    "options": {"type": "array", "items": {"type": "string"}}, "actions": {"type": "array", "items": {"type": "string"}}}}
SCENE = {"type": "object", "additionalProperties": False, "required": ["time", "visual", "voiceover", "on_screen"],
         "properties": {k: {"type": "string"} for k in ("time", "visual", "voiceover", "on_screen")}}
PLAN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "posts", "notes_on_existing"], "properties": {
    "summary": {"type": "string"},
    "notes_on_existing": {"type": "string"},
    "posts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["slot_id", "title", "format", "pillar", "job", "hook", "caption", "first_comment", "hashtags",
                     "alt_text", "slides", "script", "page_line", "why", "sources", "status"],
        "properties": {
            "slot_id": {"type": "string"}, "title": {"type": "string"},
            "format": {"type": "string", "enum": ["text", "image", "carousel", "poll", "video", "reel"]},
            "pillar": {"type": "string"}, "job": {"type": "string", "enum": ["Attract", "Educate", "De-risk", "Convert"]},
            "hook": {"type": "string"}, "caption": {"type": "string"}, "first_comment": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}}, "alt_text": {"type": "string"},
            "slides": {"type": "array", "items": SLIDE},
            "script": {"type": "object", "additionalProperties": False, "required": ["duration", "setup", "scenes"], "properties": {
                "duration": {"type": "string"}, "setup": {"type": "string"}, "scenes": {"type": "array", "items": SCENE}}},
            "poll_question": {"type": "string"}, "poll_options": {"type": "array", "items": {"type": "string"}},
            "page_line": {"type": "string"}, "why": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": ["draft", "idea"]}}}}}}


def _plan(client, model: str, monday: dt.date, context: str, research: str, sl: list[dict], tot: dict) -> dict:
    open_slots = [s for s in sl if not s["taken"]]
    prompt = f"""Plan Galvor's content for the week of {monday:%d %b %Y} (Mon to Fri; nothing on weekends).

RESEARCH BRIEF (fresh, from the web, with sources):
{research}

STUDIO CONTEXT:
{context[:60000]}

SLOTS TO FILL (write exactly one post per slot_id below):
{json.dumps(open_slots, ensure_ascii=False, indent=1)}

SLOTS ALREADY FILLED (do not write these; in notes_on_existing say if news makes any of them stale or more timely):
{json.dumps([s for s in sl if s['taken']], ensure_ascii=False, indent=1)}

How to write them:
- LinkedIn format mix: mostly carousel, image and video; at most one text-only post in the week. Video = a talking-head
  script for the person (scenes with time, visual, voiceover, on_screen). Image = one slide. Carousel = 5-8 slides.
- Instagram: reels on Mon, Wed, Fri (format "reel", 25-40 s script plus a cover slide and a CTA slide "Follow @galvor.ai");
  Tue and Thu are an image or carousel. Thursday mirrors Shrutik's "New on Instagram" post.
- Reels follow the reel playbook in the context: hook, lock-in zone, body blocks with rehooks, CTA with an aligned
  lead magnet (use "link in bio", no comment-for-DM yet), then Follow @galvor.ai. In script.setup name the bricks
  (format, seed, text hook, visual hook, layout, lead magnet) and the ONE brick being tested this time.
- Sunil's Monday post uses one of the client stories or angles (never add anything that could identify the client).
- Raj's Tuesday post is the next Brand Breakdown brand in the queue: write it as status "idea" with the hook and slide
  outline, and say in "why" that the brand's public Meta Ad Library data must be pulled before it can be finished.
  Never put a number on it that you don't have.
- Shrutik's Thursday post: the most useful Instagram change from the research, confirmed on a source.
- Every LinkedIn caption opens with a 2-line hook (each line under ~60 characters) that works before "see more".
- Sound like a real person typing: short uneven sentences, contractions, no em dashes, no "it's not X, it's Y", no
  tidy lists of three in comments, no neat moral endings, no hype words. Plain words a brand manager would say over coffee.
- Close with "Follow Galvor" (LinkedIn) or "Follow @galvor.ai" (Instagram). Never ask people to follow a person.
- Links go in first_comment on personal posts, never in the caption.
- Numbers: only from the research (with its source in "sources") or from the Studio context. Otherwise use none.
- Never name a client or anyone on the never-name list. No client results without permission.
- slides: for text/video posts use []; for carousel/image/reel fill them. Stat slides need "stat" and "source".
- script: for non-video formats give {{"duration": "", "setup": "", "scenes": []}}.
- pillar must be one of LinkedIn {PILLARS['linkedin']} or Instagram {PILLARS['instagram']}.
- page_line: the short line the Galvor page posts when it reposts this (LinkedIn personal posts only; "" otherwise).
- why: one or two lines on why this post, this week. sources: the URLs it relies on.
- status "draft" for finished scripts, "idea" only when data is still missing.
summary: 4-6 lines on the week's plan and the reasoning."""
    msg = _stream(client, model=model, max_tokens=64000, messages=[{"role": "user", "content": prompt}],
                  output_config={"effort": "high", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}})
    _usage_add(tot, msg)
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"The planning step stopped early ({msg.stop_reason}).")
    text = next(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return json.loads(text)


# ---------------------------------------------------------------- save
def _save_posts(plan: dict, sl: list[dict], monday: dt.date, run_id: str) -> list[str]:
    from .lint import lint_post
    by_id = {s["id"]: s for s in sl if not s["taken"]}
    made, reposts = [], []
    for item in plan.get("posts", []):
        s = by_id.pop(item.get("slot_id"), None)
        if not s:
            continue
        plat = s["platform"]
        fmt = item["format"] if item["format"] in FORMATS[plat] else ("reel" if plat == "instagram" else "text")
        pillar = item["pillar"] if item["pillar"] in PILLARS[plat] else PILLARS[plat][0]
        p = blank_post(plat, s["date"], time=s["time"], voice=s["voice"], pillar=pillar, job=item["job"], format=fmt,
                       status=item.get("status") or "draft", title=item["title"][:140], hook=item["hook"],
                       caption=item["caption"], first_comment=item.get("first_comment") or "",
                       hashtags=[h if h.startswith("#") else "#" + h for h in item.get("hashtags", [])][:5],
                       alt_text=item.get("alt_text") or "",
                       creative={"size": "story" if fmt == "reel" else "feed", "slides": item.get("slides") or []},
                       series={"sunil-0": "What I heard this week"}.get(f"{s['voice']}-{dt.date.fromisoformat(s['date']).weekday()}", ""),
                       notes=f"[Plan for next week · {run_id}] {item.get('why', '')}\nSources: " + ", ".join(item.get("sources", [])))
        if fmt in ("video", "reel") and (item.get("script") or {}).get("scenes"):
            p["script"] = item["script"]
        if fmt == "poll" and item.get("poll_options"):
            p["poll"] = {"question": item.get("poll_question") or item["hook"][:140], "options": item["poll_options"][:4], "duration": "1 week"}
        if s["voice"] == "raj" and dt.date.fromisoformat(s["date"]).weekday() == 1:
            p["series"] = "Brand Breakdown"
        if s["voice"] == "shrutik" or (plat == "instagram" and dt.date.fromisoformat(s["date"]).weekday() == 3):
            p["series"] = "New on Instagram"
        if any(i["severity"] == "error" and i["field"] != "images" for i in lint_post(p)) and p["status"] == "draft":
            p["notes"] += "\nThe Studio's checks flagged something on this draft: open it and fix before approving."
        saved = save_post(p, note=f"Plan for next week ({run_id}): created")
        made.append(saved["id"])
        if plat == "linkedin" and item.get("page_line"):
            reposts.append((saved, item["page_line"]))
    for orig, line in reposts:
        d = dt.date.fromisoformat(orig["date"])
        if orig["voice"] == "raj" and d.weekday() == 3:
            rd, rt = (d + dt.timedelta(days=1)).isoformat(), "16:00"
        else:
            rd, rt = orig["date"], REPOST_AT.get(orig["time"], "13:00")
        rp = blank_post("linkedin", rd, time=rt, voice="company", pillar=orig["pillar"], job="Attract", format="text",
                        series="Page repost", status="draft", title=f"Page repost: {orig['title'][:80]}", hook=line, caption=line,
                        notes=f"[Plan for next week · {run_id}] Repost {orig['voice'].title()}'s post '{orig['title']}' from the Galvor page with this line, after the first hour of comments.")
        made.append(save_post(rp, note=f"Plan for next week ({run_id}): page repost")["id"])
    # series bookkeeping
    series = _read(DATA / "series.json", {})
    if series:
        bb = series.get("brand_breakdown", {})
        planned = [x for x in plan.get("posts", []) if x.get("slot_id") == "li-1-raj"]
        if planned and bb.get("queue"):
            title = planned[0]["title"].lower()
            hit = next((q for q in bb["queue"] if q["brand"].lower() in title), None)
            if hit:
                bb["queue"].remove(hit); bb.setdefault("done", []).append(hit["brand"])
                _write(DATA / "series.json", series)
    return made


def _run(run_id: str) -> None:
    from .ai import claude_client
    monday = target_week()
    tot = {"in": 0, "out": 0, "cache_write": 0, "cache_read": 0, "searches": 0, "model": ""}
    model = load_settings().get("anthropic_model") or "claude-opus-5-5"
    try:
        sl = slots(monday)
        context = _context(monday)
        client = claude_client(timeout=900.0)
        _set(stage="Researching LinkedIn, Instagram, AI and marketing news…")
        research, sources = _research(client, model, monday, context, tot)
        _set(stage="Writing next week's scripts…")
        plan = _plan(client, model, monday, context, research, sl, tot)
        _set(stage="Saving drafts…")
        made = _save_posts(plan, sl, monday, run_id)
        usd = _cost(tot)
        report = (f"# Plan for the week of {monday:%d %b %Y}\n\nRun {run_id} · {len(made)} posts created · "
                  f"{tot['searches']} web searches · ${usd:.2f}\n\n## The plan\n{plan.get('summary', '')}\n\n"
                  f"## Notes on posts that were already in the calendar\n{plan.get('notes_on_existing', '') or 'None.'}\n\n"
                  f"## Posts\n" + "\n".join(f"- **{x['title']}** ({x['slot_id']}, {x['format']}): {x.get('why', '')}" for x in plan.get("posts", []))
                  + f"\n\n---\n\n# Research brief\n\n{research}\n\n## All sources seen\n"
                  + "\n".join(f"- [{s['title'] or s['url']}]({s['url']}) {s.get('age') or ''}" for s in sources[:80]))
        (DIR / run_id).mkdir(parents=True, exist_ok=True)
        (DIR / run_id / "report.md").write_text(report, encoding="utf-8")
        _write(DIR / run_id / "plan.json", plan)
        _log(tot, usd, run_id, ok=True)
        _set(state="done", stage="Done", finished_at=now_iso(), created=made, usd=round(usd, 4), searches=tot["searches"],
             tokens={k: tot[k] for k in ("in", "out", "cache_write", "cache_read")}, report=f"/plan/{run_id}",
             message=f"{len(made)} posts drafted for the week of {monday:%d %b}. Read the scripts before any media is made.")
    except Exception as e:                       # noqa: BLE001 — shown to the user, logged in full
        usd = _cost(tot)
        if usd:
            _log(tot, usd, run_id, ok=False)
        (DIR / run_id).mkdir(parents=True, exist_ok=True)
        (DIR / run_id / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        why = str(e)
        if "credit balance" in why.lower():
            why = ("the Claude API account is out of credit. Add credit at console.anthropic.com under Plans & Billing, "
                   "then click the button again")
        _set(state="error", stage="Stopped", finished_at=now_iso(), usd=round(usd, 4), searches=tot["searches"],
             message=f"The plan stopped: {why[:300]}. Charged so far: ${usd:.2f}.")


def _cost(tot: dict) -> float:
    model_usd = ledger.ai_cost(tot.get("model") or "claude-opus-5-5", tot["in"], tot["out"], tot["cache_write"], tot["cache_read"]) or 0.0
    return model_usd + tot["searches"] * WEB_SEARCH_USD


def _log(tot: dict, usd: float, run_id: str, ok: bool) -> None:
    ledger.record("claude", WHAT, usd, kind="ai", cap=False, model=tot.get("model", ""),
                  tokens={k: tot[k] for k in ("in", "out", "cache_write", "cache_read")}, searches=tot["searches"],
                  run=run_id, note=("" if ok else "stopped early") + f" · {tot['searches']} web searches at ${WEB_SEARCH_USD} each")


def start(actor: str) -> dict:
    with _lock:
        if status().get("state") == "running":
            return {"ok": False, "error": "A plan is already running."}
        try:
            ledger.check_ai()
        except ledger.OverBudget as e:
            return {"ok": False, "error": str(e)}
        run_id = dt.datetime.now().strftime("%Y%m%d-%H%M")
        est = estimate()
        _write(STATUS, {"state": "running", "stage": "Starting…", "run": run_id, "started_at": now_iso(), "by": actor,
                        "week_start": est["week_start"], "estimate": [est["low"], est["high"]]})
        threading.Thread(target=_run, args=(run_id,), daemon=True).start()
        return {"ok": True, "run": run_id}


def runs() -> list[dict]:
    out = []
    for d in sorted(DIR.glob("2*"), reverse=True):
        if d.is_dir():
            out.append({"run": d.name, "has_report": (d / "report.md").exists(), "error": (d / "error.txt").exists()})
    return out


def report(run_id: str) -> str:
    if not re.fullmatch(r"\d{8}-\d{4}", run_id):
        return ""
    f = DIR / run_id / "report.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""
