"""Galvor Social Studio — local content CRM for LinkedIn, Instagram and the Decoded newsletter.

Run:  python app.py   (or double-click start_studio.bat)  →  http://127.0.0.1:5055
"""
from __future__ import annotations

import calendar as cal
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   send_from_directory, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import ai, auth, notify, reminders, scheduler  # noqa: E402
from core import team as teamlib  # noqa: E402
from core.config import (BRAND, DATA, FORMATS, JOB_MIX, JOBS, MONTHLY_THEMES, PHRASES, PILLARS, PLATFORMS,  # noqa: E402
                         POST_RULES, REACH_FACTS, DISTRIBUTION, RHYTHM, SIZES, STATUS_LABEL, STATUSES, VOICES, load_env, load_settings,
                         save_settings)
from core.lint import has_errors, lint_post  # noqa: E402
from core.store import (all_posts, blank_post, delete_post, export_zip, folder_of, get_post, now_iso,  # noqa: E402
                        parse_day, post_datetime, save_post, week_start)

load_env()
app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)   # behind Cloudflare Tunnel


def _secret() -> str:
    """Random per-install session key, persisted in .env."""
    key = os.getenv("STUDIO_SECRET")
    if key:
        return key
    import secrets as _s
    key = _s.token_urlsafe(48)
    with open(ROOT / ".env", "a", encoding="utf-8") as f:
        f.write(f"\nSTUDIO_SECRET={key}\n")
    os.environ["STUDIO_SECRET"] = key
    return key


app.secret_key = _secret()
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                  PERMANENT_SESSION_LIFETIME=timedelta(days=14))

PUBLIC = ("/login", "/auth/", "/static/", "/media/", "/favicon")
ADMIN_ONLY = ("/settings", "/team", "/api/notify/test", "/api/scheduler/tick", "/api/digest/test")


def _via_tunnel() -> bool:
    h = request.headers
    return bool(h.get("CF-Connecting-IP") or h.get("X-Forwarded-For") or h.get("Cf-Ray"))


KIT = ("/kit/", "/api/kit/")


def _is_local() -> bool:
    return (request.remote_addr or "") in ("127.0.0.1", "::1", "localhost") and not _via_tunnel()


@app.before_request
def gate():
    path = request.path
    if path.startswith(PUBLIC):
        g.user = None
        return None
    # phone post kit: a signed link per post (from reminders / Google Calendar) — works without sign-in,
    # but only for that one post's kit (copy caption, save images, mark posted).
    if path.startswith(KIT):
        pid = path.split("/")[3 if path.startswith("/api/") else 2]
        if not reminders.kit_ok(pid, request.args.get("k", "")) and not (_is_local() and not auth.enabled()):
            return render_template("message.html", title="Link expired", msg="Open this post from the studio or from the latest reminder."), 403
        g.user = {"name": "Phone", "email": "", "role": "editor"}
        return None
    if os.getenv("STUDIO_IAP") == "1":
        # Hosted on Cloud Run (cms.galvor.ai): Google IAP signs everyone in before the request reaches us
        # and passes the email as "accounts.google.com:<email>". The Team list decides the role.
        email = (request.headers.get("X-Goog-Authenticated-User-Email") or "").split(":")[-1]
        member = teamlib.by_email(email)
        if not member:
            return render_template("message.html", title="Not on the team list",
                                   msg=f"{email or 'This account'} isn't on the studio's Team list. Ask an admin to add you."), 403
        g.user = member
    elif not _is_local() and not _via_tunnel():
        # reached over Wi-Fi (phone access): only the kit is available without the tunnel + sign-in
        return render_template("message.html", title="Studio is private", msg="Open the post kit link from your reminder."), 403
    if os.getenv("STUDIO_IAP") == "1":
        pass                                  # g.user set from IAP above
    elif not auth.enabled():
        if _via_tunnel():
            return render_template("message.html", title="Sign-in required",
                                   msg="This studio is being reached over the internet, but Google sign-in isn't on yet. "
                                       "An admin must enable it in Settings → Access on the studio laptop."), 403
        g.user = teamlib.local_user()
    else:
        email = session.get("email")
        member = teamlib.by_email(email) if email else None
        if not member:
            session.clear()
            if path.startswith("/api/"):
                return jsonify(ok=False, error="Please sign in again."), 401
            return redirect(url_for("login", next=request.full_path if request.method == "GET" else "/"))
        g.user = member
    u = g.user
    if path.startswith(ADMIN_ONLY) and u.get("role") != "admin":
        if path.startswith("/api/"):
            return jsonify(ok=False, error="Admins only."), 403
        return render_template("message.html", title="Admins only", msg="Ask an admin to change settings or the team list."), 403
    if request.method == "POST" and u.get("role") == "viewer" and not path.startswith(("/voice/", "/api/notifications")):
        return jsonify(ok=False, error="Viewers can't make changes."), 403
    return None


def actor() -> str:
    u = getattr(g, "user", None) or {}
    return u.get("name") or u.get("email") or "Someone"

FESTIVALS_FILE = DATA / "festivals.json"
TOPICS_FILE = DATA / "topics.json"
GAPS_FILE = DATA / "gaps.json"
METRICS_FILE = DATA / "metrics.json"


# ================================================================ data helpers
def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def festivals() -> list[dict]:
    return _read(FESTIVALS_FILE, [])


def festivals_by_day() -> dict[str, list[dict]]:
    out = defaultdict(list)
    for f in festivals():
        d = parse_day(f["date"])
        end = parse_day(f["end_date"]) if f.get("end_date") else d
        if (end - d).days > 20:          # long sale windows: show start + end only
            out[f["date"]].append(f)
            out[f["end_date"]].append({**f, "name": f["name"] + " (ends)"})
            continue
        while d <= end:
            out[d.isoformat()].append(f)
            d += timedelta(days=1)
    return out


def voice_filter() -> str:
    v = request.cookies.get("voice", "all")
    return v if v in VOICES or v == "all" else "all"


def calendar_start() -> str:
    return load_settings().get("calendar_start") or ""


def fresh(posts: list[dict]) -> list[dict]:
    """Only what belongs to the current calendar: nothing dated before Settings → calendar_start."""
    s = calendar_start()
    return [p for p in posts if p.get("date", "") >= s] if s else posts


def filtered(posts: list[dict]) -> list[dict]:
    v = voice_filter()
    posts = fresh(posts)
    return posts if v == "all" else [p for p in posts if p.get("voice") == v]


def today() -> date:
    return date.today()


# ================================================================ template helpers
@app.template_filter("d")
def fmt_day(s, f="%a %d %b"):
    try:
        return parse_day(s).strftime(f) if isinstance(s, str) else s.strftime(f)
    except (ValueError, TypeError):
        return s or ""


@app.template_filter("hl")
def hl_filter(s):
    t = escape(str(s or ""))
    return Markup(re.sub(r"\*(.+?)\*", r"<mark>\1</mark>", str(t)))


@app.template_filter("nl")
def nl_filter(s):
    return Markup(str(escape(s or "")).replace("\n", "<br>"))


@app.template_filter("tojson_attr")
def tojson_attr(v):
    return Markup(escape(json.dumps(v, ensure_ascii=False)))


@app.context_processor
def inject():
    posts = fresh(all_posts())
    review = sum(1 for p in posts if p.get("status") == "in_review")
    due = sum(1 for p in posts if p.get("status") == "scheduled" and p.get("due"))
    counts = Counter(p["platform"] for p in posts)
    try:
        from core import ideas as _ide
        counts["ideas"] = sum(1 for i in _ide.list_ideas() if i.get("status") in ("new", "shortlisted"))
    except Exception:
        pass
    return {
        "BRAND": BRAND, "VOICES": VOICES, "STATUS_LABEL": STATUS_LABEL, "STATUSES": STATUSES,
        "nav_counts": {"review": review, "due": due, **counts},
        "voice_sel": voice_filter(), "ai_status": ai.status(), "today_str": today().isoformat(),
        "hb": scheduler.heartbeat(), "endpoint": request.endpoint, "req_args": request.args,
        "me": getattr(g, "user", None) or {}, "auth_on": auth.enabled(),
        "unread": notify.unread((getattr(g, "user", None) or {}).get("email", "")),
    }


def lint_summary(p):
    issues = [i for i in lint_post(p)]
    return {"errors": sum(i["severity"] == "error" for i in issues), "warns": sum(i["severity"] == "warn" for i in issues)}


