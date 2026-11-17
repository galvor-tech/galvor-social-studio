"""Reminders and digests — so a planned post never silently goes missing.

Runs from the scheduler every minute. Every reminder is sent once (flags live in post["reminders"]).

- "Coming up"  : `reminder_minutes` (default 30) before a planned post's time.
- "Post now"   : at the planned time.
- "Missed"     : `missed_after_minutes` (default 120) after the time, if it still isn't marked posted.
- "Reply"      : 30 min after a post is marked live — reply to comments while the first hour still counts.
- Daily digest : at `digest_time` (default 08:30): today's posts, what's overdue, the content buffer.
- Weekly digest: Mondays at `weekly_digest_time` (default 09:00): what worked, what didn't, followers, buffer.

Any post that isn't published/skipped gets reminders — approved or not — because the slot is real either way;
the reminder says if it still needs approval.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date, datetime, timedelta

from .config import LOGS, load_settings
from .store import all_posts, now_iso, post_datetime, save_post

STATE = LOGS / "reminders.json"
LIVE = ("published", "skipped")


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- phone kit links
def kit_token(pid: str) -> str:
    key = (os.getenv("STUDIO_SECRET") or "galvor").encode()
    return hmac.new(key, pid.encode(), hashlib.sha256).hexdigest()[:20]


def kit_ok(pid: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(kit_token(pid), token)


def kit_path(p: dict) -> str:
    return f"/kit/{p['id']}?k={kit_token(p['id'])}"


# ---------------------------------------------------------------- helpers
def _who(p: dict) -> list[dict]:
    """Owner of the voice + admins + whoever is marked as the poster for the platform."""
    from . import team
    people = []
    owner = team.by_voice(p.get("voice")) if p.get("voice") not in (None, "", "company") else None
    if owner:
        people.append(owner)
    s = load_settings()
    posters = s.get("posters") or {}
    for email in posters.get(p["platform"], []) + posters.get("all", []):
        m = team.by_email(email)
        if m:
            people.append(m)
    people += [m for m in team.load() if m.get("role") == "admin" and m.get("active", True)]
    return people


def _label(p: dict) -> str:
    plat = {"linkedin": "LinkedIn", "instagram": "Instagram", "newsletter": "Decoded (LinkedIn newsletter + email)"}[p["platform"]]
    from .config import VOICES
    who = VOICES.get(p.get("voice"), {}).get("name", "")
    return f"{plat} {p.get('format', '')} · {who}" if p["platform"] == "linkedin" else f"{plat} {p.get('format', '')}"


def _approval_note(p: dict) -> str:
    st = p.get("status")
    if st in ("approved", "scheduled"):
        return "Approved and ready."
    if st == "in_review":
        return "Still waiting for approval — chase the reviewer or post after sign-off."
    return f"Not approved yet (status: {st}). Get it reviewed before posting."


def buffer_days(posts: list[dict] | None = None) -> dict:
    """How far ahead the plan is ready (approved/scheduled), per platform, counting days with a slot."""
    posts = posts if posts is not None else all_posts()
    today = date.today().isoformat()
    out = {}
    for plat in ("linkedin", "instagram"):
        future = [p for p in posts if p["platform"] == plat and p["date"] >= today and p.get("status") not in LIVE]
        ready_until = today
        for p in sorted(future, key=lambda q: (q["date"], q.get("time", ""))):
            if p.get("status") in ("approved", "scheduled"):
                ready_until = p["date"]
            else:
                break
        days = (date.fromisoformat(ready_until) - date.today()).days
        nxt = next((p for p in sorted(future, key=lambda q: (q["date"], q.get("time", "")))
                    if p.get("status") not in ("approved", "scheduled")), None)
        out[plat] = {"days": max(days, 0), "level": "ok" if days >= 7 else ("warn" if days >= 3 else "bad"),
                     "next_unready": nxt["id"] if nxt else None,
                     "next_unready_title": (nxt or {}).get("title"), "next_unready_date": (nxt or {}).get("date")}
    return out


# ---------------------------------------------------------------- the per-minute check
def tick(now: datetime | None = None) -> dict:
    from . import notify
    s = load_settings()
    now = now or datetime.now()
    before = int(s.get("reminder_minutes") or 30)
    missed_after = int(s.get("missed_after_minutes") or 120)
    stats = {"pre": 0, "due": 0, "missed": 0, "reply": 0}
    for p in all_posts():
        r = p.get("reminders") or {}
        when = post_datetime(p)
        st = p.get("status")
        # posts are only reminded within a day of their slot (no flood for an old backlog)
        if st not in LIVE and when - timedelta(minutes=before) <= now < when + timedelta(hours=24):
            key = None
            if now >= when + timedelta(minutes=missed_after) and "missed" not in r:
                key, subj, body, ev = "missed", f"Missed: {p.get('title')}", (
                    f"This was due at {p.get('time')} on {_label(p)} and isn't marked posted.\n"
                    "Post it now, or open Today to reschedule it to the next free slot or skip it."), "missed"
            elif now >= when and "due" not in r and "missed" not in r:
                key, subj, body, ev = "due", f"Post now: {p.get('title')}", (
                    f"{_label(p)} · {p['date']} {p.get('time')}\n{_approval_note(p)}\n"
                    "Open the post kit on your phone: copy the caption, save the images, post, tap 'I posted it'."), "due"
            elif now < when and "pre" not in r and "due" not in r:
                key, subj, body, ev = "pre", f"In {before} min: {p.get('title')}", (
                    f"{_label(p)} at {p.get('time')}.\n{_approval_note(p)}"), "reminder"
            if key:
                notify.send(_who(p), subj, body, kit_path(p), ev)
                r[key] = now_iso()
                p["reminders"] = r
                if key in ("due", "missed"):
                    p["due"] = "Missed — post, reschedule or skip" if key == "missed" else "Time to post"
                save_post(p)
                stats[key] += 1
        # amplification: when a post goes live, the rest of the team comments/reshares in the first hour (reach)
        if st == "published" and p.get("published_at") and "amplify" not in r and p["platform"] in ("linkedin", "newsletter"):
            try:
                live = datetime.fromisoformat(p["published_at"][:19])
            except ValueError:
                live = None
            if live and now - timedelta(hours=6) <= live <= now:
                from . import team
                owner = team.by_voice(p.get("voice")) if p.get("voice") not in (None, "", "company") else None
                crew = [m for m in team.load() if m.get("active", True) and m.get("email")
                        and (not owner or m.get("email") != owner.get("email"))]
                kit = (p.get("newsletter") or {}).get("amplify") or {}
                tips = "\n".join(f"• {c}" for c in (kit.get("comment_starters") or [])[:3])
                notify.send(crew, f"Boost it: {p.get('title')}",
                            ("It just went live. A real comment or a repost with your own line in the first hour is the biggest "
                             "reach lever we have." + (f"\nIdeas:\n{tips}" if tips else "") +
                             (f"\nLink: {p['published_url']}" if p.get("published_url") else "")),
                            f"/post/{p['id']}", "amplify")
                r["amplify"] = now_iso()
                p["reminders"] = r
                save_post(p)
                stats["amplify"] = stats.get("amplify", 0) + 1
        # reply reminder: 30 min after it went live
        if st == "published" and p.get("published_at") and "reply" not in r:
            try:
                live = datetime.fromisoformat(p["published_at"][:19])
            except ValueError:
                live = None
            if live and live + timedelta(minutes=30) <= now < live + timedelta(hours=6):
                extra = " Comments are listed on Today — reply from there." if p["platform"] == "instagram" else ""
                notify.send(_who(p), f"Reply to comments: {p.get('title')}",
                            "It's been 30 minutes. Replies in the first hour help the post travel further." + extra,
                            f"/post/{p['id']}", "reply")
                r["reply"] = now_iso()
                p["reminders"] = r
                save_post(p)
                stats["reply"] += 1
    _digests(now, s)
    return stats


# ---------------------------------------------------------------- digests
def _digests(now: datetime, s: dict) -> None:
    st = _state()
    today = now.date().isoformat()
    dt = s.get("digest_time") or "08:30"
    if now.strftime("%H:%M") >= dt and st.get("daily") != today:
        st["daily"] = today
        _save_state(st)
        try:
            send_daily_digest(now)
        except Exception as e:  # never break the scheduler
            _log(f"daily digest failed: {e}")
    wt = s.get("weekly_digest_time") or "09:00"
    if now.weekday() == 0 and now.strftime("%H:%M") >= wt and st.get("weekly") != today:
        st["weekly"] = today
        _save_state(st)
        try:
            send_weekly_digest(now)
        except Exception as e:
            _log(f"weekly digest failed: {e}")


def _log(msg: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "scheduler.log", "a", encoding="utf-8") as f:
        f.write(f"{now_iso()}  REMINDERS {msg}\n")


def daily_digest_text(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now()
    today = now.date().isoformat()
    posts = all_posts()
    todays = [p for p in posts if p["date"] == today and p.get("status") not in LIVE]
    overdue = [p for p in posts if p["date"] < today and p["date"] >= (now.date() - timedelta(days=14)).isoformat()
               and p.get("status") not in LIVE and p["platform"] != "newsletter"]
    lines = []
    if todays:
        lines.append("TODAY")
        for p in sorted(todays, key=lambda q: q.get("time", "")):
            lines.append(f"  {p.get('time')}  {_label(p)} — {p.get('title')}  [{p.get('status')}]")
    else:
        lines.append("Nothing planned today.")
    if overdue:
        lines.append("")
        lines.append(f"MISSED ({len(overdue)}) — post, reschedule or skip on Today")
        for p in overdue[:8]:
            lines.append(f"  {p['date']} {p.get('time')}  {_label(p)} — {p.get('title')}")
    b = buffer_days(posts)
    lines.append("")
    lines.append("READY AHEAD (approved): " + " · ".join(f"{k.title()} {v['days']} days" for k, v in b.items()))
    for k, v in b.items():
        if v["level"] != "ok" and v.get("next_unready_title"):
            lines.append(f"  ⚠ {k.title()}: next post needing approval is {v['next_unready_date']} — {v['next_unready_title']}")
    subj = f"Today: {len(todays)} post(s)" + (f", {len(overdue)} missed" if overdue else "")
    return subj, "\n".join(lines)


def send_daily_digest(now: datetime | None = None) -> None:
    from . import notify, team
    subj, body = daily_digest_text(now)
    admins = [m for m in team.load() if m.get("role") == "admin" and m.get("active", True)]
    s = load_settings()
    extra = [team.by_email(e) for e in (s.get("digest_to") or [])]
    notify.send(admins + [m for m in extra if m], subj, body, "/", "digest")


def weekly_digest_text() -> tuple[str, str]:
    lines = []
    try:
        from . import analytics
        d = analytics.weekly_digest_data()
    except Exception as e:  # analytics not set up yet
        d = {"error": str(e)}
    if d.get("error"):
        lines.append(f"Analytics not available yet: {d['error']}")
    else:
        def n(x):
            return "—" if x is None else f"{x:,.0f}"

        def ch(m):
            m = m or {}
            if m.get("pct") is None or not m.get("prev"):
                return n(m.get("value"))
            return f"{n(m.get('value'))} ({'+' if m['change'] >= 0 else ''}{m['pct'] * 100:.0f}% vs last week)"
        for plat, blk in (d.get("platforms") or {}).items():
            name = "LinkedIn page" if plat == "linkedin" else "Instagram @galvor.ai"
            f = blk.get("followers") or {}
            lines.append(name.upper() + (f"  (data to {blk['as_of']})" if blk.get("as_of") else ""))
            lines.append(f"  Followers: {n(f.get('latest'))}  (+{n(f.get('value'))} new)")
            reach = blk.get("impressions") or blk.get("reach")
            lines.append(f"  {'Impressions' if plat == 'linkedin' else 'Reach'}: {ch(reach)}")
            lines.append(f"  Engagements: {ch(blk.get('engagements'))}")
            for key, label in (("top_post", "Best"), ("worst_post", "Weakest")):
                tp = blk.get(key)
                if tp:
                    title = ((tp.get("post") or {}).get("title") or (tp.get("text") or "")[:70] or tp.get("url") or "")
                    lines.append(f"  {label}: {title} — {n(tp.get('engagements'))} engagements"
                                 + (f" ({tp['score']:.1f}× usual)" if tp.get("score") is not None else ""))
            if blk.get("stale"):
                lines.append("  ⚠ Out of date: " + ("import this week's LinkedIn export on Results." if plat == "linkedin"
                                                    else "check the Instagram connection in Settings."))
            lines.append("")
        lines.append("Make more of what worked: open Results → What works, then Ideas → Write it.")
    b = buffer_days()
    lines.append("")
    lines.append("READY AHEAD: " + " · ".join(f"{k.title()} {v['days']} days" for k, v in b.items()))
    return "Your week in content", "\n".join(lines)


def send_weekly_digest(now: datetime | None = None) -> None:
    from . import notify, team
    subj, body = weekly_digest_text()
    admins = [m for m in team.load() if m.get("role") == "admin" and m.get("active", True)]
    notify.send(admins, subj, body, "/results", "weekly")


# ---------------------------------------------------------------- reschedule helper
def next_free_slot(p: dict, after: date | None = None) -> tuple[str, str] | None:
    """Next slot on the rhythm with nothing planned for this post's kind (voice for LinkedIn, format for IG)."""
    from .config import SLOTS
    plat = p["platform"]
    if plat not in ("linkedin", "instagram"):
        return None
    kind = (p.get("voice") or "company") if plat == "linkedin" else (
        {"carousel": "carousel", "reel": "reel", "story": "story"}.get(p.get("format"), "image"))
    taken = set()
    for q in all_posts(plat):
        if q.get("status") == "skipped" or q["id"] == p["id"]:
            continue
        k = (q.get("voice") or "company") if plat == "linkedin" else (
            {"carousel": "carousel", "reel": "reel", "story": "story"}.get(q.get("format"), "image"))
        taken.add((q["date"], k))
    d = after or (date.today() + timedelta(days=1))
    for _ in range(120):
        for wd, tm, k in SLOTS[plat]:
            if d.weekday() == wd and k == kind and (d.isoformat(), kind) not in taken:
                return d.isoformat(), tm
        d += timedelta(days=1)
    return None
