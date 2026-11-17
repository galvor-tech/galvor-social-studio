"""Background scheduler: every minute, find approved/scheduled posts that are due.

- auto_publish ON and the platform is configured → publish via API, mark Published, store the URL.
- otherwise → flag as "due" so it shows at the top of Today with copy/download buttons.
Also writes a heartbeat so the UI can show the scheduler is alive.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timedelta

from .config import LOGS, load_settings
from .store import all_posts, now_iso, post_datetime, save_post

_started = False
HEARTBEAT = LOGS / "scheduler.json"


def _log(msg: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "scheduler.log", "a", encoding="utf-8") as f:
        f.write(f"{now_iso()}  {msg}\n")


def _alert(p: dict, subject: str, body: str, event: str) -> None:
    from . import notify, team
    owner = team.by_voice(p.get("voice")) if p.get("voice") not in (None, "", "company") else None
    admins = [m for m in team.load() if m.get("role") == "admin" and m.get("active", True)]
    notify.send(([owner] if owner else []) + admins, subject, body, f"/post/{p['id']}", event)


def tick() -> dict:
    from .publisher import PublishError, can_auto_publish, publish

    s = load_settings()
    now = datetime.now()
    stats = {"checked": 0, "published": 0, "due": 0, "failed": 0}
    for p in all_posts():
        if p.get("status") != "scheduled" or p.get("platform") == "newsletter":
            continue
        stats["checked"] += 1
        when = post_datetime(p)
        if when > now:
            continue
        ok, why = can_auto_publish(p)
        if s.get("auto_publish") and ok:
            if p.get("publish_attempted_at") and datetime.fromisoformat(p["publish_attempted_at"]) > now - timedelta(minutes=15):
                continue  # back off after a failure
            p["publish_attempted_at"] = now_iso()
            try:
                res = publish(p)
                p["status"] = "published"
                p["published_at"] = now_iso()
                p["published_url"] = res.get("url", "")
                p.setdefault("publish_log", []).append({"at": now_iso(), "result": res})
                p.pop("due", None)
                save_post(p, note="Auto-published by scheduler")
                stats["published"] += 1
                _log(f"PUBLISHED {p['id']} {res}")
            except PublishError as e:
                p.setdefault("publish_log", []).append({"at": now_iso(), "error": str(e)})
                first = not str(p.get("due", "")).startswith("Auto-publish failed")
                p["due"] = f"Auto-publish failed: {e}"
                save_post(p)
                if first:
                    _alert(p, f"Auto-publish failed: {p.get('title')}", f"{e}\nPost it manually from the Today page.", "publish_failed")
                stats["failed"] += 1
                _log(f"FAILED {p['id']}: {e}")
        # manual posting: the reminders module sends "coming up / post now / missed" for every planned post
    from . import reminders
    try:
        stats["reminders"] = reminders.tick(now)
    except Exception:
        _log("ERROR reminders " + traceback.format_exc().replace("\n", " | "))
    _daily_jobs(now, s)
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps({"at": now_iso(), **stats}), encoding="utf-8")
    return stats


JOBS = LOGS / "jobs.json"


def _jobs() -> dict:
    try:
        return json.loads(JOBS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _daily_jobs(now: datetime, s: dict) -> None:
    """Instagram analytics sync and the Discover scan, once a day each (and catch up after the laptop was off)."""
    j = _jobs()
    changed = False
    sync_at = s.get("analytics_sync_time") or "07:00"
    last = j.get("ig_sync", "")
    stale = not last or datetime.fromisoformat(last) < now - timedelta(hours=20)
    if s.get("instagram_access_token") and now.strftime("%H:%M") >= sync_at and stale:
        j["ig_sync"] = now_iso()
        changed = True
        threading.Thread(target=_run_ig_sync, daemon=True).start()
    try:
        from . import discover
        if s.get("discover_auto", False) and discover.scan_due() and j.get("scan") != now.date().isoformat():
            j["scan"] = now.date().isoformat()
            changed = True
            threading.Thread(target=lambda: discover.run_scan("daily"), daemon=True).start()
    except ImportError:
        pass
    if changed:
        JOBS.write_text(json.dumps(j), encoding="utf-8")


def _run_ig_sync() -> None:
    try:
        from . import analytics
        res = analytics.sync_instagram()
        m = analytics.match_posts()
        _log(f"IG SYNC {res} MATCH {m if isinstance(m, dict) and len(str(m)) < 400 else 'ok'}")
    except Exception:
        _log("ERROR ig sync " + traceback.format_exc().replace("\n", " | "))


def _loop():
    while True:
        try:
            if load_settings().get("scheduler_enabled", True):
                tick()
        except Exception:  # never let the thread die
            _log("ERROR " + traceback.format_exc().replace("\n", " | "))
        time.sleep(60)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="gss-scheduler", daemon=True).start()


def heartbeat() -> dict:
    try:
        return json.loads(HEARTBEAT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
