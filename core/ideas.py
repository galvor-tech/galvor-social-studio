"""Ideas: turn scanned posts (core.discover) into post ideas, and surface unused hooks from data/topics.json.

Ported from galvor-cms ideas.py. The model may only cite numbers that really appear in the source
posts: any number whose value can't be found in its source item is dropped before saving.
All LLM calls go through core.ai.complete (Claude or Gemini, whichever the studio is set to).

Data: data/ideas.json = {"ideas": [...]}.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

from . import discover, guard, ledger
from .config import DATA, FORMATS, JOBS, PILLARS, VOICES, load_settings

IDEAS_FILE = DATA / "ideas.json"
TOPICS_FILE = DATA / "topics.json"
STATUSES = ("new", "shortlisted", "used", "dropped")
PLATFORMS = ("linkedin", "instagram", "both")
WRITING_VOICES = [v for v in VOICES if v != "kc"]  # KC amplifies; he doesn't get posts written for him
IG_HANDLE = "@galvor.ai"

# Rough per-million-token prices for the ledger (ai.complete doesn't return usage, so we estimate
# tokens as chars/4 and add a thinking allowance). Claude Opus 5.5 $4/$20; Gemini flash per the CMS.
AI_USD_PER_M = {"anthropic": {"in": 4.0, "out": 20.0}, "gemini": {"in": 0.30, "out": 2.50},
                "gemini-pro": {"in": 1.25, "out": 10.0}}
THINKING_ALLOWANCE_TOKENS = 3000

_lock = threading.RLock()

CONTEXT = """Galvor is an AI creative-intelligence company for D2C brands (India first, some UK).
It decodes why ads and creator videos work, vets creators before brands pay them, checks creator
videos against the brief before they go live, and drafts scripts from a brand's own data.

What buyers told us in 63 sales meetings (Jul-Oct 2026):
- They care most about CREATORS: finding them, vetting them, scripts, and checking creator videos
  before they go live. Weight ideas toward creator topics.
- They distrust "this ad won" when the only evidence is how long it ran. Never call a public ad a
  winner; say "ran longest" or tie it to real results.
- They compare Galvor with their agency and with doing it themselves in ChatGPT, not with other tools.
- They want a short ranked list of actions, not another dashboard.
- They want Indian, regional and language-level examples.
- Proof matters most: anonymised, specific, checkable.

Rules: never name a Galvor client or its category. No invented numbers. Plain, direct language.
Write for D2C marketing heads, founders, performance marketers and influencer managers."""

STUDIO_RULES = f"""Studio rules (from the content spec, which also applies):
- One post, one argument. Open with tension, an observation or a claim; never "Excited to share".
- Earn the product mention: the buyer's problem comes first. Small samples are "a signal", never a rule.
- Never claim a competitor's spend or ROAS from public data. No client names or client numbers.
- Banned words: excited to share, thrilled, game-changer, revolutionise, unlock, unleash, delve,
  cutting-edge, seamlessly, elevate, next-level, skyrocket, synergy, "in today's fast-paced".
- The closing CTA always asks people to follow Galvor: "Follow Galvor" on LinkedIn, "Follow {IG_HANDLE}"
  on Instagram (the Instagram handle is {IG_HANDLE}). Never "Follow Raj", "Follow me" or "Follow along".
