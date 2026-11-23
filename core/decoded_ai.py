"""AI help for Decoded: issue ideas, a full draft in the exact house format, and a promo pack.

Writing is normally done by hand; these are optional assists. Honesty rules are enforced in code, not just asked for:
- The draft may only link URLs we hand it (Discover items or URLs the writer pastes).
- Any outside number must appear in the text of a source we hand it; any Galvor number must be in the facts bank.
  Everything else gets a [DATA NEEDED: …] marker, which blocks export until a person resolves it.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from . import ai, decoded
from .config import DATA
from .store import all_posts, blank_post, folder_of, now_iso, save_post

IDEAS_FILE = DATA / "decoded_ideas.json"
SPEC = DATA / "CONTENT_SPEC.md"
EXEMPLAR_FILE = DATA / "decoded_exemplar.md"      # Issue #4 in markup (written on first use)


def _facts() -> str:
    t = SPEC.read_text(encoding="utf-8")
    m = re.search(r"## 4\. Facts bank.*?(?=\n## 5\.)", t, re.S)
    return m.group(0) if m else ""


def _exemplar() -> str:
    if EXEMPLAR_FILE.exists():
        return EXEMPLAR_FILE.read_text(encoding="utf-8")
    for p in all_posts("newsletter"):
        nl = p.get("newsletter") or {}
        if nl.get("issue") == 4 and nl.get("markup"):
            EXEMPLAR_FILE.write_text(nl["markup"], encoding="utf-8")
            return nl["markup"]
    return ""


def _issues() -> list[dict]:
    out = []
    for p in all_posts("newsletter"):
        nl = p.get("newsletter") or {}
        out.append({"issue": nl.get("issue"), "date": p["date"], "title": p.get("title"), "status": p.get("status"), "id": p["id"]})
    return sorted(out, key=lambda r: (r["issue"] or 0))


def _sources(item_ids: list[str] | None, urls_text: str = "") -> list[dict]:
    """Discover items (and pasted URLs) the draft is allowed to cite."""
    srcs = []
    try:
        from . import discover
        items = discover.get_items(item_ids) if item_ids else [i for i in discover.items(relevant_only=True, sort="score", limit=12)]
        for it in items:
            srcs.append({"id": it["id"], "url": it["url"], "publisher": it.get("source") or it.get("source_kind"),
                         "author": it.get("author") or "", "date": (it.get("posted_at") or "")[:10],
                         "title": it.get("title") or (it.get("text") or "")[:90], "text": (it.get("text") or "")[:1500]})
    except Exception:
        pass
    for line in (urls_text or "").splitlines():
        m = re.search(r"(https?://\S+)", line)
        if m:
            note = line.replace(m.group(1), "").strip(" -–—:|")
            srcs.append({"id": "u" + uuid.uuid4().hex[:6], "url": m.group(1), "publisher": "", "author": "", "date": "",
                         "title": note[:120], "text": note})
    return srcs


# ---------------------------------------------------------------- ideas
def load_ideas() -> list[dict]:
    try:
        return json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_ideas(rows):
    IDEAS_FILE.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")


def generate_ideas(n: int = 5, item_ids: list[str] | None = None, steer: str = "") -> list[dict]:
    srcs = _sources(item_ids)
    past = "\n".join(f"#{r['issue']} ({r['date']}, {r['status']}): {r['title']}" for r in _issues())
    src_txt = "\n".join(f"[{s['id']}] {s['publisher']} {s['date']} — {s['title']} — {s['text'][:400]} ({s['url']})" for s in srcs)
    prompt = f"""You plan issues of "Decoded by Galvor", a fortnightly newsletter (every other Tuesday, from the Galvor LinkedIn page and by
email) for Indian D2C founders, CMOs, growth and creative leads. Galvor decodes why ads and creator videos work.
Goal of the newsletter: awareness — issues people forward, comment on and click. Each issue: a contrarian, specific title
in the house style (e.g. "Creative Diversity: Low. Why 30 New Ads Won't Fix It", "Fake Followers: 0%. Why Your Creator Still
Won't Sell", "False Bangers: Why Your Best Hook Isn't Always Your Best Ad"), a cold open with Sam (a recurring growth lead),
outside data with sources, what Galvor saw in its own data, a section on how Galvor approaches it, five moves for marketers
and leaders, a free-offer CTA.

Issues already planned or sent (don't repeat their angle):
{past}

Recent things people are posting about (you may build on them; cite only by [id]):
{src_txt or '(none)'}

Galvor facts you may rely on (only these numbers):
{_facts()[:2500]}

{('Steer from the editor: ' + steer) if steer else ''}
Return JSON: {{"ideas": [{{"title": "Decoded-style title (no issue number)", "dek": "one-paragraph italic standfirst",
"cold_open": "two sentences: the Sam scene", "why_now": "why this week", "sections": ["5-7 section headings in order"],
"galvor_data_needed": ["what Galvor's data must show — the team pulls it"], "source_ids": ["ids from the list you'd cite"],
"cta": "the free offer (audit, shortlist, decode)", "awareness_angle": "why people will forward/comment"}}]}} with {n} ideas."""
    data = ai._parse_json(ai.complete(prompt, what="Decoded: ideas"))
    rows = load_ideas()
    made = []
    valid = {s["id"]: s for s in srcs}
    for it in (data.get("ideas") or [])[:n]:
        if not it.get("title"):
            continue
        it["source_ids"] = [x for x in it.get("source_ids") or [] if x in valid]
        it["sources"] = [valid[x] | {"text": ""} for x in it["source_ids"]]
        it.update(id="di-" + uuid.uuid4().hex[:8], created_at=now_iso(), status="new")
        made.append(it)
    _save_ideas(made + rows)
    return made


def use_idea(idea_id: str, post_id: str) -> dict:
    """Put an idea into an issue (keeps the issue number, chain and date)."""
    rows = load_ideas()
    idea = next((r for r in rows if r["id"] == idea_id), None)
    p = next((q for q in all_posts("newsletter") if q["id"] == post_id), None)
    if not idea or not p:
        raise ValueError("Idea or issue not found")
    nl = p.setdefault("newsletter", {})
    meta, sections = decoded.parse(nl.get("markup") or "---\n---\n")
    n = nl.get("issue")
    title = f"Decoded #{n}: {idea['title']}"
    keep = [(h, ls) for h, ls in sections if h.lower().startswith(("next issue", "cta:", "how we did this", "sources"))]
    fm = {**meta, "issue": n, "title": title, "dek": idea.get("dek", "")}
    body = ["## Key takeaways", "", "- [DATA NEEDED: takeaway 1]", "- [DATA NEEDED: takeaway 2]", "- [DATA NEEDED: takeaway 3]"]
    for h in idea.get("sections") or []:
        body += ["", f"## {h}", ""]
        body.append(f"[DATA NEEDED: write this section. Cold open brief: {idea.get('cold_open', '')}]" if h.lower().startswith("monday")
                    else "[DATA NEEDED: write this section]")
    for h, ls in keep:
        body += ["", f"## {h}"] + ls
    md = "---\n" + "\n".join(f"{k}: {fm[k]}" for k in ("issue", "title", "dek", "author", "previous_title", "previous_url") if fm.get(k)) + "\n---\n\n" + "\n".join(body)
    nl.update(markup=re.sub(r"\n{3,}", "\n\n", md), idea_id=idea_id, data_needed=idea.get("galvor_data_needed"),
              allowed_sources=idea.get("sources") or [])
    p["title"] = title
    p["hook"] = idea["title"]
    if p.get("status") == "idea":
        p["status"] = "draft"
    save_post(p, note=f"Decoded idea {idea_id} used")
    idea["status"], idea["post_id"] = "used", p["id"]
    _save_ideas(rows)
    return p


def set_idea_status(idea_id: str, status: str) -> None:
    rows = load_ideas()
    for r in rows:
        if r["id"] == idea_id:
            r["status"] = status
    _save_ideas(rows)


# ---------------------------------------------------------------- full draft
NUM = re.compile(r"(?<![\w#\[])(\d[\d,.]*\s?%|[₹$]\s?\d[\d,.]*(?:\s?(?:crore|lakh|bn|billion|million|k))?|\d[\d,]{2,}(?:\.\d+)?)")


def _verify_numbers(md: str, allowed_text: str) -> tuple[str, int]:
    """Tag every number the model used that isn't in a source or the facts bank."""
    flagged = 0
    head, _, body = md.partition("\n---\n") if md.startswith("---") else ("", "", md)
    cut = body.lower().find("## how we did this")
    main, rest = (body[:cut], body[cut:]) if cut > 0 else (body, "")
    allowed = allowed_text.replace(",", "")

    def fix_sentence(sent: str) -> str:
        nonlocal flagged
        if sent.lstrip().startswith(("![", "caption:", "button:", "##")) or "DATA NEEDED" in sent:
            return sent
        bad = [x for x in NUM.findall(sent) if not re.fullmatch(r"(19|20)\d\d", x.strip()) and x.strip().replace(",", "") not in allowed]
        if bad:
            flagged += 1
            return sent.rstrip() + f" [DATA NEEDED: verify {', '.join(dict.fromkeys(b.strip() for b in bad))}]"
        return sent
    out_lines = []
    in_cold_open = False
    for line in main.split("\n"):
        if line.startswith("## "):
            in_cold_open = bool(re.match(r"## (monday|tuesday|wednesday|thursday|friday)", line.lower()))
            out_lines.append(line)
            continue
        if in_cold_open or not line.strip():
            out_lines.append(line)            # the Sam scene is an illustration, not a claim
            continue
        out_lines.append(" ".join(fix_sentence(s) for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(\[])", line)))
    return (head + "\n---\n" if head else "") + "\n".join(out_lines) + rest, flagged


def _only_allowed_links(md: str, urls: set[str]) -> tuple[str, int]:
    dropped = 0

    def repl(m):
        nonlocal dropped
        url = m.group(2)
        if url in urls or url.startswith(("https://galvor.ai", "https://talk.galvor.ai", "#")):
            return m.group(0)
        dropped += 1
        return f"{m.group(1)} [DATA NEEDED: source link]"
    return re.sub(r"\[([^\]]+)\]\(((?:https?://|#)[^)\s]+)\)", repl, md), dropped


def draft_issue(post_id: str, instruction: str = "", item_ids: list[str] | None = None, urls_text: str = "") -> dict:
    p = next((q for q in all_posts("newsletter") if q["id"] == post_id), None)
    if not p:
        raise ValueError("Issue not found")
    nl = p.setdefault("newsletter", {})
    current = nl.get("markup") or ""
    meta, _ = decoded.parse(current) if current else ({}, [])
    srcs = (nl.get("allowed_sources") or []) + _sources(item_ids, urls_text)
    seen, uniq = set(), []
    for s in srcs:
        if s["url"] not in seen:
            seen.add(s["url"])
            uniq.append(s)
    srcs = uniq[:20]
    src_txt = "\n".join(f"- {s.get('publisher', '')} ({s.get('date', '')}), \"{s.get('title', '')}\" {s['url']}\n  TEXT: {s.get('text', '')[:1200]}" for s in srcs)
    prompt = f"""Write one complete issue of "Decoded by Galvor" in Decoded markup. Match the EXAMPLE issue's structure, rhythm,
tone and length (about 1,900-2,500 words) exactly: front matter; ## Key takeaways (exactly 3 bullets); a cold open
"## Monday, H:MM a.m." with Sam, the recurring growth lead (3 short paragraphs, then a "> " italic one-line turn);
3-5 sections that move from what the industry says (linked sources) to what Galvor saw in its own data to how Galvor
approaches it ("### 1 …" numbered subheads where useful); "## The shift for marketers and leaders" with "Five moves Galvor
recommends, whatever tool you use." and five "- **Lead.** text" bullets; "## Next issue: …" with a two-sentence teaser;
"## CTA: …" with body and a "button: Label | https://talk.galvor.ai" line; "## How we did this"; "## Sources" as
"- Publisher (date), [title](url)" lines. Use "![alt](fig_01.png)" placeholders where a chart belongs, with alt text that
describes the chart in full sentences, followed by "caption: Source: …".

HARD RULES (they are checked in code):
- Link only these URLs. Never invent a link, a publisher or a study.
- An outside number may appear only if it is in a source's TEXT below; link that source in the same sentence.
- A Galvor number may appear only if it is in the FACTS. If the section needs Galvor data you don't have, write
  [DATA NEEDED: exactly what to pull] instead of a number.
- Never name a Galvor client. Plain, direct Indian-English. No hype words (unlock, game-changer, delve, seamless…).
- The newsletter's goal is awareness: a title and dek people want to forward, a cold open that feels familiar, at least one
  line worth quoting, and a closing question in the CTA body only if it's a real one.

FRONT MATTER TO KEEP: issue {nl.get('issue')}; title "{p.get('title')}"; author {meta.get('author') or 'Raj Dhakad, Founding AI Engineer, Galvor AI'};
previous_title {meta.get('previous_title', '')}; previous_url {meta.get('previous_url', '')}.
NEXT ISSUE: {nl.get('next_issue') or '[pick a natural next topic]'}

CURRENT DRAFT / BRIEF (build on it; keep anything a person already wrote):
{current[:9000]}

EDITOR'S INSTRUCTION: {instruction or '(none)'}

SOURCES YOU MAY CITE:
{src_txt or '(none — then use no outside numbers)'}

FACTS (the only Galvor numbers allowed):
{_facts()}

EXAMPLE ISSUE (Issue #4, sent 11 Nov 2026 — copy its format exactly, not its topic):
{_exemplar()[:16000]}

Return JSON: {{"markup": "the whole issue in Decoded markup, starting with ---"}}."""
    raw = ai.complete(prompt, max_tokens=24000, what="Decoded: write an issue")
    try:
        md = (ai._parse_json(raw).get("markup") or "").strip()
    except Exception:
        md = raw.strip()
    md = re.sub(r"^```\w*\n|\n```$", "", md).strip() + "\n"
    if not md.startswith("---"):
        raise ai.AIError("The AI didn't return Decoded markup. Try again.")
    allowed_text = _facts() + " " + " ".join(s.get("text", "") + " " + s.get("title", "") for s in srcs)
    md, n_links = _only_allowed_links(md, {s["url"] for s in srcs})
    md, n_nums = _verify_numbers(md, allowed_text)
    hist = nl.setdefault("history", [])
    if current:
        hist.insert(0, {"at": now_iso(), "markup": current, "why": "before AI draft"})
        del hist[10:]
    nl["markup"] = md
    nl["allowed_sources"] = [{k: v for k, v in s.items() if k != "text"} for s in srcs]
    if p.get("status") == "idea":
        p["status"] = "draft"
    save_post(p, note=f"AI draft ({n_nums} number(s) and {n_links} link(s) flagged for checking)")
    return {"flagged_numbers": n_nums, "dropped_links": n_links, "words": decoded.word_count(md)}


# ---------------------------------------------------------------- promo pack (awareness)
def promo_pack(post_id: str) -> dict:
    """From a finished issue: LinkedIn share text + subject lines, an Instagram story on the day, an Instagram carousel
    of the takeaways in the next free slot, and an amplification kit (Raj reshare + comment starters for the team)."""
    from .reminders import next_free_slot
    p = next((q for q in all_posts("newsletter") if q["id"] == post_id), None)
    if not p:
        raise ValueError("Issue not found")
    nl = p.get("newsletter") or {}
    meta, sections = decoded.parse(nl.get("markup") or "")
    n = nl.get("issue")
    short = re.sub(r"^Decoded #\d+:\s*", "", meta.get("title", p.get("title", "")))
    takeaways = [ln[2:].strip() for h, ls in sections if h.lower() == "key takeaways" for ln in ls if ln.startswith("- ")]
    plain = lambda s: re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).replace("**", "")
    takeaways = [plain(t) for t in takeaways][:3]
    created = []
    try:
        data = ai._parse_json(ai.complete(f"""For this issue of Decoded by Galvor, write promotion copy aimed at awareness (views, comments, clicks).
Title: {short}
Standfirst: {meta.get('dek', '')}
Takeaways: {json.dumps(takeaways, ensure_ascii=False)}
Return JSON: {{"subject_lines": [3 email subject lines under 60 chars], "preview_text": "under 90 chars",
"linkedin_share": "the text posted with the LinkedIn newsletter from the Galvor page: hook line under 200 chars, 3-5 short
lines, no hashtags in the body, end by asking readers to subscribe", "raj_reshare": "Raj's 'repost with your thoughts' text, first person, 2-4 lines",
"comment_starters": ["3 genuine first comments teammates could leave, each a different angle, no praise-only comments"]}}
Rules: no invented numbers (only numbers in the takeaways), no client names, no hype words."""))
    except ai.AIError as e:
        data = {"error": str(e)}
    if data.get("linkedin_share"):
        p["caption"] = data["linkedin_share"]
    nl.update(subject_lines=data.get("subject_lines") or nl.get("subject_lines"), preview_text=data.get("preview_text") or nl.get("preview_text"),
              amplify={"raj_reshare": data.get("raj_reshare", ""), "comment_starters": data.get("comment_starters") or []})
    p["newsletter"] = nl
    save_post(p, note="Promo pack generated")
    # Instagram story on the issue day, 12:30
    if takeaways:
        story = blank_post("instagram", p["date"], time="12:30", voice="company", format="story", pillar="Newsletter", job="Attract",
                           title=f"Story pack: Decoded #{n} is out", hook=f"Decoded #{n} is out", status="draft",
                           caption=f"Decoded #{n}: {short}. Link in bio.", alt_text=f"Instagram story frames announcing Decoded issue {n}: {short}.",
                           hashtags=["#KnowWhyYourAdsWin"])
        story["creative"] = {"size": "story", "slides": [
            {"layout": "cover", "kicker": f"Decoded · Issue #{n}", "headline": short[:90], "sub": "Out now. Link in bio."},
            {"layout": "text", "kicker": "One thing from this issue", "headline": takeaways[0][:78], "body": ""},
            {"layout": "cta", "headline": "Get Decoded every other Tuesday", "sub": "Free. For D2C growth and creative teams.",
             "actions": ["Follow @galvor.ai", "Link in bio to subscribe"]}]}
        created.append(save_post(story, note=f"Promo pack for Decoded #{n}")["id"])
        car = blank_post("instagram", p["date"], voice="company", format="carousel", pillar="Newsletter", job="Educate",
                         title=f"Decoded #{n} in three slides", hook=short, status="draft",
                         caption=f"{short}\n\n" + "\n\n".join(f"{i}. {t}" for i, t in enumerate(takeaways, 1)) +
                         f"\n\nThe full issue of Decoded is free. Link in bio.\n\nFollow @galvor.ai for more.",
                         alt_text=f"Carousel of the three takeaways from Decoded issue {n}.",
                         hashtags=["#performancemarketing", "#d2cindia", "#creativestrategy", "#KnowWhyYourAdsWin"])
        car["creative"] = {"size": "feed", "slides": [{"layout": "cover", "kicker": f"Decoded · Issue #{n}", "headline": short[:95], "sub": "Swipe for the three takeaways →"}] +
                           [{"layout": "text", "kicker": f"Takeaway {i}", "headline": t.split(".")[0][:78], "body": t[:300]} for i, t in enumerate(takeaways, 1)] +
                           [{"layout": "cta", "headline": "Read the full issue free", "sub": "Decoded by Galvor, every other Tuesday.",
                             "actions": ["Follow @galvor.ai", "Save this", "Link in bio"]}]}
        slot = next_free_slot(car)
        from datetime import date as _d, timedelta as _td
        issue_day = _d.fromisoformat(p["date"])
        if slot and (_d.fromisoformat(slot[0]) - issue_day).days <= 14:
            car["date"], car["time"] = slot
        else:   # the plan is full: an extra on the first day after the issue with no other Instagram feed post
            busy = {q["date"] for q in all_posts("instagram") if q.get("format") != "story" and q.get("status") != "skipped"}
            d = issue_day + _td(days=1)
            while d.isoformat() in busy and (d - issue_day).days < 10:
                d += _td(days=1)
            car["date"], car["time"] = d.isoformat(), "19:00"
            car["notes"] = "Extra post from the promo pack: the regular carousel slots are full. Swap it with a planned post or skip it."
        created.append(save_post(car, note=f"Promo pack for Decoded #{n}")["id"])
    return {"created": created, "ai": "ok" if not data.get("error") else data["error"]}
