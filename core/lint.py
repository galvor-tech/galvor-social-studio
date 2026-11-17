"""Quality gate. Every post is checked before it can be approved / scheduled.

Severity: "error" blocks approval; "warn" is shown but doesn't block.
"""
from __future__ import annotations

import json
import re

from .config import FORMATS, VOICES

LIMITS = {
    "linkedin": {"caption": 3000, "hashtags": 5, "see_more": 210, "first_comment": 1250},
    "instagram": {"caption": 2200, "hashtags": 5, "see_more": 125, "first_comment": 2200},
    "newsletter": {"caption": 100000, "hashtags": 0, "see_more": 0, "first_comment": 0},
}

BANNED = [
    "excited to share", "thrilled to announce", "game-changer", "game changer", "revolutionize", "revolutionise",
    "unlock the power", "unleash", "delve", "in today's fast-paced", "in today’s fast-paced", "synergy",
    "leverage synergies", "cutting-edge", "seamlessly", "elevate your", "next-level", "10x your",
    "guaranteed results", "skyrocket",
]
# client/customer names: need written permission before naming (plan rule)
CLIENTS = ["XTEND", "C4 Original", "Pure Nutrition", "Physics Wallah", "halo care", "Blue Nectar", "MaisonX",
           "GMR", "AngelOne", "Angel One", "Palladium", "Gritzo", "HealthKart", "Traya", "Fazlani", "Sopariwala",
           "Kreedo", "Carvix", "Glowfolk", "Comet"]
COMPETITOR_SPEND = re.compile(r"\b(spent|spends|spending|roas of|budget of)\b[^.]{0,40}(₹|\$|rs\.?|lakh|crore|million)", re.I)

HEADLINE_MAX = {"cover": 95, "statement": 110, "text": 80, "stat": 90, "list": 70, "compare": 60,
                "poll": 90, "festival": 70, "cta": 80}
LAYOUTS = set(HEADLINE_MAX)


def _issue(sev, field, msg):
    return {"severity": sev, "field": field, "message": msg}