- Instagram posts go out from the company account only (voice "company").
- Voices: sunil = co-founder (money, risk, teams; founders/CMOs); raj = founding AI engineer (what the ads and
  numbers say, how we built it; performance heads); shrutik = client servicing (briefs, creators, approvals, QC;
  brand/creative managers, agencies); company = Galvor page (proof, product, culture)."""

FORMAT_ALIASES = {
    "short video": "video", "short-video": "video", "video script": "video", "talking head": "video",
    "text post": "text", "linkedin text post": "text", "post": "text", "single image": "image",
    "static": "image", "document": "carousel", "pdf": "carousel", "slides": "carousel", "reels": "reel",
}


# ------------------------------------------------------------------ storage
def _load() -> dict:
    try:
        d = json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("ideas"), list):
            return d
    except (OSError, json.JSONDecodeError):
        pass
    return {"ideas": []}


def _save(d: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = IDEAS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(IDEAS_FILE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_ideas(status: str | None = None) -> list[dict]:
    with _lock:
        rows = _load()["ideas"]
    if status:
        rows = [i for i in rows if i.get("status") == status]
    return sorted(rows, key=lambda i: i.get("created_at") or "", reverse=True)


def get_idea(idea_id: str) -> dict | None:
    with _lock:
        return next((i for i in _load()["ideas"] if i["id"] == idea_id), None)


EDITABLE = {"hook", "title", "angle", "outline", "platform", "format", "pillar", "voice", "job", "why_now",
            "status", "post_id", "notes"}


def update_idea(idea_id: str, **fields) -> dict | None:
    """Edit an idea. Platform/format/pillar/voice are re-validated; guard flags are re-run on text changes."""
    bad = set(fields) - EDITABLE
    if bad:
        raise ValueError(f"Can't edit {sorted(bad)} on an idea.")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"Status must be one of {STATUSES}.")
    with _lock:
        d = _load()
        idea = next((i for i in d["ideas"] if i["id"] == idea_id), None)
        if not idea:
            return None
        idea.update(fields)
        if fields.keys() & {"platform", "format", "pillar", "voice", "job"}:
            idea.update(_validate_meta(idea))
        if fields.keys() & {"hook", "title", "angle", "outline", "why_now"}:
            idea["flags"] = guard.check(_idea_text(idea))
        if fields.get("post_id") and "status" not in fields:
            idea["status"] = "used"
        idea["updated_at"] = _now()
        _save(d)
        return idea


# ------------------------------------------------------------------ number check
_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _source_text(item: dict) -> str:
    metrics = {k: item.get(k) for k in ("likes", "comments", "shares", "views") if item.get(k)}
    return " ".join([item.get("title") or "", item.get("text") or "", json.dumps(metrics)])


def _num_tokens(s: str) -> set[str]:
    return {t.replace(",", "").rstrip(".") for t in _NUM_TOKEN.findall(s or "")}


def _value_in_source(value, item: dict) -> bool:
    """A number must appear in the post's text or counts (commas and units ignored).
    Ported from the CMS; the digit fallback is tightened to whole numbers so '3' and '6' from
    different places can't combine into '36'."""
    hay = _source_text(item)
    v = str(value if value is not None else "").strip()
    if not v or not re.search(r"\d", v):
        return False
    if re.search(r"(?<![\d.,])" + re.escape(v.lower()) + r"(?![\d])", hay.lower()):
        return True
    want = _num_tokens(v)
    return bool(want) and want <= _num_tokens(hay)


def _quote_for(value, item: dict, quote: str | None) -> str:
    text = " ".join([item.get("title") or "", item.get("text") or ""])
    norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()
    if quote and norm(quote) in norm(text):
        return quote.strip()
    digits = next(iter(_num_tokens(str(value))), None)
    for m in _NUM_TOKEN.finditer(text):
        if digits and m.group(0).replace(",", "").rstrip(".") == digits:
            a, b = max(0, m.start() - 70), min(len(text), m.end() + 70)
            return ("…" if a else "") + re.sub(r"\s+", " ", text[a:b]).strip() + ("…" if b < len(text) else "")
    return f"(from the post's counts: {value})"


# ------------------------------------------------------------------ validation
def _closest(value, allowed, default):
    if not value:
        return default
    low = {a.lower(): a for a in allowed}
    v = str(value).strip()
    if v.lower() in low:
        return low[v.lower()]
    m = difflib.get_close_matches(v.lower(), list(low), n=1, cutoff=0.6)
    return low[m[0]] if m else default


def _coerce_format(fmt, platform):
    f = FORMAT_ALIASES.get(str(fmt or "").strip().lower(), str(fmt or "").strip().lower())
    if platform == "instagram" and f == "video":
        f = "reel"
    if platform in ("linkedin",) and f in ("reel", "story"):
        f = "video"
    if platform == "both":
        allowed = [x for x in FORMATS["linkedin"] if x in FORMATS["instagram"]]  # image, carousel
        return f if f in allowed else "carousel"
    allowed = FORMATS[platform]
    if f in allowed:
        return f
    return "text" if platform == "linkedin" else "carousel"


