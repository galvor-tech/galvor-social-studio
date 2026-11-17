"""Instagram numbers entered by hand, for when the Meta connection isn't set up.

Two inputs, both written into the same store the automatic sync uses (data/analytics/instagram.json), so the
Results page, post matching and the weekly digest work the same way:

  1. A CSV of posts: the content export from Meta Business Suite (Insights → Content → Export data), or the
     Studio's own template (Results → Download template).
  2. Account numbers for a day: followers, reach, profile views.

Re-uploading never double counts: a post is identified by its link (or Meta's post id) and its numbers are
replaced with the newest ones.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime, timedelta

from . import analytics as an

TEMPLATE_HEADERS = ["Date (YYYY-MM-DD)", "Time (HH:MM)", "Type (image/carousel/reel/story)", "Link", "Caption (first line is enough)",
                    "Views", "Reach", "Likes", "Comments", "Shares", "Saves", "Follows", "Profile visits"]

COLS = {   # our field -> header names it may appear under (lower-case, compared after stripping brackets)
    "id": ["post id", "media id"],
    "link": ["permalink", "link", "url", "post link", "post url"],
    "caption": ["description", "caption", "title", "post caption"],
    "when": ["publish time", "published", "post time", "date", "publish date"],
    "time": ["time"],
    "type": ["post type", "type", "media type", "content type"],
    "views": ["views", "impressions", "plays"],
    "reach": ["reach", "accounts reached"],
    "likes": ["likes", "reactions"],
    "comments": ["comments"],
    "shares": ["shares"],
    "saves": ["saves", "saved"],
    "follows": ["follows", "new follows"],
    "profile_visits": ["profile visits", "profile views"],
    "replies": ["replies"],
}
TYPES = [("reel", ("REELS", "VIDEO")), ("story", ("STORY", "IMAGE")), ("carousel", ("FEED", "CAROUSEL_ALBUM")),
         ("album", ("FEED", "CAROUSEL_ALBUM")), ("video", ("REELS", "VIDEO")), ("image", ("FEED", "IMAGE")),
         ("photo", ("FEED", "IMAGE"))]


def template_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADERS)
    w.writerow(["2026-11-19", "13:00", "image", "https://www.instagram.com/p/EXAMPLE/", "First line of the caption", 0, 0, 0, 0, 0, 0, 0, 0])
    return buf.getvalue()


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", (h or "").replace("﻿", "")).strip().lower())


def _num(v):
    s = re.sub(r"[,\s]", "", str(v or ""))
    if not s or s in ("-", "--", "n/a", "N/A"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _when(d: str, t: str = "") -> datetime | None:
    d, t = (d or "").strip(), (t or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            dt = datetime.strptime(d, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    if t and dt.hour == 0 and dt.minute == 0:
        m = re.match(r"(\d{1,2}):(\d{2})", t)
        if m:
            dt = dt.replace(hour=int(m.group(1)), minute=int(m.group(2)))
    return dt.replace(tzinfo=an.IST)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def import_csv(raw: bytes, match: bool = True) -> dict:
    """Read a posts CSV. Returns counts and a list of rows that were skipped, with the reason."""
    text = _decode(raw)
    lines = text.splitlines()
    # Meta exports sometimes start with a 'sep=,' line or a title row: find the header row
    start = next((i for i, ln in enumerate(lines[:6]) if sum(1 for c in ("reach", "views", "likes", "permalink", "link", "date", "publish time")
                                                              if c in ln.lower()) >= 2), 0)
    sample = lines[start] if lines else ""
    delim = "\t" if sample.count("\t") > sample.count(",") else (";" if sample.count(";") > sample.count(",") else ",")
    rows = list(csv.reader(io.StringIO("\n".join(lines[start:])), delimiter=delim))
    if len(rows) < 2:
        raise an.AnalyticsError("This file has no rows under the header.")
    heads = [_norm(h) for h in rows[0]]
    idx = {}
    for field, names in COLS.items():
        for n in names:
            if n in heads:
                idx[field] = heads.index(n)
                break
    if "when" not in idx:
        raise an.AnalyticsError("Couldn't find a date column (Date or Publish time). Use the template from Results.")
    if not any(k in idx for k in ("views", "reach", "likes", "comments", "saves", "shares")):
        raise an.AnalyticsError("Couldn't find any numbers (Views, Reach, Likes, Comments, Shares, Saves).")
    now = datetime.now(an.IST).replace(microsecond=0)
    added = updated = 0
    skipped = []
    with an._lock:
        data = an._ig_store()
        for n, r in enumerate(rows[1:], start=2):
            cell = lambda f: (r[idx[f]].strip() if f in idx and idx[f] < len(r) else "")
            if not any(c.strip() for c in r):
                continue
            ts = _when(cell("when"), cell("time"))
            if not ts:
                skipped.append(f"row {n}: date '{cell('when')}' not understood")
                continue
            link = cell("link")
            if "EXAMPLE" in link:
                continue
            key = cell("id") or ("manual:" + hashlib.sha1((link or f"{ts.isoformat()}|{cell('caption')[:60]}").encode()).hexdigest()[:14])
            t = cell("type").lower()
            product, media = next((v for k, v in TYPES if k in t), ("FEED", "IMAGE"))
            if "/reel/" in link:
                product, media = "REELS", "VIDEO"
            latest = {k: _num(cell(k)) for k in ("views", "reach", "likes", "comments", "shares", "saves", "follows", "profile_visits", "replies")}
            latest = {k: v for k, v in latest.items() if v is not None}
            if not latest:
                skipped.append(f"row {n}: no numbers")
                continue
            latest["engagements"] = an._ig_engagements(latest)
            rec = data["media"].get(key, {})
            if rec:
                updated += 1
            else:
                added += 1
            age_h = (now - ts).total_seconds() / 3600
            rec.update({"id": key, "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S%z"), "permalink": link, "caption": cell("caption"),
                        "media_product_type": product, "media_type": media, "latest": latest, "latest_at": now.isoformat(),
                        "age_hours": round(age_h, 1), "manual": True})
            if "snap_24h" not in rec and age_h >= 24:
                rec["snap_24h"] = {**latest, "at": now.isoformat(), "age_hours": round(age_h, 1), "estimated": age_h >= 48}
            if "snap_7d" not in rec and age_h >= 7 * 24:
                rec["snap_7d"] = {**latest, "at": now.isoformat(), "age_hours": round(age_h, 1), "estimated": age_h >= 8 * 24}
            data["media"][key] = rec
        if added or updated:
            data["last_synced"] = an._now_iso()
            data["manual_upload_at"] = data["last_synced"]
            an._save("instagram.json", data)
    out = {"added": added, "updated": updated, "skipped": skipped[:20]}
    if match and (added or updated):
        try:
            out["matched"] = len(an.match_posts().get("matched", []))
        except Exception as e:  # noqa: BLE001
            out["match_error"] = str(e)
    return out


def save_day(day: str, followers=None, reach=None, profile_views=None, new_followers=None) -> dict:
    """Account numbers for one day, typed in from the Instagram app's Insights screen."""
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise an.AnalyticsError("Pick the date the numbers are for.")
    if d > datetime.now(an.IST).date() + timedelta(days=1):
        raise an.AnalyticsError("That date is in the future.")
    vals = {"followers": _num(followers), "reach": _num(reach), "profile_views": _num(profile_views), "new_followers": _num(new_followers)}
    if all(v is None for v in vals.values()):
        raise an.AnalyticsError("Enter at least one number.")
    with an._lock:
        data = an._ig_store()
        if vals["followers"] is not None:
            data["follower_totals"][d.isoformat()] = vals["followers"]
            data["profile"] = {**(data.get("profile") or {}), "followers_count": vals["followers"], "at": an._now_iso(),
                               "username": (data.get("profile") or {}).get("username") or "galvor.ai"}
        for k in ("reach", "profile_views", "new_followers"):
            if vals[k] is not None:
                data["daily"].setdefault(d.isoformat(), {})[k] = vals[k]
        data["last_synced"] = an._now_iso()
        data["manual_upload_at"] = data["last_synced"]
        an._save("instagram.json", data)
    return {k: v for k, v in vals.items() if v is not None}
