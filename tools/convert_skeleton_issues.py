"""Convert the old 'writing brief' skeleton drafts (#9, #11, #12, #13) into Decoded markup with the brief kept
inside [DATA NEEDED: …] markers, so the writer sees what each section must cover and export stays blocked until written."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import decoded  # noqa: E402
from core.store import all_posts, save_post  # noqa: E402


def convert(p):
    nl = p["newsletter"]
    old_meta, old_sections = decoded.parse(nl["markup"])
    draft = nl.get("draft_markdown") or ""
    parts = re.split(r"^\*\*(.+?)\*\*\s*", draft, flags=re.M)
    note = re.search(r"^\*([^*].+?)\*$", draft, re.M)
    body = ["## Key takeaways", ""]
    sections = []
    for lead, text in zip(parts[1::2], parts[2::2]):
        text = " ".join(text.split())
        lead_l = lead.lower()
        if lead_l.startswith("key takeaways"):
            items = re.findall(r"\d+\.\s+(.+?)(?=\s+\d+\.\s|$)", text)
            body += [f"- {t.strip()}" for t in items]
        elif lead_l.startswith("opening"):
            sections += ["", "## Monday, 9:40 a.m.", "", f"[DATA NEEDED: write the cold open (3 short paragraphs + an italic turn). Brief: {text}]"]
        elif lead_l.startswith("section"):
            title = re.sub(r"^section \d+\s*[—-]\s*", "", lead, flags=re.I).rstrip(".:")
            if title.lower().startswith("the shift for marketers and leaders"):
                sections += ["", "## The shift for marketers and leaders", "", "Five moves Galvor recommends, whatever tool you use.", ""]
                sections += [f"- **[DATA NEEDED: move {i}].** One or two sentences." for i in range(1, 6)]
                sections += ["", f"[DATA NEEDED: brief for the five moves: {text}]"]
            else:
                sections += ["", f"## {title}", "", f"[DATA NEEDED: write this section. Brief: {text}]"]
        elif lead_l.startswith(("close", "template")):
            sections += ["", f"[DATA NEEDED: {lead.rstrip(':')} — {text}]"]
    keep = [(h, ls) for h, ls in old_sections if h.lower().startswith(("next issue", "cta:", "how we did this", "sources"))]
    meta = old_meta
    meta["dek"] = "[DATA NEEDED: one-paragraph standfirst in Decoded style]"
    fm = ["---"] + [f"{k}: {meta[k]}" for k in ("issue", "title", "dek", "author", "previous_title", "previous_url") if k in meta] + ["---", ""]
    tail = []
    for h, ls in keep:
        tail += ["", f"## {h}"] + ls
    md = "\n".join(fm + body + sections + tail)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    nl["markup"] = md
    if note:
        p["notes"] = f"Writer's brief: {note.group(1)}\n\n" + (p.get("notes") or "")
    save_post(p, note="Skeleton brief converted to Decoded markup")
    return decoded.word_count(md)


for p in all_posts("newsletter"):
    nl = p.get("newsletter") or {}
    if nl.get("issue") in (9, 11, 12, 13) and "**Section 1" in (nl.get("draft_markdown") or ""):
        print("#", nl["issue"], convert(p), "words (mostly briefs inside [DATA NEEDED])")