# ================================================================ pages
@app.route("/")
def today_page():
    posts = filtered(all_posts())
    t = today()
    ts = t.isoformat()
    now = datetime.now()
    week_end = (t + timedelta(days=6)).isoformat()
    live = ("published", "skipped")
    todays = [p for p in posts if p["date"] == ts and p.get("status") not in live and p["platform"] != "newsletter"]
    due_now = [p for p in todays if post_datetime(p) <= now]
    later = [p for p in todays if post_datetime(p) > now]
    missed = [p for p in posts if p["date"] < ts and p.get("status") not in live and p["platform"] != "newsletter"
              and p["date"] >= (t - timedelta(days=21)).isoformat()]
    attention = []
    for p in posts:
        if p["date"] < ts or p.get("status") in live or p["date"] > (t + timedelta(days=14)).isoformat():
            continue
        ls = lint_summary(p)
        if ls["errors"]:
            attention.append((p, f"{ls['errors']} blocking issue(s)"))
        elif p.get("status") in ("idea", "draft", "designed") and p["date"] <= (t + timedelta(days=3)).isoformat():
            attention.append((p, "Not approved yet and goes out within 3 days"))
        elif (p.get("creative") or {}).get("slides") and not p.get("images"):
            attention.append((p, "Images not rendered"))
    upcoming_f = [f for f in festivals() if ts <= f["date"] <= (t + timedelta(days=30)).isoformat()]
    week = [p for p in posts if ts <= p["date"] <= week_end and p.get("status") not in live]
    just_live = [p for p in all_posts() if p.get("status") == "published" and (p.get("published_at") or "") >= (now - timedelta(hours=48)).isoformat()]
    buf = reminders.buffer_days()
    comments, k = [], {}
    try:
        from core import analytics
        comments = analytics.instagram_comments()[:12] if load_settings().get("instagram_access_token") else []
        k = analytics.kpis(7)
    except Exception:  # analytics not configured yet
        comments, k = [], {}
    stats = {
        "today": len(todays), "missed": len(missed),
        "review": sum(1 for p in posts if p.get("status") == "in_review"),
        "week": len(week),
        "published_month": sum(1 for p in all_posts() if p.get("status") == "published" and (p.get("published_at") or p["date"])[:7] == ts[:7]),
    }
    return render_template("today.html", due_now=due_now, later=later, missed=missed, attention=attention,
                           upcoming_f=upcoming_f, week=week, stats=stats, buf=buf, comments=comments, kpi=k,
                           goals=_goals(k), just_live=just_live, theme=MONTHLY_THEMES.get(ts[:7], ""),
                           kit_path=reminders.kit_path)


def _goals(k: dict) -> list[dict]:
    """Targets from Settings vs where we are, with the pace needed to hit them by the deadline."""
    s = load_settings()
    out = []
    by = s.get("goal_date") or "2026-12-31"
    try:
        days_left = max((parse_day(by) - today()).days, 1)
    except ValueError:
        return out
    for key, label, cur_fn in (
        ("goal_ig_followers", "Instagram followers", lambda: ((k.get("instagram") or {}).get("followers") or {}).get("latest")),
        ("goal_li_followers", "LinkedIn page followers", lambda: ((k.get("linkedin") or {}).get("followers") or {}).get("latest")),
        ("goal_audits", "Free audit requests", lambda: s.get("audits_count")),
    ):
        target = s.get(key)
        if not target:
            continue
        try:
            cur = cur_fn()
        except Exception:
            cur = None
        need = (float(target) - float(cur)) / days_left if cur is not None else None
        out.append({"label": label, "target": target, "current": cur, "by": by, "days_left": days_left,
                    "per_day": round(need, 1) if need is not None else None,
                    "pct": min(100, round(100 * float(cur) / float(target))) if cur not in (None, 0) and float(target) else 0})
    return out


# ---------------------------------------------------------------- phone post kit
@app.route("/kit/<pid>")
def kit(pid):
    p = get_post(pid)
    if not p:
        return render_template("message.html", title="Post moved", msg="This post's date changed. Open the latest reminder or the studio."), 404
    imgs = [f for f in (p.get("images") or []) if f != "carousel.pdf"]
    pdf = "carousel.pdf" in (p.get("images") or [])
    return render_template("kit.html", p=p, imgs=imgs, pdf=pdf, k=request.args.get("k", ""),
                           caption=_caption_full(p), utm=utm_link(p))


@app.get("/kit/<pid>/zip")
def kit_zip(pid):
    p = get_post(pid)
    if not p:
        abort(404)
    import io
    return send_file(io.BytesIO(export_zip([p])), mimetype="application/zip", as_attachment=True, download_name=f"{p['id']}.zip")