def _validate_meta(idea: dict) -> dict:
    """Coerce platform/format/pillar/voice/job into allowed values."""
    platform = str(idea.get("platform") or "").strip().lower()
    platform = platform if platform in PLATFORMS else "linkedin"
    fmt = _coerce_format(idea.get("format"), platform)
    base = "linkedin" if platform == "both" else platform
    pillar = _closest(idea.get("pillar"), PILLARS[base], "Brand Memory / POV" if base == "linkedin" else "Quick Tip")
    voice = str(idea.get("voice") or "").strip().lower()
    voice = voice if voice in WRITING_VOICES else "company"
    if platform == "instagram":
        voice = "company"
    out = {"platform": platform, "format": fmt, "pillar": pillar, "voice": voice,
           "job": _closest(idea.get("job"), JOBS, "Educate")}
    if platform == "both":
        out["pillar_instagram"] = _closest(idea.get("pillar_instagram") or idea.get("pillar"),
                                           PILLARS["instagram"], "Quick Tip")
    return out


def _idea_text(idea: dict) -> str:
    return " ".join([idea.get("title") or "", idea.get("hook") or "", idea.get("angle") or "",
                     " ".join(idea.get("outline") or []), idea.get("why_now") or ""])


def _clean_idea(raw: dict, by_id: dict[str, dict]) -> dict | None:
    """Turn one model idea into a stored idea, or None if it is unusable (no hook)."""
    if not isinstance(raw, dict):
        return None
    hook = str(raw.get("hook") or "").strip()
    if not hook:
        return None
    ids = [str(i) for i in (raw.get("source_item_ids") or raw.get("item_ids") or []) if str(i) in by_id]
    numbers = []
    for p in raw.get("numbers") or raw.get("data_points") or []:
        if not isinstance(p, dict):
            continue
        src = by_id.get(str(p.get("source_item_id") or p.get("item_id") or ""))
        val = p.get("value")
        if src and _value_in_source(val, src):
            numbers.append({"value": str(val).strip(), "source_item_id": src["id"],
                            "quote": _quote_for(val, src, p.get("quote")), "label": p.get("label") or "",
                            "url": src.get("url")})
            if src["id"] not in ids:
                ids.append(src["id"])
    outline = raw.get("outline") or []
    if isinstance(outline, str):
        outline = [ln.strip(" -•\t") for ln in outline.splitlines() if ln.strip()]
    idea = {
        "id": "idea-" + uuid.uuid4().hex[:10], "created_at": _now(), "origin": "discover",
        "source_item_ids": ids, "title": str(raw.get("title") or hook)[:90], "hook": hook,
        "angle": str(raw.get("angle") or "").strip(),
        "outline": [str(x) for x in outline][:10], "why_now": str(raw.get("why_now") or raw.get("why") or "").strip(),
        "numbers": numbers, "status": "new", "post_id": None,
        "numbers_dropped": len([p for p in raw.get("numbers") or [] if isinstance(p, dict)]) - len(numbers),
    }
    idea.update(_validate_meta(raw))
    idea["flags"] = guard.check(_idea_text(idea))
    return idea


# ------------------------------------------------------------------ AI call (priced)
def _rates():
    from . import ai
    p = ai.provider()
    if p == "gemini" and "pro" in str(load_settings().get("gemini_model") or "").lower():
        return p, AI_USD_PER_M["gemini-pro"]
    return p, AI_USD_PER_M.get(p, AI_USD_PER_M["anthropic"])


def _priced_complete(prompt: str, what: str) -> str:
    from . import ai
    p, r = _rates()
    in_tok = (len(ai.SYSTEM) + len(prompt)) / 4
    est = in_tok / 1e6 * r["in"] + (4000 + THINKING_ALLOWANCE_TOKENS) / 1e6 * r["out"]
    ledger.check(est, what)
    text = ai.complete(prompt, log=False)
    out_tok = len(text) / 4 + (THINKING_ALLOWANCE_TOKENS if p == "anthropic" else 0)
    ledger.record(p, what, in_tok / 1e6 * r["in"] + out_tok / 1e6 * r["out"])
    return text


