"""References: links, PDFs, images and notes that KC (or anyone) shares for the team to learn from.

Each one is saved by date under data/references/<date>_<slug>/ with whatever was shared (source.txt, the
uploaded file) and a summary.json: what it says, the main points, how Galvor can use it, what to change, and
what to be careful about. The summary is written either by the Studio's AI (costs money, shown on Costs) or in
the Claude terminal (no API charge); items waiting for one show as "To read".
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.request
from datetime import date, datetime
from pathlib import Path

from .config import DATA

DIR = DATA / "references"
INDEX = DIR / "index.json"
MAX_CHARS = 120_000          # more than this is not sent to the AI; the summary says so
UA = "Mozilla/5.0 (compatible; reference-reader)"


def _load() -> list[dict]:
    try:
        d = json.loads(INDEX.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48] or "reference"


def all_refs() -> list[dict]:
    items = _load()
    for it in items:
        f = DIR / it["folder"] / "summary.json"
        try:
            it["summary"] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            it["summary"] = None
        it["status"] = "read" if it["summary"] else "to_read"
    return sorted(items, key=lambda r: (r.get("date", ""), r.get("added", "")), reverse=True)


def get(rid: str) -> dict | None:
    return next((r for r in all_refs() if r["id"] == rid), None)


def by_day() -> list[tuple[str, list[dict]]]:
    out: dict[str, list[dict]] = {}
    for r in all_refs():
        out.setdefault(r.get("date", ""), []).append(r)
    return sorted(out.items(), reverse=True)


# ---------------------------------------------------------------- reading what was shared
def _html_to_text(raw: str) -> tuple[str, str]:
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    raw = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<(br|/p|/div|/h[1-6]|/li|/tr)[^>]*>", "\n", raw, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"[ \t\r\f]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return title, text


def _youtube(url: str, folder: Path) -> tuple[str, str]:
    """Title and spoken words of a YouTube video, via yt-dlp captions. Empty strings if that fails."""
    try:
        t = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(title)s | %(channel)s | %(duration_string)s", url],
                           capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace")
        title = (t.stdout or "").strip().splitlines()[0] if t.stdout.strip() else ""
        subprocess.run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*",
                        "--sub-format", "vtt", "-o", str(folder / "captions"), url],
                       capture_output=True, timeout=180)
        vtts = sorted(folder.glob("captions*.vtt"))
        if not vtts:
            return title, ""
        out, last = [], None
        for line in vtts[0].read_text(encoding="utf-8", errors="replace").splitlines():
            if "-->" in line or not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:")):
                continue
            s = re.sub(r"<[^>]+>", "", line).strip()
            if s and s != last:
                out.append(s)
                last = s
        for v in vtts:
            v.unlink()
        return title, " ".join(out)
    except (OSError, subprocess.SubprocessError):
        return "", ""


def _fetch(url: str, folder: Path) -> tuple[str, str, str]:
    """(title, text, problem). Never raises: a link we can't read is still saved, with the reason."""
    if re.search(r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts)", url):
        title, text = _youtube(url, folder)
        return title, text, "" if text else "Couldn't get this video's captions. Paste the transcript or your notes."
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = r.headers.get("Content-Type", "")
            data = r.read(8_000_000)
    except Exception as e:  # network, 4xx, 5xx, bad URL
        return "", "", f"Couldn't open the link ({str(e)[:120]}). Paste the text instead."
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        f = folder / "source.pdf"
        f.write_bytes(data)
        return "", _pdf_text(f), ""
    title, text = _html_to_text(data.decode("utf-8", errors="replace"))
    problem = ""
    if "linkedin.com" in url and len(text) < 1500:
        problem = "LinkedIn shows only a little of a post without sign-in. Paste the post text to get a full summary."
    return title, text, problem


def _pdf_text(f: Path) -> str:
    try:
        import pymupdf
    except ImportError:
        return ""
    try:
        with pymupdf.open(f) as doc:
            return "\n\n".join(page.get_text() for page in doc).strip()
    except Exception:
        return ""


def add(*, url: str = "", text: str = "", title: str = "", shared_by: str = "KC", day: str = "",
        note: str = "", upload=None) -> dict:
    """Save one shared item. `upload` is a werkzeug FileStorage (pdf, image, txt, md)."""
    day = day or date.today().isoformat()
    url, text = (url or "").strip(), (text or "").strip()
    items = _load()
    rid = f"ref{datetime.now().strftime('%y%m%d%H%M%S')}{len(items) % 100:02d}"
    name = title or (upload.filename if upload and upload.filename else "") or url or text[:50]
    folder_name = f"{day}_{_slug(name)}"
    n = 2
    while (DIR / folder_name).exists():
        folder_name = f"{day}_{_slug(name)}-{n}"
        n += 1
    folder = DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    kind, problem, files = "note", "", []
    if upload and upload.filename:
        safe = re.sub(r"[^\w.-]", "_", upload.filename)
        f = folder / safe
        upload.save(f)
        files.append(safe)
        ext = safe.lower().rsplit(".", 1)[-1]
        if ext == "pdf":
            kind = "pdf"
            text = text or _pdf_text(f)
            if not text:
                problem = "This PDF has no readable text (it may be scanned). Open it in the Claude terminal for a summary."
        elif ext in ("png", "jpg", "jpeg", "webp", "gif"):
            kind = "image"
            if not text:
                problem = "Images are read in the Claude terminal. Ask there for a summary of this reference."
        else:
            kind = "file"
            try:
                text = text or f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    if url:
        kind = "video" if re.search(r"youtu\.?be", url) else ("link" if kind == "note" else kind)
        if not text:
            t, text, problem = _fetch(url, folder)
            title = title or t
    if text:
        (folder / "source.txt").write_text(text, encoding="utf-8")
    item = {"id": rid, "date": day, "added": datetime.now().isoformat(timespec="seconds"),
            "title": (title or name)[:160], "url": url, "kind": kind, "shared_by": shared_by or "KC",
            "note": note, "folder": folder_name, "files": files, "chars": len(text), "problem": problem}
    items.append(item)
    _save(items)
    return item