@app.post("/api/kit/<pid>/posted")
def kit_posted(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    p["status"] = "published"
    p["published_at"] = now_iso()
    if url:
        p["published_url"] = url
    p.pop("due", None)
    save_post(p, note="Marked posted from the phone kit")
    return jsonify(ok=True)


def _caption_full(p: dict) -> str:
    cap = (p.get("caption") or "").rstrip()
    tags = " ".join(p.get("hashtags") or [])
    return f"{cap}\n\n{tags}".strip() if tags and tags not in cap else cap


def utm_link(p: dict, dest: str = "https://galvor.ai/") -> str:
    """A tracked link for this post (use in first comments, story link stickers, DMs)."""
    from urllib.parse import urlencode
    camp = p.get("slug") or p["id"]
    q = {"utm_source": p["platform"], "utm_medium": "organic_social", "utm_campaign": camp[:60], "utm_content": p["id"][:80]}
    return dest + ("&" if "?" in dest else "?") + urlencode(q)


app.jinja_env.globals["utm_link"] = utm_link


@app.post("/api/post/<pid>/reschedule")
def api_reschedule(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    slot = reminders.next_free_slot(p)
    if not slot:
        return jsonify(ok=False, error="No free slot in the next 4 months — pick a date on the post page."), 400
    old = f"{p['date']} {p.get('time')}"
    p["rescheduled_from"] = p.get("rescheduled_from") or p["date"]
    p["date"], p["time"] = slot
    p["theme"] = MONTHLY_THEMES.get(slot[0][:7], p.get("theme", ""))
    p.pop("due", None)
    p["reminders"] = {}
    saved = save_post(p, note=f"{actor()}: rescheduled from {old} to the next free slot")
    return jsonify(ok=True, id=saved["id"], message=f"Moved to {parse_day(slot[0]).strftime('%a %d %b')} {slot[1]}")


@app.route("/overview")
def overview():
    posts = filtered(all_posts())
    month = request.args.get("m", today().isoformat()[:7])
    mp = [p for p in posts if p["date"][:7] == month]
    by_status = {pl: Counter(p["status"] for p in mp if p["platform"] == pl) for pl in PLATFORMS}
    jobs = Counter(p.get("job") for p in mp if p["platform"] == "linkedin")
    fmts = Counter(p.get("format") for p in mp if p["platform"] == "linkedin")
    ig_fmts = Counter(p.get("format") for p in mp if p["platform"] == "instagram")
    voices = Counter(p.get("voice") for p in mp if p["platform"] == "linkedin")
    pillars = Counter(p.get("pillar") for p in mp)
    months = sorted({p["date"][:7] for p in fresh(all_posts())})
    return render_template("overview.html", month=month, months=months, mp=mp, by_status=by_status, jobs=jobs,
                           fmts=fmts, ig_fmts=ig_fmts, voices=voices, pillars=pillars, JOB_MIX=JOB_MIX,
                           theme=MONTHLY_THEMES.get(month, ""))


@app.route("/approvals")
def approvals():
    posts = filtered(all_posts())
    review = [p for p in posts if p.get("status") == "in_review"]
    ready = [p for p in posts if p.get("status") in ("draft", "designed") and p["date"] >= today().isoformat()][:40]
    approved = [p for p in posts if p.get("status") == "approved"]
    me = g.user.get("email")
    mine = [p for p in review if me and me in (p.get("review") or {}).get("reviewers", [])]
    return render_template("approvals.html", review=review, ready=ready, approved=approved, mine=mine,
                           lint_summary=lint_summary, can_approve=lambda q: teamlib.can_approve(g.user, q),
                           reviewers_for=teamlib.reviewers_for)


@app.route("/calendar")
def calendar_page():
    m = (request.args.get("m") or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m):
        m = today().isoformat()[:7]           # bad or missing month → this month
    plat = request.args.get("p", "all")
    plat = plat if plat in ("all",) + PLATFORMS else "all"
    y, mo = int(m[:4]), int(m[5:7])
    weeks = cal.Calendar(firstweekday=0).monthdatescalendar(y, mo)
    posts = filtered(all_posts())
    if plat != "all":
        posts = [p for p in posts if p["platform"] == plat]
    by_day = defaultdict(list)
    for p in posts:
        by_day[p["date"]].append(p)
    prev_m = (date(y, mo, 1) - timedelta(days=1)).strftime("%Y-%m")
    next_m = (date(y, mo, 28) + timedelta(days=7)).strftime("%Y-%m")
    return render_template("calendar.html", weeks=weeks, by_day=by_day, fest=festivals_by_day(), m=m, plat=plat,
                           title=date(y, mo, 1).strftime("%B %Y"), prev_m=prev_m, next_m=next_m, month_num=mo,
                           theme=MONTHLY_THEMES.get(m, ""), today=today(), cur_month=m)


@app.route("/content/<platform>")
def content_list(platform):
    if platform not in PLATFORMS:
        abort(404)
    if platform == "newsletter" and not request.args:
        return redirect(url_for("decoded_page"))
    posts = filtered(all_posts(platform))
    st, mo, fm = request.args.get("status", ""), request.args.get("month", ""), request.args.get("format", "")
    if st:
        posts = [p for p in posts if p.get("status") == st]
    if mo:
        posts = [p for p in posts if p["date"][:7] == mo]
    if fm:
        posts = [p for p in posts if p.get("format") == fm]
    months = sorted({p["date"][:7] for p in fresh(all_posts(platform))})
    groups = defaultdict(list)
    for p in posts:
        groups[p["date"][:7]].append(p)
    return render_template("content.html", platform=platform, groups=dict(sorted(groups.items())), months=months,
                           st=st, mo=mo, fm=fm, formats=FORMATS[platform], lint_summary=lint_summary, total=len(posts),
                           folder=str((ROOT / "content" / platform)))


@app.route("/post/<pid>")
def post_page(pid):
    p = get_post(pid)
    if not p:
        abort(404)
    issues = lint_post(p)
    fest = festivals_by_day().get(p["date"], [])
    files = sorted(f.name for f in (folder_of(p) / "images").glob("*")) if (folder_of(p) / "images").exists() else []
    return render_template("post.html", p=p, issues=issues, fest=fest, files=files, PILLARS=PILLARS, FORMATS=FORMATS,
                           JOBS=JOBS, layouts=["cover", "statement", "text", "stat", "list", "compare", "poll", "festival", "cta"],
                           sizes=list(SIZES), blocking=has_errors(issues), reviewers=teamlib.reviewers_for(p),
                           can_approve=teamlib.can_approve(g.user, p), kit_url=reminders.kit_path(p),
                           hashtag_sets=hashtag_sets())


@app.route("/media/<pid>/<path:fname>")
def media(pid, fname):
    p = get_post(pid)
    if not p:
        abort(404)
    return send_from_directory(folder_of(p) / "images", fname)


# ---------------------------------------------------------------- post actions (JSON)
EDITABLE = ["date", "time", "voice", "pillar", "job", "format", "series", "title", "hook", "festival", "caption",
            "first_comment", "hashtags", "alt_text", "cta", "script", "poll", "creative", "notes", "topic_ref",
            "newsletter", "platform", "metrics", "published_url"]


def _apply(p: dict, data: dict) -> dict:
    for k in EDITABLE:
        if k in data:
            p[k] = data[k]
    if isinstance(p.get("hashtags"), str):
        p["hashtags"] = [t.strip() for t in re.split(r"[\s,]+", p["hashtags"]) if t.strip()]
    p["hashtags"] = [t if t.startswith("#") else f"#{t}" for t in p.get("hashtags") or []]
    return p


@app.post("/api/post/<pid>/save")
def api_save(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    before = _words(p)
    p = _apply(p, request.get_json(force=True))
    try:
        parse_day(p["date"])
    except ValueError:
        return jsonify(ok=False, error="Date must be YYYY-MM-DD"), 400
    note, msg = None, None
    if p.get("status") in ("approved", "scheduled") and has_errors(lint_post(p)):
        p["status"] = "draft"
    elif p.get("status") in ("approved", "scheduled") and _words(p) != before:
        # approval is of the words: changing them sends the post back for a fresh sign-off
        p["status"] = "draft"
        note = f"{actor()}: edited the approved words — back to draft for re-approval"
        msg = "The approved words changed, so it's back to draft. Send it for review again."
    saved = save_post(p, note=note)
    return jsonify(ok=True, id=saved["id"], issues=lint_post(saved), status=saved["status"], message=msg)


def _words(p: dict) -> str:
    slides = [{k: v for k, v in sl.items() if k not in ("bg", "image")} for sl in ((p.get("creative") or {}).get("slides") or [])]
    return json.dumps([p.get("caption"), p.get("first_comment"), p.get("hashtags"), slides, p.get("poll"), p.get("script")],
                      ensure_ascii=False, sort_keys=True)


@app.post("/api/post/<pid>/render")
def api_render(pid):
    from core.render import render_post
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    if studio_plus.media_blocked(p):
        return jsonify(ok=False, error=BLOCKED_MSG), 400
    data = request.get_json(silent=True) or {}
    if data:
        p = save_post(_apply(p, data))
    try:
        files = render_post(p, folder_of(p))
    except Exception as e:  # surfaced to the UI
        return jsonify(ok=False, error=str(e)), 500
    p["images"] = files
    if p.get("status") in ("idea", "draft"):
        p["status"] = "designed"
    saved = save_post(p)
    return jsonify(ok=True, id=saved["id"], images=files, status=saved["status"], v=int(datetime.now().timestamp()))


@app.post("/api/post/<pid>/status")
def api_status(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    data = request.get_json(force=True)
    new = data.get("status")
    note = (data.get("note") or "").strip()
    if new not in STATUSES:
        return jsonify(ok=False, error="Unknown status"), 400
    if new in ("approved", "scheduled", "published"):
        issues = lint_post(p)
        if has_errors(issues):
            return jsonify(ok=False, error="Fix blocking issues first: " + "; ".join(
                i["message"] for i in issues if i["severity"] == "error")), 400
    if new == "scheduled" and p.get("status") not in ("approved", "scheduled"):
        return jsonify(ok=False, error="Only approved posts can be scheduled — send it for review first."), 400
    if new == "approved" and p.get("status") not in ("in_review", "approved"):
        return jsonify(ok=False, error="Send the post for review before approving it."), 400
    sending_back = p.get("status") == "in_review" and new in ("draft", "designed")
    if (new == "approved" or sending_back) and not teamlib.can_approve(g.user, p):
        names = ", ".join(r.get("name") for r in teamlib.reviewers_for(p))
        return jsonify(ok=False, error=f"Only the assigned reviewer ({names}) or an admin can do this."), 403
    if new == "in_review" and not teamlib.can_edit(g.user):
        return jsonify(ok=False, error="You don't have edit rights."), 403
    if new == "scheduled" and (p.get("creative") or {}).get("slides") and not p.get("images"):
        return jsonify(ok=False, error="Render the images before scheduling."), 400
    if new == "published":
        p["published_at"] = p.get("published_at") or now_iso()
        if data.get("url"):
            p["published_url"] = data["url"]
    old_status = p.get("status")
    p["status"] = new
    p.pop("due", None)
    reviewers = []
    if new == "in_review":
        reviewers = teamlib.reviewers_for(p)
        p["review"] = {"requested_by": g.user.get("email", ""), "requested_by_name": actor(), "requested_at": now_iso(),
                       "reviewers": [r["email"] for r in reviewers if r.get("email")],
                       "reviewer_names": [r.get("name") for r in reviewers]}
    elif new == "approved":
        p.setdefault("review", {}).update(approved_by=actor(), approved_at=now_iso())
    saved = save_post(p, note=f"{actor()}: status → {STATUS_LABEL[new]}" + (f" — {note}" if note else ""))
    title = saved.get("title") or saved.get("hook") or saved["id"]
    when = f"{saved['date']} {saved.get('time', '')} · {saved['platform']}"
    path = f"/post/{saved['id']}"
    rv = saved.get("review") or {}
    requester = teamlib.by_email(rv.get("requested_by", "")) or {}
    author = teamlib.by_voice(saved.get("voice")) or {}
    notified = 0
    if new == "in_review":
        missing = [r.get("name") for r in reviewers if not r.get("email")]
        notified = notify.send(reviewers, f"Review needed: {title}",
                               f"{actor()} sent this for your sign-off.\nGoes out: {when}" + (f"\nNote: {note}" if note else ""),
                               path, "review_requested")
        msg = "Sent to " + ", ".join(r.get("name") for r in reviewers)
        if missing:
            msg += f" (no email on file for {', '.join(missing)} — add it under Team)"
        return jsonify(ok=True, status=saved["status"], id=saved["id"], message=msg, notified=notified)
    if new == "approved":
        notified = notify.send([requester, author], f"Approved: {title}",
                               f"{actor()} approved it. Next step: schedule it.\nGoes out: {when}",
                               path, "approved", exclude=g.user.get("email", ""))
    elif old_status == "in_review" and new in ("draft", "designed"):
        notified = notify.send([requester, author], f"Changes requested: {title}",
                               f"{actor()} sent it back." + (f"\n\nNote: {note}" if note else ""),
                               path, "sent_back", exclude=g.user.get("email", ""))
    return jsonify(ok=True, status=saved["status"], id=saved["id"], notified=notified)


@app.post("/api/post/<pid>/ai")
def api_ai(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    data = request.get_json(force=True)
    try:
        if data.get("mode") == "draft":
            new = ai.draft_post(p, data.get("instruction", ""))
        else:
            new = ai.rewrite(p, data.get("instruction") or "Tighten it.")
    except ai.AIError as e:
        return jsonify(ok=False, error=str(e)), 400
    saved = save_post(new, note="AI " + ("draft" if data.get("mode") == "draft" else f"edit: {data.get('instruction', '')[:80]}"))
    return jsonify(ok=True, id=saved["id"])


@app.post("/api/post/<pid>/script")
def api_post_script(pid):
    """AI writes (or rewrites) only the reel/video script; the caption is left alone."""
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    try:
        p["script"] = ai.write_script(p, (request.get_json(silent=True) or {}).get("instruction", ""))
    except ai.AIError as e:
        return jsonify(ok=False, error=str(e)), 400
    saved = save_post(p, note=f"{actor()}: AI wrote the script")
    probs = [i["message"] for i in lint_post(saved) if i["field"].startswith("script") and i["severity"] == "error"]
    return jsonify(ok=True, id=saved["id"], scenes=len(saved["script"]["scenes"]),
                   message=("Check the script: " + "; ".join(probs)) if probs else None)


@app.post("/api/post/<pid>/publish")
def api_publish(pid):
    from core.publisher import PublishError, publish
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    if has_errors(lint_post(p)):
        return jsonify(ok=False, error="Fix blocking issues first."), 400
    try:
        res = publish(p)
    except PublishError as e:
        return jsonify(ok=False, error=str(e)), 400
    p.update(status="published", published_at=now_iso(), published_url=res.get("url", ""))
    p.setdefault("publish_log", []).append({"at": now_iso(), "result": res})
    p.pop("due", None)
    save_post(p, note="Published via API")
    return jsonify(ok=True, result=res)


@app.post("/api/post/<pid>/duplicate")
def api_duplicate(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False), 404
    data = request.get_json(silent=True) or {}
    q = {k: v for k, v in p.items() if k not in ("id", "_folder", "images", "approvals", "metrics", "published_url",
                                                 "published_at", "publish_log", "due")}
    q["slug"] = ""
    q["status"] = "draft"
    if data.get("platform") in PLATFORMS:
        q["platform"] = data["platform"]
        if q["platform"] == "instagram":
            q["voice"] = "company"
            q["pillar"] = q["pillar"] if q["pillar"] in PILLARS["instagram"] else "Quick Tip"
            q["format"] = q["format"] if q["format"] in FORMATS["instagram"] else "image"
            q["hashtags"] = (q.get("hashtags") or [])[:5]
            q.setdefault("creative", {}).setdefault("size", "feed")
        else:
            q["pillar"] = q["pillar"] if q["pillar"] in PILLARS["linkedin"] else "Brand Memory / POV"
            q["format"] = q["format"] if q["format"] in FORMATS["linkedin"] else "image"
    q["title"] = (q.get("title") or "") + (" (copy)" if not data.get("platform") else f" ({q['platform']})")
    saved = save_post(q, note=f"Duplicated from {pid}")
    return jsonify(ok=True, id=saved["id"])


@app.post("/api/post/<pid>/delete")
def api_delete(pid):
    if g.user.get("role") != "admin":
        return jsonify(ok=False, error="Only admins can delete posts."), 403
    return jsonify(ok=delete_post(pid))


@app.get("/post/<pid>/download")
def download(pid):
    p = get_post(pid)
    if not p:
        abort(404)
    import io
    return send_file(io.BytesIO(export_zip([p])), mimetype="application/zip", as_attachment=True,
                     download_name=f"{p['id']}.zip")


@app.post("/api/post/<pid>/open-folder")
def open_folder(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False), 404
    f = folder_of(p)
    if os.name == "nt":
        os.startfile(f)  # noqa: S606 — local desktop tool
    else:
        subprocess.Popen(["xdg-open", str(f)])
    return jsonify(ok=True)


REPURPOSE = {
    "ig_carousel": ("instagram", "carousel", "Rewrite this as an Instagram carousel for @galvor.ai: 6–8 slides (cover hook → value slides → cta "
                    "slide whose first action is 'Follow @galvor.ai'), punchier caption 400–900 chars, first line under 125 chars, "
                    "'link in bio', 3–5 Instagram hashtags incl. #KnowWhyYourAdsWin."),
    "ig_reel": ("instagram", "reel", "Turn this into a 25–40s Instagram Reel for @galvor.ai: scene-by-scene script (hook in the first 2s, "
                "on-screen text for every scene), one story-size cover slide, short caption with 'link in bio'."),
    "li_carousel": ("linkedin", "carousel", "Rewrite this as a LinkedIn document carousel: 6–9 slides (cover → value → cta slide with "
                    "'Follow Galvor' first), caption 700–1,200 chars with the hook in the first 200 chars, link in first comment."),
    "nl_section": ("newsletter", "issue", "Rewrite this as one section for the Decoded newsletter: a 150–250 word section with a "
                   "subhead, keeping every number exactly as written and its source."),
}


@app.post("/api/post/<pid>/repurpose")
def api_repurpose(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    kind = (request.get_json(silent=True) or {}).get("kind")
    if kind not in REPURPOSE:
        return jsonify(ok=False, error="Unknown format"), 400
    plat, fmt, ins = REPURPOSE[kind]
    q = {k: v for k, v in p.items() if k not in ("id", "_folder", "images", "approvals", "metrics", "published_url",
                                                 "published_at", "publish_log", "due", "reminders", "external_id", "review")}
    q.update(slug="", status="draft", platform=plat, format=fmt, repurposed_from=pid,
             title=(p.get("title") or "") + f" ({kind.replace('_', ' ')})")
    if plat == "instagram":
        q["voice"] = "company"
        q["pillar"] = q["pillar"] if q.get("pillar") in PILLARS["instagram"] else "Quick Tip"
        q["creative"] = {"size": "story" if fmt == "reel" else "feed", "slides": (p.get("creative") or {}).get("slides") or []}
    elif plat == "linkedin":
        q["pillar"] = q["pillar"] if q.get("pillar") in PILLARS["linkedin"] else "Brand Memory / POV"
    else:
        q["pillar"] = "Newsletter"
    nxt = reminders.next_free_slot(q) if plat != "newsletter" else None
    if nxt:
        q["date"], q["time"] = nxt
    try:
        q = ai.rewrite(q, ins)
    except ai.AIError as e:
        saved = save_post(q, note=f"Repurposed from {pid} (AI unavailable: {e}) — rewrite by hand")
        return jsonify(ok=True, id=saved["id"], message=f"Copied without AI: {e}")
    saved = save_post(q, note=f"{actor()}: repurposed from {pid} as {kind}")
    return jsonify(ok=True, id=saved["id"])


HASHTAG_FILE = DATA / "hashtag_sets.json"
DEFAULT_HASHTAG_SETS = {
    "LinkedIn · performance": ["#PerformanceMarketing", "#MetaAds", "#D2CIndia"],
    "LinkedIn · creative": ["#CreativeStrategy", "#AdCreative", "#D2C"],
    "LinkedIn · AI & team": ["#AIinMarketing", "#MarketingAnalytics", "#GrowthMarketing"],
    "LinkedIn · creators": ["#CreatorMarketing", "#D2CIndia", "#CreativeStrategy"],
    "Instagram · tips": ["#performancemarketing", "#metaads", "#adcreative", "#marketingtips", "#KnowWhyYourAdsWin"],
    "Instagram · D2C India": ["#d2cindia", "#digitalmarketingindia", "#adstrategy", "#creativestrategy", "#KnowWhyYourAdsWin"],
    "Instagram · memes": ["#marketingmemes", "#metaads", "#adcreative", "#d2cindia", "#KnowWhyYourAdsWin"],
    "Instagram · UGC & creators": ["#ugcads", "#creatormarketing", "#d2cindia", "#adcreative", "#KnowWhyYourAdsWin"],
}


def hashtag_sets() -> dict:
    return _read(HASHTAG_FILE, None) or DEFAULT_HASHTAG_SETS


@app.route("/api/hashtag-sets", methods=["GET", "POST"])
def api_hashtag_sets():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        clean = {str(k)[:40]: [t if t.startswith("#") else "#" + t for t in v][:5] for k, v in data.items() if isinstance(v, list)}
        _write(HASHTAG_FILE, clean)
        return jsonify(ok=True)
    return jsonify(ok=True, sets=hashtag_sets())


# ---------------------------------------------------------------- hubs (6 screens + playbook)
@app.route("/create")
def create_hub():
    return redirect(url_for("approvals"))


@app.route("/playbook")
def playbook():
    return redirect(url_for("strategy"))


# ---------------------------------------------------------------- create
@app.route("/new", methods=["GET", "POST"])
def new_post():
    topics = _read(TOPICS_FILE, [])
    used = {p.get("topic_ref") for p in all_posts() if p.get("topic_ref")}
    if request.method == "POST":
        f = request.form
        plat = f.get("platform", "linkedin")
        day = f.get("date") or today().isoformat()
        p = blank_post(plat, day, time=f.get("time") or "09:00", voice=f.get("voice") or "company",
                       format=f.get("format") or ("text" if plat == "linkedin" else "carousel"),
                       pillar=f.get("pillar") or PILLARS[plat][0], job=f.get("job") or "Attract",
                       hook=f.get("hook", "").strip(), title=(f.get("title") or f.get("hook") or "New post").strip()[:90],
                       festival=f.get("festival") or None, topic_ref=f.get("topic_ref") or "", status="idea")
        if plat == "instagram":
            p["voice"] = "company"
        if p["format"] in ("reel", "story", "video"):
            p["creative"]["size"] = "story"
        if f.get("use_ai") == "1":
            try:
                p = ai.draft_post(p, f.get("brief", ""))
            except ai.AIError as e:
                flash(f"AI draft failed — saved as an idea instead. {e}", "error")
        saved = save_post(p, note="Created")
        return redirect(url_for("post_page", pid=saved["id"]))
    pre = {k: request.args.get(k, "") for k in ("platform", "date", "voice", "format", "festival", "hook", "topic_ref", "pillar", "job", "time")}
    return render_template("new.html", pre=pre, topics=topics, used=used, PILLARS=PILLARS, FORMATS=FORMATS, JOBS=JOBS)


@app.route("/planner", methods=["GET", "POST"])
def planner():
    start = parse_day(request.values.get("start") or week_start(today() + timedelta(days=7)).isoformat())
    weeks = int(request.values.get("weeks") or 1)
    posts = all_posts()
    have = {(p["platform"], p["date"], p.get("voice")) for p in posts}
    topics = _read(TOPICS_FILE, [])
    used = {p.get("topic_ref") for p in posts if p.get("topic_ref")}
    pool = {v: [t for t in topics if t["voice"] == v and t["ref"] not in used] for v in ("sunil", "raj", "shrutik")}
    dow = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    slots = []
    for w in range(weeks):
        for plat, rows in RHYTHM.items():
            for day, tm, voice, desc in rows:
                if day not in dow:
                    continue
                d = (start + timedelta(days=7 * w + dow[day])).isoformat()
                exists = (plat, d, voice) in have
                topic = None
                if not exists and voice in pool and pool[voice]:
                    topic = pool[voice].pop(0)
                slots.append({"platform": plat, "date": d, "time": tm, "voice": voice, "desc": desc, "exists": exists, "topic": topic,
                              "festivals": [f["name"] for f in festivals_by_day().get(d, [])]})
    if request.method == "POST":
        made = 0
        use_ai = request.form.get("use_ai") == "1"
        errors = []
        for s in slots:
            if s["exists"] or request.form.get(f"slot_{s['platform']}_{s['date']}_{s['voice']}") != "1":
                continue
            t = s["topic"]
            if s["platform"] == "instagram":
                fmt = ("reel" if s["desc"].startswith("Reel") else "story" if s["desc"].startswith("Stories")
                       else "image" if s["desc"].startswith("Single") else "carousel")
                p = blank_post("instagram", s["date"], time=s["time"], voice="company", format=fmt,
                               pillar="Quick Tip" if fmt == "carousel" else "Ad Breakdown", job="Educate",
                               title=s["desc"], hook="", status="idea")
                if fmt in ("reel", "story"):
                    p["creative"]["size"] = "story"
            else:
                fmt = (t or {}).get("format", "text")
                fmt = fmt if fmt in FORMATS["linkedin"] else "text"
                p = blank_post("linkedin", s["date"], time=s["time"], voice=s["voice"], format=fmt,
                               pillar=_map_pillar(t), job=(t or {}).get("job", "Attract"),
                               hook=(t or {}).get("hook", ""), title=(t or {}).get("hook", s["desc"])[:90],
                               topic_ref=(t or {}).get("ref", ""), status="idea")
                if fmt == "video":
                    p["creative"]["size"] = "story"
            if use_ai:
                try:
                    p = ai.draft_post(p)
                except ai.AIError as e:
                    errors.append(str(e))
            save_post(p, note="Created by planner")
            made += 1
        flash(f"Created {made} post(s)." + (f" AI errors: {errors[0]}" if errors else ""), "error" if errors else "ok")
        return redirect(url_for("calendar_page", m=start.isoformat()[:7]))
    return render_template("planner.html", slots=slots, start=start.isoformat(), weeks=weeks)


def _map_pillar(t) -> str:
    if not t:
        return "Brand Memory / POV"
    m = {"Marketing money for founders and CMOs": "Marketing Money", "Brand Memory (our point of view)": "Brand Memory / POV",
         "AI and the marketing team": "AI & the Team", "In the room with buyers (series: \"What I Heard in the Room\")": "In the Room",
         "Building Galvor (founder journey)": "Building Galvor", "Reading ads (series: \"Ad of the Week\")": "Decode Teardown",
         "What public data can and can't tell you": "Public Data", "Building the engine (learning in public)": "Building Galvor",
         "Measurement that matters": "Measurement", "Creators and testing": "Creators & Testing", "Better briefs": "Better Briefs",
         "Running creator campaigns in India": "Creator Ops India", "Feedback and approvals": "Feedback & Approvals",
         "AI in the real workflow": "AI & the Team", "Client lessons": "Client Lessons"}
    return m.get(t.get("pillar"), "Brand Memory / POV")


@app.route("/topics")
def topics_page():
    topics = _read(TOPICS_FILE, [])
    used = {}
    for p in all_posts():
        if p.get("topic_ref"):
            used[p["topic_ref"]] = p
    v = voice_filter()
    if v != "all":
        topics = [t for t in topics if t["voice"] == v]
    return render_template("topics.html", topics=topics, used=used)


@app.route("/festivals")
def festivals_page():
    fs = festivals()
    hol = request.args.get("holiday", "")
    rel = request.args.get("religion", "")
    if hol:
        fs = [f for f in fs if (f.get("holiday") or "none") == hol]
    if rel:
        fs = [f for f in fs if f.get("religion") == rel]
    posts_by_fest = defaultdict(list)
    for p in all_posts():
        if p.get("festival"):
            posts_by_fest[p["date"]].append(p)
    groups = defaultdict(list)
    for f in fs:
        groups[f["date"][:7]].append(f)
    religions = sorted({f.get("religion") for f in festivals() if f.get("religion")})
    counts = Counter((f.get("holiday") or "none") for f in festivals())
    return render_template("festivals.html", groups=dict(sorted(groups.items())), religions=religions, hol=hol, rel=rel,
                           counts=counts, total=len(festivals()), posts_by_fest=posts_by_fest, ts=today().isoformat())


@app.route("/strategy")
def strategy():
    return render_template("strategy.html", PHRASES=PHRASES, RULES=POST_RULES, RHYTHM=RHYTHM, THEMES=MONTHLY_THEMES,
                           JOB_MIX=JOB_MIX, PILLARS=PILLARS, REACH=REACH_FACTS,
                           DISTRIBUTION=DISTRIBUTION)


@app.route("/brand")
def brand():
    md = (DATA / "CONTENT_SPEC.md").read_text(encoding="utf-8")
    return render_template("brand.html", html=_md(md))


def _md(md: str) -> Markup:
    """Tiny markdown → HTML (headings, tables, lists, code blocks, bold, inline code)."""
    out, in_code, in_table, in_list = [], False, False, False
    def inline(s):
        s = str(escape(s))
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"(?<![\w*])\*([^*]+)\*(?!\w)", r"<i>\1</i>", s)
        return s
    for line in md.splitlines():
        if line.startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(str(escape(line)))
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if not in_table:
                out.append("<table class='tbl'>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        m = re.match(r"^(#{1,3}) (.+)", line)
        if m:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h{len(m.group(1)) + 1}>{inline(m.group(2))}</h{len(m.group(1)) + 1}>")
        elif re.match(r"^\s*[-*] ", line) or re.match(r"^\d+\. ", line):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(re.sub(r'^\s*([-*]|\d+\.) ', '', line))}</li>")
        elif line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    return Markup("\n".join(out))


# ---------------------------------------------------------------- gaps
@app.route("/gaps", methods=["GET", "POST"])
def gaps():
    data = _read(GAPS_FILE, [])
    if request.method == "POST":
        body = request.get_json(force=True)
        for g in data:
            if g["id"] == body.get("id"):
                g["status"] = body.get("status", g["status"])
                g["owner"] = body.get("owner", g.get("owner", ""))
                g["updated"] = now_iso()
        _write(GAPS_FILE, data)
        return jsonify(ok=True)
    groups = defaultdict(list)
    for g in data:
        groups[g["group"]].append(g)
    done = sum(g["status"] == "done" for g in data)
    return render_template("gaps.html", groups=groups, done=done, total=len(data))


# ---------------------------------------------------------------- results (analytics)
@app.route("/analytics")
def analytics():
    return redirect(url_for("results_page"))


@app.route("/results")
def results_page():
    from core import analytics as an
    days = int(request.args.get("days") or 7)
    plat = request.args.get("p", "all")
    k = an.kpis(days)
    series = {
        "li_followers": an.daily_series("linkedin", "followers", 90),
        "li_impressions": an.daily_series("linkedin", "impressions", 90),
        "ig_followers": an.daily_series("instagram", "followers", 90),
        "ig_reach": an.daily_series("instagram", "reach", 90),
    }
    acct = {a: an.daily_series("linkedin", "impressions", 90, account=a)
            for a in (k.get("linkedin") or {}).get("accounts", {}) if a != "company"}
    table = an.post_table(None if plat == "all" else plat, days=int(request.args.get("window") or 90))
    pats = {pl: an.patterns(pl) for pl in ("linkedin", "instagram")}
    s = load_settings()
    outside = [r for r in table if not r.get("post")][:30]
    aw = awareness(days)
    return render_template("results.html", aw=aw, k=k, series=series, acct_series=acct, table=table, pats=pats, days=days, plat=plat,
                           ig_connected=bool(s.get("instagram_access_token") and s.get("instagram_user_id")),
                           outside=outside, audits=_read(DATA / "audits.json", []))


AWARE_KEYS = (("views", "Views & impressions", ("impressions", "views")), ("comments", "Comments", ("comments",)),
              ("clicks", "Link & profile clicks", ("clicks", "profile_visits", "website_clicks")),
              ("shares", "Reposts, shares & saves", ("reposts", "shares", "saves", "sends")), ("follows", "New follows", ("follows",)))


def awareness(days: int = 7) -> dict:
    """The goal: more people seeing and engaging with Galvor, across every handle (page, founders' profiles, Instagram)."""
    from core import analytics as an
    rows = an.post_table(None, days=days * 2 + 7)
    ends = [r["date"] for r in rows if r.get("date")]
    if not ends:
        return {"rows": [], "as_of": None}
    as_of = parse_day(max(ends))
    cur_from, prev_from = as_of - timedelta(days=days - 1), as_of - timedelta(days=2 * days - 1)

    def total(fr, to, keys, plat=None):
        t = 0.0
        for r in rows:
            d = parse_day(r["date"]) if r.get("date") else None
            if d and fr <= d <= to and (not plat or r["platform"] == plat):
                m = r.get("metrics") or {}
                vals = [m.get(k) for k in keys if isinstance(m.get(k), (int, float))]
                t += (max(vals) if keys[0] in ("impressions", "views") and vals else sum(vals)) if vals else 0
        return t
    s = load_settings()
    out = []
    for key, label, keys in AWARE_KEYS:
        cur = total(cur_from, as_of, keys)
        prev = total(prev_from, cur_from - timedelta(days=1), keys)
        out.append({"key": key, "label": label, "value": cur, "prev": prev,
                    "pct": (cur - prev) / prev if prev else None,
                    "by": {pl: total(cur_from, as_of, keys, pl) for pl in ("linkedin", "instagram")},
                    "target": (s.get("aware_targets") or {}).get(key)})
    return {"rows": out, "as_of": as_of.isoformat(), "from": cur_from.isoformat(), "days": days}


@app.post("/api/results/import")
def api_results_import():
    from core import analytics as an
    files = request.files.getlist("files")
    if not files:
        return jsonify(ok=False, error="Choose the LinkedIn export file(s)."), 400
    up = DATA / "analytics" / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    done, errors = [], []
    for f in files:
        name = re.sub(r"[^\w .()-]", "_", f.filename or "export.xls")
        dest = up / f"{datetime.now():%Y%m%d-%H%M%S}_{name}"
        f.save(dest)
        try:
            done.append(an.import_linkedin_file(str(dest), account=request.form.get("account") or None))
        except an.AnalyticsError as e:
            errors.append(f"{f.filename}: {e}")
    return jsonify(ok=not errors, imported=done, errors=errors)


@app.post("/api/results/sync")
def api_results_sync():
    from core import analytics as an
    res = an.sync_instagram()
    return jsonify(ok=bool(res.get("ok")), result=res, reason=res.get("reason"))


@app.post("/api/results/link")
def api_results_link():
    from core import analytics as an
    d = request.get_json(force=True) or {}
    return jsonify(ok=True, result=an.link_post(d.get("key", ""), d.get("post_id") or None))


@app.post("/api/results/audits")
def api_results_audits():
    """Free-audit requests per week (from the website / CRM): the number that matters most."""
    d = request.get_json(force=True) or {}
    rows = _read(DATA / "audits.json", [])
    try:
        n = int(d.get("count"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Enter a number."), 400
    week = d.get("week") or week_start(today()).isoformat()
    rows = [r for r in rows if r["week"] != week] + [{"week": week, "count": n, "source": d.get("source", ""), "note": d.get("note", "")}]
    rows.sort(key=lambda r: r["week"])
    _write(DATA / "audits.json", rows)
    s = load_settings()
    s["audits_count"] = sum(r["count"] for r in rows if r["week"] >= (s.get("goal_start") or "2026-11-09"))
    save_settings(s)
    return jsonify(ok=True)


@app.post("/api/ig/reply")
def api_ig_reply():
    from core import analytics as an
    d = request.get_json(force=True) or {}
    if not (d.get("comment_id") and (d.get("text") or "").strip()):
        return jsonify(ok=False, error="Write a reply first."), 400
    res = an.reply_instagram_comment(d["comment_id"], d["text"].strip())
    if res.get("ok"):
        return jsonify(ok=True, id=res.get("id"))
    return jsonify(ok=False, reason=res.get("reason"))


# ---------------------------------------------------------------- discover + ideas (from galvor-cms)
@app.route("/discover")
def discover_page():
    from core import discover, ledger
    kind = request.args.get("kind") or None
    q = request.args.get("q") or None
    rel = request.args.get("all") != "1"
    sort = request.args.get("sort", "score")
    src = request.args.get("source") or None
    items = discover.items(kind=kind, q=q, relevant_only=rel, sort=sort, limit=150, source=src)
    searches = sorted({i.get("source") for i in discover.items(limit=0, include_hidden=True)
                       if (i.get("source") or "").startswith("Search: ")})
    unit = {"google": discover.APIFY_USD_PER_RESULT["apify~google-search-scraper"],
            "x": discover.X_PER_SEARCH * discover.APIFY_USD_PER_RESULT["apidojo~tweet-scraper"],
            "instagram_hashtag": discover.HIKER_USD_PER_REQUEST, "instagram_account": 2 * discover.HIKER_USD_PER_REQUEST,
            "linkedin_accounts": discover.LI_PER_ACCOUNT * discover.APIFY_USD_PER_RESULT["harvestapi~linkedin-profile-posts"]}
    srcs = discover.sources()
    for s in srcs:
        s["usd"] = discover.estimate([dict(s, enabled=True)])
    return render_template("discover.html", items=items, kind=kind, q=q or "", rel=rel, kinds=discover.KINDS,
                           sources=srcs, last=discover.last_scan(), spend=ledger.summary(), sort=sort,
                           search_kinds=discover.SEARCH_KINDS, unit=unit, src=src or "", searches=searches)


@app.post("/api/discover/scan")
def api_discover_scan():
    from core import discover, ledger
    d = request.get_json(silent=True) or {}
    try:
        if d.get("q"):                                   # a keyword or topic the user typed, on the platforms they ticked
            srcs = discover.search_sources(d["q"], d.get("kinds") or [])
            if not srcs:
                return jsonify(ok=False, error="Type a keyword and tick at least one place to search. LinkedIn needs a page or profile link."), 400
            scan = discover.run_scan("search", srcs=srcs)
            scan["source"] = f"Search: {d['q'].strip()}"
        else:                                            # saved sources the user ticked
            ids = set(d.get("ids") or [])
            srcs = [dict(s, enabled=True) for s in discover.sources() if s["id"] in ids]
            if not srcs:
                return jsonify(ok=False, error="Tick at least one saved source to scan."), 400
            scan = discover.run_scan("manual", srcs=srcs)
    except ledger.OverBudget as e:
        return jsonify(ok=False, error=f"Daily spending limit reached: {e}"), 400
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, scan=scan)


@app.post("/api/discover/hide")
def api_discover_hide():
    from core import discover
    d = request.get_json(force=True) or {}
    discover.hide(d.get("id"), bool(d.get("hidden", True)))
    return jsonify(ok=True)


@app.post("/api/discover/sources")
def api_discover_sources():
    from core import discover
    try:
        discover.save_sources((request.get_json(force=True) or {}).get("sources") or [])
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True)


@app.route("/ideas")
def ideas_page():
    from core import ideas as ide
    st = request.args.get("status") or None
    every = ide.list_ideas()
    items = ide.list_ideas(st) if st else [i for i in every if i.get("status") in ("new", "shortlisted")]
    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    items.sort(key=lambda i: 0 if i.get("status") == "shortlisted" else 1)
    return render_template("ideas.html", ideas=items, st=st or "", counts=Counter(i.get("status") for i in every))


@app.post("/api/ideas/generate")
def api_ideas_generate():
    from core import ideas as ide, ledger
    d = request.get_json(silent=True) or {}
    try:
        if d.get("from") == "topics":
            made = ide.from_topics(int(d.get("n") or 6))
        else:
            made = ide.generate(item_ids=d.get("item_ids") or None, n_ideas=int(d.get("n") or 6))
    except ledger.OverBudget as e:
        return jsonify(ok=False, error=f"Daily spending limit reached: {e}"), 400
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, n=len(made))


@app.post("/api/ideas/<iid>")
def api_idea_update(iid):
    from core import ideas as ide
    d = request.get_json(force=True) or {}
    allowed = {k: v for k, v in d.items() if k in ("status", "hook", "angle", "platform", "format", "voice", "pillar")}
    ide.update_idea(iid, **allowed)
    return jsonify(ok=True)


@app.post("/api/ideas/<iid>/to-post")
def api_idea_to_post(iid):
    """Idea -> a draft post in the next free slot, written by the AI from the idea's brief."""
    from core import ideas as ide
    b = ide.idea_to_post_brief(iid)
    plat = (request.get_json(silent=True) or {}).get("platform") or b["platform"]
    if plat not in ("linkedin", "instagram"):
        plat = "linkedin"
    fmt = b["format"] if b["format"] in FORMATS[plat] else ("carousel" if plat == "instagram" else "text")
    pillar = b["pillar"] if b["pillar"] in PILLARS[plat] else PILLARS[plat][0]
    p = blank_post(plat, today().isoformat(), voice="company" if plat == "instagram" else (b.get("voice") or "company"),
                   format=fmt, pillar=pillar, job=b.get("job") or "Educate", hook=b.get("hook", ""),
                   title=(b.get("title") or b.get("hook") or "New post")[:90], topic_ref=b.get("topic_ref") or "",
                   status="idea", idea_id=iid)
    if fmt in ("reel", "story", "video"):
        p["creative"]["size"] = "story"
    slot = reminders.next_free_slot(p)
    if slot:
        p["date"], p["time"] = slot
    msg = None
    try:
        p = ai.draft_post(p, b.get("brief", ""))
    except ai.AIError as e:
        msg = f"Saved as an idea; AI draft failed: {e}"
    saved = save_post(p, note=f"{actor()}: created from idea {iid}")
    ide.update_idea(iid, status="used", post_id=saved["id"])
    return jsonify(ok=True, id=saved["id"], message=msg)


@app.post("/api/post/<pid>/metrics")
def api_metrics(pid):
    p = get_post(pid)
    if not p:
        return jsonify(ok=False), 404
    data = request.get_json(force=True)
    clean = {}
    for k, v in data.items():
        try:
            clean[k] = float(v) if v not in ("", None) else None
        except (TypeError, ValueError):
            pass
    p["metrics"] = clean
    save_post(p)
    return jsonify(ok=True)


# ---------------------------------------------------------------- settings / misc
@app.route("/settings", methods=["GET", "POST"])
def settings():
    s = load_settings()
    if request.method == "POST":
        f = request.form
        for k in ("ai_provider", "anthropic_model", "gemini_model", "chrome_path", "public_base_url", "linkedin_access_token",
                  "linkedin_org_urn", "linkedin_api_version", "instagram_access_token", "instagram_user_id", "graph_api_version",
                  "google_client_id", "base_url", "smtp_host", "smtp_user", "smtp_from", "chat_webhook"):
            if k in f:
                s[k] = f[k].strip()
        for k in ("google_client_secret", "smtp_password"):      # blank = keep the saved secret
            if f.get(k, "").strip():
                s[k] = f[k].strip()
        if f.get("smtp_port", "").strip().isdigit():
            s["smtp_port"] = int(f["smtp_port"])
        s["allowed_domains"] = [d.strip().lower().lstrip("@") for d in f.get("allowed_domains", "galvor.com").split(",") if d.strip()]
        s["notify_email"] = f.get("notify_email") == "1"
        want_google = f.get("auth_mode") == "google"
        if want_google and not (s.get("google_client_id") and s.get("google_client_secret")):
            flash("Add the Google client ID and secret before turning sign-in on.", "error")
            want_google = False
        if want_google and not teamlib.by_email(g.user.get("email", "")):
            flash("Your own email must be on the Team list as an admin first, or you'd be locked out.", "error")
            want_google = False
        if want_google and not s.get("base_url"):
            flash("Set the studio's web address (base URL) before turning sign-in on.", "error")
            want_google = False
        s["auth_mode"] = "google" if want_google else "off"
        s["auto_publish"] = f.get("auto_publish") == "1"
        for k in ("reminder_minutes", "missed_after_minutes"):
            if f.get(k, "").strip().isdigit():
                s[k] = int(f[k])
        for k in ("digest_time", "weekly_digest_time", "analytics_sync_time", "discover_scan_time", "goal_date",
                  "instagram_api_host"):
            if k in f:
                s[k] = f[k].strip()
        for k in ("goal_ig_followers", "goal_li_followers", "goal_audits"):
            if k in f:
                s[k] = int(f[k]) if f[k].strip().isdigit() else None
        try:
            s["discover_daily_cap_usd"] = float(f.get("discover_daily_cap_usd") or 2)
        except ValueError:
            pass
        if f.get("hiker_daily_searches", "").strip().isdigit():
            s["hiker_daily_searches"] = int(f["hiker_daily_searches"])
        s["discover_auto"] = f.get("discover_auto") == "1"
        s["aware_targets"] = {k: int(f[f"aware_{k}"]) for k in ("views", "comments", "clicks", "shares", "follows")
                              if f.get(f"aware_{k}", "").strip().isdigit()}
        s["posters"] = {pl: [e.strip().lower() for e in f.get(f"posters_{pl}", "").split(",") if e.strip()]
                        for pl in ("instagram", "linkedin")}
        s["scheduler_enabled"] = f.get("scheduler_enabled") == "1"
        s["linkedin_person_urns"] = {v: f.get(f"urn_{v}", "").strip() for v in ("sunil", "raj", "shrutik") if f.get(f"urn_{v}", "").strip()}
        s["linkedin_person_tokens"] = {v: f.get(f"tok_{v}", "").strip() for v in ("sunil", "raj", "shrutik") if f.get(f"tok_{v}", "").strip()}
        save_settings(s)
        flash("Settings saved.", "ok")
        return redirect(url_for("settings"))
    from core.render import find_browser
    try:
        browser = find_browser()
    except RuntimeError as e:
        browser = f"Not found — {e}"
    return render_template("settings.html", s=s, browser=browser, env_path=str(ROOT / ".env"),
                           notify_log=notify.recent_log(), team=teamlib.load())


@app.post("/api/digest/test")
def api_digest_test():
    subj, body = reminders.daily_digest_text()
    notify.send([g.user], subj, body, "/", "digest")
    return jsonify(ok=True)


@app.post("/api/scheduler/tick")
def api_tick():
    return jsonify(ok=True, stats=scheduler.tick())


@app.post("/api/ask")
def api_ask():
    q = (request.get_json(force=True) or {}).get("q", "").strip()
    if not q:
        return jsonify(ok=False, error="Ask something.")
    upcoming = [p for p in all_posts() if p["date"] >= today().isoformat()][:60]
    ctx = "\n".join(f"{p['date']} {p['time']} {p['platform']} {p.get('voice')} {p.get('format')} [{p.get('status')}] {p.get('title')}" for p in upcoming)
    ctx += "\nUpcoming festivals: " + "; ".join(f"{f['date']} {f['name']}" for f in festivals() if f["date"] >= today().isoformat())[:3000]
    try:
        return jsonify(ok=True, a=ai.ask(q, ctx))
    except ai.AIError as e:
        return jsonify(ok=False, error=str(e))


@app.post("/voice/<v>")
def set_voice(v):
    resp = redirect(request.referrer or url_for("today_page"))
    resp.set_cookie("voice", v if v in VOICES or v == "all" else "all", max_age=3600 * 24 * 365)
    return resp


@app.get("/search")
def search():
    q = request.args.get("q", "").strip().lower()
    res = []
    if q:
        for p in all_posts():
            hay = " ".join(str(p.get(k, "")) for k in ("title", "hook", "caption", "pillar", "festival", "topic_ref", "id")).lower()
            if q in hay:
                res.append(p)
    return render_template("search.html", q=q, res=res[:100])


# ---------------------------------------------------------------- sign-in
@app.route("/login")
def login():
    if not auth.enabled():
        return redirect(url_for("today_page"))
    nxt = request.args.get("next", "/")
    session["next"] = nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"
    return render_template("login.html", domains=auth.allowed_domains(), error=request.args.get("error"))


@app.route("/auth/login")
def auth_login():
    if not auth.enabled():
        return redirect(url_for("today_page"))
    if request.host.startswith("127.0.0.1"):          # Google only accepts "localhost" for local redirects
        return redirect(request.url.replace("127.0.0.1", "localhost", 1))
    return redirect(auth.login_url(request.host_url, session))


@app.route("/auth/callback")
def auth_callback():
    try:
        who = auth.finish(request.args, request.host_url, session)
    except auth.AuthError as e:
        return redirect(url_for("login", error=str(e)))
    member = teamlib.by_email(who["email"])
    if not member:
        return redirect(url_for("login", error=f"{who['email']} isn't on the content team yet. Ask an admin to add you under Team."))
    nxt = session.pop("next", "/")
    session.clear()
    session.permanent = True
    session["email"] = who["email"]
    session["picture"] = who.get("picture", "")
    return redirect(nxt)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login") if auth.enabled() else url_for("today_page"))


# ---------------------------------------------------------------- team
@app.route("/team", methods=["GET", "POST"])
def team_page():
    if request.method == "POST":
        f = request.form
        rows = []
        for i in range(int(f.get("n", 0)) + 1):
            name = f.get(f"name_{i}", "").strip()
            email = f.get(f"email_{i}", "").strip().lower()
            if not name and not email:
                continue
            if email and email.split("@")[-1] not in auth.allowed_domains():
                flash(f"{email}: only {', '.join(auth.allowed_domains())} addresses can sign in.", "error")
            rows.append({"name": name, "email": email, "title": f.get(f"title_{i}", "").strip(),
                         "role": f.get(f"role_{i}", "viewer"), "voice": f.get(f"voice_{i}", ""),
                         "brand_signoff": f.get(f"signoff_{i}") == "1", "active": f.get(f"active_{i}") == "1"})
        if not any(r["role"] == "admin" and r["active"] and r["email"] for r in rows):
            flash("Keep at least one active admin with an email — not saved.", "error")
            return redirect(url_for("team_page"))
        voices = [r["voice"] for r in rows if r["voice"] and r["active"]]
        if len(voices) != len(set(voices)):
            flash("Each voice (Sunil, Raj, Shrutik, KC) can belong to only one person — not saved.", "error")
            return redirect(url_for("team_page"))
        teamlib.save(rows)
        flash("Team saved.", "ok")
        return redirect(url_for("team_page"))
    return render_template("team.html", team=teamlib.load(), roles=teamlib.ROLES)


# ---------------------------------------------------------------- notifications
@app.route("/notifications")
def notifications_page():
    items = notify.inbox(g.user.get("email", ""))
    return render_template("notifications.html", items=items[:200])


@app.post("/api/notifications/read")
def api_notif_read():
    nid = (request.get_json(silent=True) or {}).get("id")
    notify.mark_read(g.user.get("email", ""), nid)
    return jsonify(ok=True)


@app.post("/api/notify/test")
def api_notify_test():
    n = notify.send([g.user], "Test notification", "If you can read this, studio notifications reach you.", "/notifications", "test")
    s = load_settings()
    channels = ["in-app"] + (["email"] if s.get("smtp_user") and s.get("smtp_password") and s.get("notify_email") else []) \
        + (["chat webhook"] if s.get("chat_webhook") else [])
    return jsonify(ok=bool(n), message=f"Sent via {', '.join(channels)}. Email/webhook results appear in the delivery log in a few seconds.")


# ---------------------------------------------------------------- Decoded (newsletter, every Wednesday)
def _nl_post(pid):
    p = get_post(pid)
    if not p or p["platform"] != "newsletter":
        abort(404)
    return p


@app.route("/decoded")
def decoded_page():
    from core import decoded, decoded_ai
    rows = []
    for p in fresh(all_posts("newsletter")):
        md = (p.get("newsletter") or {}).get("markup") or ""
        iss = decoded.check(md, folder_of(p) / "images") if md else [{"severity": "error", "message": "No issue text yet"}]
        rows.append({"p": p, "n": (p.get("newsletter") or {}).get("issue"), "words": decoded.word_count(md),
                     "errors": sum(i["severity"] == "error" for i in iss), "warns": sum(i["severity"] == "warn" for i in iss),
                     "data_needed": md.count("DATA NEEDED")})
    rows.sort(key=lambda r: r["p"]["date"])
    open_issues = [r for r in rows if r["p"]["date"] >= today().isoformat() and r["p"].get("status") not in ("published", "skipped")]
    ideas = [i for i in decoded_ai.load_ideas() if i.get("status") == "new"]
    return render_template("decoded.html", rows=rows, ideas=ideas, open_issues=open_issues)


@app.post("/api/decoded/ideas")
def api_decoded_ideas():
    from core import decoded_ai, ledger
    d = request.get_json(silent=True) or {}
    try:
        made = decoded_ai.generate_ideas(int(d.get("n") or 5), d.get("item_ids") or None, d.get("steer", ""))
    except (ai.AIError, ledger.OverBudget) as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, n=len(made))


@app.post("/api/decoded/ideas/<iid>")
def api_decoded_idea(iid):
    from core import decoded_ai
    d = request.get_json(force=True) or {}
    if d.get("use_in"):
        p = decoded_ai.use_idea(iid, d["use_in"])
        return jsonify(ok=True, id=p["id"])
    decoded_ai.set_idea_status(iid, d.get("status", "dropped"))
    return jsonify(ok=True)


@app.route("/decoded/<pid>")
def decoded_editor(pid):
    from core import decoded
    p = _nl_post(pid)
    nl = p.get("newsletter") or {}
    md = nl.get("markup") or ""
    files = sorted(f.name for f in (folder_of(p) / "images").glob("*")) if (folder_of(p) / "images").exists() else []
    return render_template("decoded_edit.html", p=p, nl=nl, md=md, files=files,
                           issues=decoded.check(md, folder_of(p) / "images") if md else [],
                           words=decoded.word_count(md), outline=decoded.outline(md) if md else [])


@app.post("/api/decoded/<pid>/save")
def api_decoded_save(pid):
    from core import decoded
    p = _nl_post(pid)
    md = (request.get_json(force=True) or {}).get("markup", "")
    nl = p.setdefault("newsletter", {})
    if md != nl.get("markup"):
        hist = nl.setdefault("history", [])
        if nl.get("markup"):
            hist.insert(0, {"at": now_iso(), "markup": nl["markup"], "why": "before edit"})
            del hist[10:]
        nl["markup"] = md
        meta, _ = decoded.parse(md)
        if meta.get("title"):
            p["title"] = meta["title"]
        if p.get("status") in ("approved", "scheduled"):
            p["status"] = "draft"          # approval is of the words
        save_post(p, note=f"{actor()}: edited the issue")
    issues = decoded.check(md, folder_of(p) / "images")
    return jsonify(ok=True, issues=issues, words=decoded.word_count(md), status=p.get("status"))


@app.route("/decoded/<pid>/preview", methods=["GET", "POST"])
def decoded_preview(pid):
    from core import decoded
    p = _nl_post(pid)
    md = request.form.get("markup") if request.method == "POST" else (p.get("newsletter") or {}).get("markup", "")
    try:
        out = decoded.render(md or "", folder_of(p) / "images", embed=False)
    except decoded.DecodedError as e:
        return f"<p style='font-family:Georgia;padding:20px;color:#B42318'>{escape(str(e))}</p>"
    # relative figure files resolve to this post's media; links open in a new tab
    return out.replace("<head>", f'<head>\n<base href="/media/{p["id"]}/" target="_blank">', 1)


@app.get("/decoded/<pid>/export.html")
def decoded_export(pid):
    from core import decoded
    import io
    p = _nl_post(pid)
    md = (p.get("newsletter") or {}).get("markup", "")
    errs = [i["message"] for i in decoded.check(md, folder_of(p) / "images") if i["severity"] == "error"]
    if errs and request.args.get("draft") != "1":
        return render_template("message.html", title="Not ready to export", msg="Fix first: " + " · ".join(errs)), 400
    out = decoded.render(md, folder_of(p) / "images", embed=True)
    n = (p.get("newsletter") or {}).get("issue")
    name = f"decoded-issue-{int(n):02d}{'-DRAFT' if errs else ''}.html" if str(n).isdigit() else f"{p['slug']}.html"
    return send_file(io.BytesIO(out.encode("utf-8")), mimetype="text/html", as_attachment=True, download_name=name)


@app.post("/api/decoded/<pid>/figure")
def api_decoded_figure(pid):
    p = _nl_post(pid)
    f = request.files.get("file")
    if not f or not re.search(r"\.(png|jpe?g|gif|webp)$", f.filename or "", re.I):
        return jsonify(ok=False, error="Upload a PNG, JPG, GIF or WebP."), 400
    img = folder_of(p) / "images"
    img.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(m.group(1)) for x in img.glob("fig_*") if (m := re.match(r"fig_(\d+)", x.name))] or [0])
    name = f"fig_{n:02d}.{f.filename.rsplit('.', 1)[1].lower().replace('jpeg', 'jpg')}"
    f.save(img / name)
    p["images"] = sorted(set((p.get("images") or []) + [name]))
    save_post(p)
    return jsonify(ok=True, name=name)


@app.post("/api/decoded/<pid>/ai")
def api_decoded_ai(pid):
    from core import decoded_ai, ledger
    _nl_post(pid)
    d = request.get_json(force=True) or {}
    try:
        res = decoded_ai.draft_issue(pid, d.get("instruction", ""), d.get("item_ids") or None, d.get("urls", ""))
    except (ai.AIError, ledger.OverBudget, ValueError) as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, **res)


@app.post("/api/decoded/<pid>/promo")
def api_decoded_promo(pid):
    from core import decoded_ai
    _nl_post(pid)
    try:
        res = decoded_ai.promo_pack(pid)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, **res)