def _pick_items(n_items: int) -> list[dict]:
    """Top relevant recent items, unused first, spread across source kinds."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    pool = [i for i in discover.items(limit=0) if (i.get("fetched_at") or "") >= cutoff]
    rel = [i for i in pool if i.get("relevant")] or pool
    rel.sort(key=lambda i: (not i.get("used_in_ideas"), i.get("score") or 0), reverse=True)
    by_kind: dict[str, list] = {}
    for i in rel:
        by_kind.setdefault(i["source_kind"], []).append(i)
    picked = []
    while len(picked) < n_items and any(by_kind.values()):
        for k in list(by_kind):
            if by_kind[k] and len(picked) < n_items:
                picked.append(by_kind[k].pop(0))
    return picked


def build_prompt(items: list[dict], n_ideas: int) -> str:
    listing = "\n\n".join(
        f"[{i['id']}] {i['source_kind']} | {i.get('author') or ''} | {i.get('posted_at') or ''} | "
        f"likes {i.get('likes', 0)}, comments {i.get('comments', 0)}, shares {i.get('shares', 0)}, views {i.get('views', 0)}\n"
        f"{(i.get('text') or '')[:700]}"
        for i in items)
    pillars = json.dumps({"linkedin": PILLARS["linkedin"], "instagram": PILLARS["instagram"]}, ensure_ascii=False)
    formats = json.dumps({"linkedin": [f for f in FORMATS["linkedin"] if f not in ("newsletter", "article")],
                          "instagram": FORMATS["instagram"]})
    return f"""TASK OVERRIDE: for this request do NOT write a post and do NOT use the post schema. Return the
ideas JSON described at the end instead.

{CONTEXT}

{STUDIO_RULES}

Below are posts people published in the last few days about Meta ads, creators and D2C marketing.
Each starts with its id in brackets.

{listing}

