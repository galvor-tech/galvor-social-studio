"""Folder-based content store.

content/<platform>/<YYYY-MM>/<YYYY-MM-DD>_<slug>/
    post.json          ← source of truth
    caption.txt        ← ready-to-paste post text (+ hashtags)
    first_comment.txt
    script.md          ← video / reel script (if any)
    images/slide_XX.png, carousel.pdf
"""
from __future__ import annotations

import io
import json
import re
import shutil
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import CONTENT, MONTHLY_THEMES, PLATFORMS, STATUSES, VOICES

_lock = threading.RLock()
PREFIX = {"linkedin": "li", "instagram": "ig", "newsletter": "nl"}


def slugify(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[*“”\"'’]", "", text.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:maxlen].rstrip("-")) or "post"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _folder_for(post: dict) -> Path:
    d = post["date"]
    return CONTENT / post["platform"] / d[:7] / f"{d}_{post['slug']}"


def blank_post(platform: str, day: str, **kw) -> dict:
    p = {
        "id": "", "slug": "", "platform": platform, "date": day, "time": kw.get("time", "09:00"),
        "voice": "company", "pillar": "", "job": "Attract", "format": "image", "series": "",
        "title": "", "hook": "", "status": "idea", "festival": None, "theme": MONTHLY_THEMES.get(day[:7], ""),
        "caption": "", "first_comment": "", "hashtags": [], "alt_text": "", "cta": "",
        "script": None, "poll": None, "creative": {"size": "feed", "slides": []},
        "images": [], "notes": "", "approvals": [], "metrics": {}, "published_url": "", "published_at": "",
        "publish_log": [], "created_at": now_iso(), "updated_at": now_iso(),
    }
    p.update(kw)
    return p


# ---------------------------------------------------------------- read
def all_posts(platform: str | None = None) -> list[dict]:
    out = []
    plats = [platform] if platform else PLATFORMS
    for pl in plats:
        base = CONTENT / pl
        if not base.exists():
            continue
        for f in base.glob("*/*/post.json"):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                p["_folder"] = str(f.parent)
                out.append(p)
            except (json.JSONDecodeError, OSError):
                continue
    out.sort(key=lambda p: (p.get("date", ""), p.get("time", ""), p.get("platform", "")))
    return out


def get_post(pid: str) -> dict | None:
    for p in all_posts():
        if p.get("id") == pid:
            return p
    return None


def folder_of(post: dict) -> Path:
    return Path(post["_folder"]) if post.get("_folder") else _folder_for(post)


# ---------------------------------------------------------------- write
def _caption_with_tags(post: dict) -> str:
    cap = (post.get("caption") or "").rstrip()
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in post.get("hashtags") or [])
    return f"{cap}\n\n{tags}".strip() if tags and tags not in cap else cap


def script_markdown(post: dict) -> str:
    sc = post.get("script") or {}
    if not sc or not sc.get("scenes"):
        return ""
    lines = [f"# {post.get('title') or post.get('hook')}", "",
             f"**Platform:** {post['platform']} · **Format:** {post.get('format')} · **Length:** {sc.get('duration', '')}",
             f"**Voice:** {VOICES.get(post.get('voice'), {}).get('name', '')}", ""]
    if sc.get("setup"):
        lines += [f"**Setup / shoot notes:** {sc['setup']}", ""]
    lines += ["| Time | Visual | Voiceover / dialogue | On-screen text |", "|---|---|---|---|"]
    for s in sc["scenes"]:
        cells = [str(s.get(k, "")).replace("|", "/").replace("\n", " ") for k in ("time", "visual", "voiceover", "on_screen")]
        lines.append("| " + " | ".join(cells) + " |")
    if sc.get("music"):
        lines += ["", f"**Audio:** {sc['music']}"]
    if sc.get("notes"):
        lines += ["", f"**Notes:** {sc['notes']}"]
    return "\n".join(lines) + "\n"


def save_post(post: dict, *, note: str | None = None) -> dict:
    """Create or update. Moves the folder if date/slug/platform changed."""
    with _lock:
        post = {k: v for k, v in post.items() if k != "_folder"}
        if post.get("status") not in STATUSES:
            post["status"] = "draft"
        if not post.get("slug"):
            post["slug"] = slugify(post.get("title") or post.get("hook") or "post")
        if not post.get("theme"):
            post["theme"] = MONTHLY_THEMES.get(post["date"][:7], "")
        new_id = f"{PREFIX[post['platform']]}-{post['date']}-{post['slug']}"
        old = get_post(post["id"]) if post.get("id") else None
        # make id unique
        if not old or old["id"] != new_id:
            base_slug, n = post["slug"], 2
            while (clash := get_post(new_id)) and (not old or clash["id"] != old["id"]):
                post["slug"] = f"{base_slug}-{n}"
                new_id = f"{PREFIX[post['platform']]}-{post['date']}-{post['slug']}"
                n += 1
        target = _folder_for(post)
        if old:
            src = folder_of(old)
            if src.resolve() != target.resolve() and src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(target))
                _prune(src.parent)
        post["id"] = new_id
        post["updated_at"] = now_iso()
        post.setdefault("created_at", post["updated_at"])
        if note:
            post.setdefault("approvals", []).append({"at": post["updated_at"], "action": note})
        target.mkdir(parents=True, exist_ok=True)
        tmp = target / "post.json.tmp"
        tmp.write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target / "post.json")
        (target / "caption.txt").write_text(_caption_with_tags(post) + "\n", encoding="utf-8")
        fc = target / "first_comment.txt"
        if post.get("first_comment"):
            fc.write_text(post["first_comment"].strip() + "\n", encoding="utf-8")
        elif fc.exists():
            fc.unlink()
        sm = script_markdown(post)
        sp = target / "script.md"
        if sm:
            sp.write_text(sm, encoding="utf-8")
        elif sp.exists():
            sp.unlink()
        post["_folder"] = str(target)
        return post


def delete_post(pid: str) -> bool:
    with _lock:
        p = get_post(pid)
        if not p:
            return False
        f = folder_of(p)
        shutil.rmtree(f, ignore_errors=True)
        _prune(f.parent)
        return True


def _prune(month_dir: Path) -> None:
    try:
        if month_dir.exists() and not any(month_dir.iterdir()):
            month_dir.rmdir()
    except OSError:
        pass


def export_zip(posts: list[dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in posts:
            f = folder_of(p)
            if not f.exists():
                continue
            for file in f.rglob("*"):
                if file.is_file():
                    z.write(file, str(Path(p["platform"]) / f.name / file.relative_to(f)))
    return buf.getvalue()


# ---------------------------------------------------------------- helpers
def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def post_datetime(p: dict) -> datetime:
    t = p.get("time") or "09:00"
    try:
        return datetime.strptime(f"{p['date']} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(p["date"], "%Y-%m-%d")