@app.post("/api/decoded/<pid>/restore")
def api_decoded_restore(pid):
    p = _nl_post(pid)
    nl = p.get("newsletter") or {}
    hist = nl.get("history") or []
    if not hist:
        return jsonify(ok=False, error="No earlier version."), 400
    prev = hist.pop(0)
    nl["markup"] = prev["markup"]
    save_post(p, note=f"{actor()}: restored the version from {prev['at']}")
    return jsonify(ok=True)


# ---------------------------------------------------------------- video (raea + Whisper)
@app.route("/api/post/<pid>/video", methods=["GET", "POST"])
def api_post_video(pid):
    from core import video as vid
    if request.method == "GET":
        return jsonify({**vid.status(pid), "ok": True})
    p = get_post(pid)
    if not p:
        return jsonify(ok=False, error="Post not found"), 404
    if studio_plus.media_blocked(p):
        return jsonify(ok=False, error=BLOCKED_MSG), 400
    mode = request.form.get("mode") or (request.get_json(silent=True) or {}).get("mode") or "motion"
    footage = None
    if mode == "footage":
        f = request.files.get("file")
        if not f or not re.search(r"\.(mp4|mov|m4v|webm)$", f.filename or "", re.I):
            return jsonify(ok=False, error="Upload the filmed take (.mp4, .mov, .m4v)."), 400
        proj = vid.project_dir(p)
        (proj / "upload").mkdir(parents=True, exist_ok=True)
        footage = proj / "upload" / re.sub(r"[^\w.-]", "_", f.filename)
        f.save(footage)
    try:
        job = vid.start(pid, mode, footage, redo_voice=(request.form.get("redo_voice") or (request.get_json(silent=True) or {}).get("redo_voice")) in (True, "1"))
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, **{k: v for k, v in job.items() if k != "log_file"})


import studio_plus  # noqa: E402

studio_plus.register(app)

BLOCKED_MSG = ("Read the script first. Media is made only after you choose the script "
               "(Use this script) or replace it with your own content.")


@app.errorhandler(404)
def nf(e):
    return render_template("message.html", title="Not found", msg="That page or post doesn't exist (it may have been renamed when its date changed)."), 404


if __name__ == "__main__":
    scheduler.start()
    port = int(os.getenv("STUDIO_PORT", "5055"))
    print(f"\n  Galvor Social Studio → http://localhost:{port}\n")
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=8)   # local only; team access goes through the tunnel
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