def lint_post(p: dict) -> list[dict]:
    out: list[dict] = []
    plat = p.get("platform")
    lim = LIMITS.get(plat, LIMITS["linkedin"])
    cap = p.get("caption") or ""
    fmt = p.get("format")

    if not p.get("date"):
        out.append(_issue("error", "date", "No publish date."))
    else:
        try:
            from datetime import date as _date
            if plat != "newsletter" and _date.fromisoformat(p["date"]).weekday() >= 5:
                out.append(_issue("warn", "date", "This falls on a weekend. Posting is Monday to Friday: move it to a weekday."))
        except ValueError:
            pass
    if fmt not in FORMATS.get(plat, []):
        out.append(_issue("error", "format", f"Format “{fmt}” isn't valid for {plat}."))
    if p.get("voice") not in VOICES:
        out.append(_issue("error", "voice", "Unknown voice / profile."))
    if plat == "instagram" and p.get("voice") != "company":
        out.append(_issue("error", "voice", "Instagram posts go out from @galvor.ai (company)."))

    # caption
    if plat != "newsletter":
        if not cap.strip():
            out.append(_issue("error", "caption", "Caption is empty."))
        if len(cap) > lim["caption"]:
            out.append(_issue("error", "caption", f"Caption is {len(cap)} chars; limit is {lim['caption']}."))
        first = cap.strip().split("\n")[0] if cap.strip() else ""
        if first and len(first) > lim["see_more"]:
            out.append(_issue("warn", "caption", f"Opening line is {len(first)} chars; it will be cut before “see more” (~{lim['see_more']})."))
        low = cap.lower()
        for b in BANNED:
            if b in low:
                out.append(_issue("error", "caption", f"Banned phrase: “{b}”."))
        if re.search(r"https?://", cap) and plat == "linkedin":
            out.append(_issue("warn", "caption", "Link in the post body cuts reach — move it to the first comment."))
        if re.search(r"https?://", cap) and plat == "instagram":
            out.append(_issue("warn", "caption", "Links aren't clickable in Instagram captions — use “link in bio”."))
        if "  " in cap.replace("\n", ""):
            out.append(_issue("warn", "caption", "Double spaces in caption."))
        if cap.count("*") % 2:
            out.append(_issue("warn", "caption", "Stray “*” in caption (LinkedIn/Instagram don't render markdown)."))
        if re.search(r"\*\*[^*]+\*\*", cap):
            out.append(_issue("error", "caption", "Markdown bold (**…**) won't render on social — remove it."))
        if "TODO" in cap or "[" in cap and "]" in cap and re.search(r"\[(insert|add|name|link|tbd)[^\]]*\]", cap, re.I):
            out.append(_issue("error", "caption", "Placeholder left in caption."))
        if COMPETITOR_SPEND.search(cap):
            out.append(_issue("warn", "caption", "Looks like a spend/ROAS claim — never claim a competitor's spend from public data."))
        for c in CLIENTS:
            if re.search(rf"\b{re.escape(c)}\b", cap + " " + str(p.get("creative")), re.I):
                out.append(_issue("warn", "caption", f"Names “{c}” — needs written client permission (or anonymise)."))
                break

    # warnings learned from 63 sales meetings (ported from galvor-cms): they flag, a person decides
    if plat != "newsletter" and cap.strip():
        try:
            from .guard import check as _guard
            for g in _guard(cap):
                if g.get("rule") != "client-name":           # client names are already checked above
                    out.append(_issue("warn", "caption", f"{g['message']} ({g.get('why', '')})".strip(" ()")))
        except Exception:
            pass

    if plat == "newsletter" and (p.get("newsletter") or {}).get("markup"):
        from .decoded import check as _dcheck
        from .store import folder_of as _fo
        try:
            imgs = _fo(p) / "images" if p.get("_folder") else None
        except Exception:
            imgs = None
        for i in _dcheck(p["newsletter"]["markup"], imgs):
            out.append(_issue(i["severity"], "newsletter", "Decoded: " + i["message"]))
        return out

    if plat == "newsletter":
        low = cap.lower()
        for b in BANNED:
            if b in low:
                out.append(_issue("error", "caption", f"Banned phrase: “{b}”."))
        if re.search(r"\[DATA NEEDED", cap):
            out.append(_issue("error", "caption", "Data placeholder in the public intro."))
        draft = ((p.get("newsletter") or {}).get("draft_markdown") or "")
        n = len(re.findall(r"\[DATA NEEDED", draft))
        if n:
            out.append(_issue("warn", "newsletter", f"{n} [DATA NEEDED] placeholder(s) in the draft — fill before sending."))

    # brand rule: the call to follow is always Galvor, never an individual
    person_follow = re.compile(r"\bfollow (raj|sunil|shrutik|kc)\b|\bfollow (me|him|her|them|along|for)\b", re.I)
    for field, text in (("caption", cap), ("first_comment", p.get("first_comment") or ""),
                        ("creative", json.dumps((p.get("creative") or {}).get("slides") or [], ensure_ascii=False)),
                        ("script", json.dumps((p.get("script") or {}).get("scenes") or [], ensure_ascii=False))):
        if person_follow.search(text):
            out.append(_issue("error", field, "CTA must ask people to follow Galvor (LinkedIn) / @galvor.ai (Instagram), never an individual."))
    _slides = (p.get("creative") or {}).get("slides") or []
    if _slides and _slides[-1].get("layout") == "cta":
        last = _slides[-1]
        if not re.search(r"follow (galvor|@galvor\.ai)", " ".join([last.get("headline") or "", last.get("sub") or ""] + list(last.get("actions") or [])), re.I):
            out.append(_issue("error", "creative", "Closing CTA slide must include “Follow Galvor” (or “Follow @galvor.ai” on Instagram)."))

    # emoji that Windows Chrome can't render in creatives (flags show as letters)
    for i, s in enumerate((p.get("creative") or {}).get("slides") or [], 1):
        if re.search(r"[\U0001F1E6-\U0001F1FF]", json.dumps(s, ensure_ascii=False)):
            out.append(_issue("error", "creative", f"Slide {i}: flag emoji renders as letters in images — use ✨ or text instead."))

    # hashtags
    tags = p.get("hashtags") or []
    if len(tags) > lim["hashtags"]:
        out.append(_issue("error", "hashtags", f"{len(tags)} hashtags; keep to {lim['hashtags']} or fewer."))
    for t in tags:
        if not re.fullmatch(r"#?[A-Za-z0-9_]+", t):
            out.append(_issue("error", "hashtags", f"Invalid hashtag “{t}” (letters, numbers, _ only)."))
    if plat == "linkedin" and p.get("first_comment") and len(p["first_comment"]) > lim["first_comment"]:
        out.append(_issue("error", "first_comment", "First comment exceeds 1,250 chars."))

    # creative
    slides = (p.get("creative") or {}).get("slides") or []
    needs_visual = fmt in ("image", "carousel", "reel", "story") or (plat == "instagram")
    if needs_visual and not slides:
        out.append(_issue("error", "creative", "No slides — this format needs a visual."))
    if fmt == "carousel" and len(slides) < 3:
        out.append(_issue("warn", "creative", "Carousels perform best with 5–10 slides."))
    if fmt == "carousel" and len(slides) > (20 if plat == "instagram" else 300):
        out.append(_issue("error", "creative", "Too many slides (Instagram max 20)."))
    if fmt == "image" and len(slides) > 1:
        out.append(_issue("warn", "creative", "Single-image format but more than one slide — switch to carousel?"))
    for i, s in enumerate(slides, 1):
        lay = s.get("layout")
        if lay not in LAYOUTS:
            out.append(_issue("error", "creative", f"Slide {i}: unknown layout “{lay}”."))
            continue
        h = re.sub(r"[*]", "", str(s.get("headline") or s.get("greeting") or ""))
        if not h.strip():
            out.append(_issue("error", "creative", f"Slide {i}: headline is empty."))
        if len(h) > HEADLINE_MAX[lay]:
            out.append(_issue("warn", "creative", f"Slide {i}: headline is {len(h)} chars (max ~{HEADLINE_MAX[lay]} for {lay}); it may look cramped."))
        if str(s.get("headline", "")).count("*") % 2:
            out.append(_issue("error", "creative", f"Slide {i}: unbalanced * highlight markers."))
        if lay == "stat" and not s.get("stat"):
            out.append(_issue("error", "creative", f"Slide {i}: stat layout needs a number."))
        if lay == "stat" and not s.get("source"):
            out.append(_issue("error", "creative", f"Slide {i}: every number needs a source line."))
        if lay == "list" and not (2 <= len(s.get("items") or []) <= 6):
            out.append(_issue("error", "creative", f"Slide {i}: list needs 2–6 items."))
        if lay == "poll" and not (2 <= len(s.get("options") or []) <= 4):
            out.append(_issue("error", "creative", f"Slide {i}: poll needs 2–4 options."))
        if lay == "compare" and (not s.get("left") or not s.get("right")):
            out.append(_issue("error", "creative", f"Slide {i}: compare needs both columns."))
    if slides and not p.get("images"):
        out.append(_issue("warn", "images", "Images not rendered yet — click “Render images”."))
    if slides and not (p.get("alt_text") or "").strip():
        out.append(_issue("warn", "alt_text", "Add alt text for accessibility."))

    # poll
    if fmt == "poll":
        poll = p.get("poll") or {}
        opts = poll.get("options") or []
        if not poll.get("question"):
            out.append(_issue("error", "poll", "Poll question missing."))
        elif len(poll["question"]) > 140:
            out.append(_issue("error", "poll", "LinkedIn poll question max 140 chars."))
        if not (2 <= len(opts) <= 4):
            out.append(_issue("error", "poll", "LinkedIn polls need 2–4 options."))
        for o in opts:
            if len(o) > 30:
                out.append(_issue("error", "poll", f"Poll option “{o}” is over 30 chars (LinkedIn limit)."))

    # video / reel script
    if fmt in ("video", "reel"):
        sc = p.get("script") or {}
        if not sc.get("scenes"):
            out.append(_issue("error", "script", "Video/Reel needs a scene-by-scene script."))
    return out


def has_errors(issues: list[dict]) -> bool:
    return any(i["severity"] == "error" for i in issues)