def add_text(rid: str, text: str) -> None:
    r = get(rid)
    if r and text.strip():
        (DIR / r["folder"] / "source.txt").write_text(text.strip(), encoding="utf-8")
        items = _load()
        for it in items:
            if it["id"] == rid:
                it["chars"], it["problem"] = len(text.strip()), ""
        _save(items)


def source_text(r: dict) -> str:
    try:
        return (DIR / r["folder"] / "source.txt").read_text(encoding="utf-8")
    except OSError:
        return ""


def delete(rid: str) -> None:
    """Remove from the list. The folder stays on disk (rename with a leading underscore) so nothing shared is lost."""
    items = _load()
    for it in items:
        if it["id"] == rid:
            f = DIR / it["folder"]
            if f.exists():
                f.rename(DIR / ("_removed_" + it["folder"]))
    _save([it for it in items if it["id"] != rid])


def read_image(rid: str) -> str:
    """Gemini reads an image reference (a screenshot of a post, a chart, a slide) and writes out everything on it,
    so the deep dive can run without the terminal. One paid Gemini call, logged on Costs."""
    import os
    from . import ai, ledger
    r = get(rid)
    img = next((f for f in (r or {}).get("files") or [] if f.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp")), None)
    if not img:
        raise ai.AIError("This reference has no image to read.")
    key, model = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL")
    if not key or not model:
        raise ai.AIError("Set GEMINI_API_KEY and GEMINI_MODEL in studio/.env to read images here.")
    from google.genai import types
    data = (DIR / r["folder"] / img).read_bytes()
    mime = {"png": "image/png", "webp": "image/webp"}.get(img.lower().rsplit(".", 1)[-1], "image/jpeg")
    try:
        resp = ai._gemini(key).models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime),
                      "Write out everything on this image, in reading order: every heading, sentence, number, chart "
                      "label and name, exactly as shown. Then describe any chart or diagram in two sentences. "
                      "Do not add opinions or anything that is not on the image."])
    except Exception as e:
        raise ai.AIError(f"Gemini couldn't read the image: {str(e)[:200]}") from e
    text = (resp.text or "").strip()
    try:
        um = resp.usage_metadata
        ledger.record("gemini", "Read an image reference", 0.0, kind="ai", cap=False, model=model,
                      tokens={"in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0},
                      note="Gemini price not in the table; see your Google bill")
    except Exception:
        pass
    if len(text) < 40:
        raise ai.AIError("Gemini returned almost nothing for this image.")
    add_text(rid, text)
    return text


# ---------------------------------------------------------------- the deep dive
SUMMARY_KEYS = ("says", "points", "use", "changes", "caution")

PROMPT = """You are reading something a senior advisor shared with Galvor's marketing team. Read it the way a
skeptical marketing head would: what does it really say, what is proven, and what should we do about it.

Galvor sells creative marketing intelligence to D2C performance marketing teams (India first, also US and UK).
Marketing runs LinkedIn posts from three people (Sunil: executive, Raj: builder, Shrutik: client reality) and
the company page, Instagram, and a weekly newsletter called Decoded. Rules we keep: no client names or numbers
without permission, never claim a competitor's spend or ROAS, no invented numbers, no engagement pods.

Return ONE JSON object, plain words, no jargon:
{"says": "3 to 5 sentences: what this piece says and who made it",
 "points": ["the 5 to 9 points worth remembering, each one sentence, with the number or example it gave"],
 "use": ["3 to 6 specific ways Galvor can use this: name the channel, voice or Studio page it applies to"],
 "changes": ["2 to 5 concrete changes to make this month, each starting with a verb"],
 "caution": ["what is unproven, self-serving, out of date, or against our rules; say 'nothing' only if true"]}

Title: {title}
Link: {url}
Shared by: {shared_by}
{cut}
CONTENT:
{text}"""


def summarise(rid: str) -> dict:
    """Ask the Studio's AI for the deep dive. Raises ai.AIError with a plain message if it can't."""
    from . import ai
    r = get(rid)
    if not r:
        raise ai.AIError("That reference no longer exists.")
    text = source_text(r)
    if len(text) < 600 and r.get("kind") == "image":
        text = read_image(rid)          # Gemini reads the picture first
    if len(text) < 200:
        raise ai.AIError("There isn't enough text saved for this one. Paste the text, or ask for the summary in the Claude terminal.")
    cut = ""
    if len(text) > MAX_CHARS:
        cut = f"NOTE: the content is {len(text):,} characters; only the first {MAX_CHARS:,} are below. Say so in 'caution'."
        text = text[:MAX_CHARS]
    prompt = (PROMPT.replace("{title}", r["title"]).replace("{url}", r.get("url") or "(none)")
              .replace("{shared_by}", r.get("shared_by") or "").replace("{cut}", cut).replace("{text}", text))
    data = ai._parse_json(ai.complete(prompt, max_tokens=6000, what="Reference deep dive"))
    save_summary(rid, data, by="Studio AI")
    return data


def save_summary(rid: str, data: dict, by: str = "Claude terminal") -> None:
    r = get(rid)
    if not r:
        return
    out = {k: data.get(k) or ([] if k != "says" else "") for k in SUMMARY_KEYS}
    out["by"], out["at"] = by, datetime.now().isoformat(timespec="seconds")
    (DIR / r["folder"] / "summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