Write {n_ideas} distinct content ideas for Galvor, each taking a real angle from one or more of these
posts (agree, disagree, add Galvor's view, or turn it into a teardown). Mix platforms and formats
(LinkedIn text, carousel, poll, video; Instagram carousel, reel). At least a third must be about creators.
Ignore posts that are off-topic for D2C performance marketing.

Return ONLY this JSON: {{"ideas": [{{
  "title": "one-line idea, under 90 characters",
  "hook": "the first line of the post or the first spoken line of the video",
  "angle": "2-3 sentences: what we say and why it is Galvor's to say",
  "outline": ["4-6 short beats or slide/paragraph lines; the last one is the closing CTA (Follow Galvor / Follow {IG_HANDLE})"],
  "platform": "linkedin | instagram | both",
  "format": one of {formats} for that platform ("both" must be image or carousel),
  "pillar": one of {pillars} for that platform ("both" uses a LinkedIn pillar),
  "voice": one of {WRITING_VOICES} (instagram is always "company"),
  "job": one of {JOBS},
  "why_now": "why now, citing the source posts",
  "source_item_ids": ["ids of the posts used"],
  "numbers": [{{"value": "a number exactly as written in the post or its counts", "source_item_id": "id", "quote": "the exact sentence from the post containing it", "label": "short phrase that reads naturally after the number"}}]
}}]}}
Only put numbers in "numbers" that literally appear in the cited post or its counts; they will be checked
and dropped if not found. If none fit, return an empty list. Do not put any other statistic in the hook or
angle unless it is in the facts bank."""


def generate(item_ids=None, n_ideas: int = 8, n_items: int = 25) -> list[dict]:
    """Ideas from the selected discover items (or the top relevant recent ones). Saves and returns them."""
    from . import ai
    items = discover.get_items(item_ids) if item_ids else _pick_items(n_items)
    if not items:
        raise ValueError("No scanned posts to work from. Run a scan first.")
    text = _priced_complete(build_prompt(items, n_ideas), f"{n_ideas} ideas from {len(items)} posts")
    out = ai._parse_json(text)
    raw = out.get("ideas") if isinstance(out, dict) else out
    if not isinstance(raw, list):
        raise ai.AIError("The model didn't return a list of ideas.")
    by_id = {i["id"]: i for i in items}
    saved = [x for x in (_clean_idea(r, by_id) for r in raw) if x]
    with _lock:
        d = _load()
        d["ideas"].extend(saved)
        _save(d)
    used = {}
    for idea in saved:
        for iid in idea["source_item_ids"]:
            used.setdefault(iid, []).append(idea["id"])
    for iid, idea_ids in used.items():
        discover.mark_used([iid], idea_ids)
    return saved


# ------------------------------------------------------------------ topics bank
TOPIC_PILLAR_MAP = {  # same mapping as app._map_pillar
    "Marketing money for founders and CMOs": "Marketing Money", "Brand Memory (our point of view)": "Brand Memory / POV",
    "AI and the marketing team": "AI & the Team", "In the room with buyers (series: \"What I Heard in the Room\")": "In the Room",
    "Building Galvor (founder journey)": "Building Galvor", "Reading ads (series: \"Ad of the Week\")": "Decode Teardown",
    "What public data can and can't tell you": "Public Data", "Building the engine (learning in public)": "Building Galvor",
    "Measurement that matters": "Measurement", "Creators and testing": "Creators & Testing", "Better briefs": "Better Briefs",
    "Running creator campaigns in India": "Creator Ops India", "Feedback and approvals": "Feedback & Approvals",
    "AI in the real workflow": "AI & the Team", "Client lessons": "Client Lessons",
}


def _used_topic_refs() -> set[str]:
    refs = set()
    try:
        from .store import all_posts
        refs |= {p.get("topic_ref") for p in all_posts() if p.get("topic_ref")}
    except Exception:
        pass
    refs |= {i.get("topic_ref") for i in _load()["ideas"] if i.get("topic_ref") and i.get("status") != "dropped"}
    return refs


def from_topics(n: int = 6) -> list[dict]:
    """Surface n unused hooks from data/topics.json as ideas (no AI call), spread across voices."""
    try:
        topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        topics = []
    used = _used_topic_refs()
    by_voice: dict[str, list] = {}
    for t in topics:
        if t.get("ref") and t["ref"] not in used and t.get("hook"):
            by_voice.setdefault(t.get("voice") or "company", []).append(t)
    picked = []
    while len(picked) < n and any(by_voice.values()):
        for v in list(by_voice):
            if by_voice[v] and len(picked) < n:
                picked.append(by_voice[v].pop(0))
    saved = []
    for t in picked:
        idea = {"id": "idea-" + uuid.uuid4().hex[:10], "created_at": _now(), "origin": "topic",
                "topic_ref": t["ref"], "source_item_ids": [], "title": t["hook"][:90], "hook": t["hook"],
                "angle": "", "outline": [], "why_now": f"Unused hook {t['ref']} from the 90-day plan ({t.get('pillar')}).",
                "numbers": [], "status": "new", "post_id": None}
        idea.update(_validate_meta({"platform": t.get("platform") or "linkedin", "format": t.get("format"),
                                    "pillar": TOPIC_PILLAR_MAP.get(t.get("pillar"), t.get("pillar")),
                                    "voice": t.get("voice"), "job": t.get("job")}))
        idea["flags"] = guard.check(_idea_text(idea))
        saved.append(idea)
    with _lock:
        d = _load()
        d["ideas"].extend(saved)
        _save(d)
    return saved


# ------------------------------------------------------------------ to the new-post flow
def idea_to_post_brief(idea: dict | str) -> dict:
    """Prefill fields for the existing new-post flow (/new): platform, format, pillar, voice, hook,
    title, brief, job, topic_ref, idea_id. 'both' ideas start as the LinkedIn version."""
    if isinstance(idea, str):
        idea = get_idea(idea) or {}
    meta = _validate_meta(idea)
    platform = "linkedin" if meta["platform"] == "both" else meta["platform"]
    lines = []
    if idea.get("angle"):
        lines.append(f"Angle: {idea['angle']}")
    if idea.get("outline"):
        lines.append("Outline:\n" + "\n".join(f"- {x}" for x in idea["outline"]))
    if idea.get("why_now"):
        lines.append(f"Why now: {idea['why_now']}")
    if idea.get("numbers"):
        lines.append("Verified numbers you may quote (each appears in its public source post; say where it comes from, "
                     "e.g. 'a creator posted…'; never present it as Galvor data):\n" +
                     "\n".join(f"- {n['value']} {n.get('label') or ''} — \"{n.get('quote') or ''}\" ({n.get('url') or n['source_item_id']})"
                               for n in idea["numbers"]))
    else:
        lines.append("No verified numbers from the source posts: use only facts-bank numbers, or none.")
    if meta["platform"] == "both":
        lines.append(f"Also planned for Instagram (pillar {meta.get('pillar_instagram')}); write the LinkedIn version first.")
    lines.append("Closing CTA: " + ("\"Follow Galvor\"." if platform == "linkedin" else f"\"Follow {IG_HANDLE}\"."))
    for f in idea.get("flags") or []:
        lines.append(f"Watch out ({f['rule']}): {f['why']}")
    return {"platform": platform, "format": meta["format"], "pillar": meta["pillar"], "voice": meta["voice"], "hook": idea.get("hook") or "",
            "title": (idea.get("title") or idea.get("hook") or "New post")[:90], "brief": "\n\n".join(lines),
            "job": meta["job"], "topic_ref": idea.get("topic_ref") or "", "idea_id": idea.get("id")}
