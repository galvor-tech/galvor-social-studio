"""Notifications: in-app inbox (always on) + email via SMTP + Google Chat / Slack webhook (optional).

Events: review requested · approved · sent back · scheduled post due · auto-publish failed.
Email/webhook sends run in a background thread so the UI never waits on them.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import threading
import urllib.request
import uuid
from email.message import EmailMessage
from html import escape

from .config import DATA, LOGS, load_settings
from .store import now_iso

INBOX = DATA / "notifications.json"
_lock = threading.RLock()


def _log(msg: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "notify.log", "a", encoding="utf-8") as f:
        f.write(f"{now_iso()}  {msg}\n")


def _load() -> list[dict]:
    try:
        return json.loads(INBOX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    tmp = INBOX.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-2000:], indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INBOX)


def inbox(email: str, include_read: bool = True) -> list[dict]:
    e = (email or "").lower()
    items = [n for n in _load() if n["to"] == e and (include_read or not n.get("read"))]
    return list(reversed(items))


def unread(email: str) -> int:
    return len(inbox(email, include_read=False))


def mark_read(email: str, nid: str | None = None) -> None:
    with _lock:
        items = _load()
        for n in items:
            if n["to"] == (email or "").lower() and (nid is None or n["id"] == nid):
                n["read"] = True
        _save(items)


def link(path: str) -> str:
    base = (load_settings().get("base_url") or "http://localhost:5055").rstrip("/")
    return base + path


def send(recipients: list[dict], subject: str, body: str, path: str = "", event: str = "", exclude: str = "") -> int:
    """recipients: team members (dicts with email/name). Returns how many were notified in-app."""
    seen, targets = set(), []
    for r in recipients:
        e = (r.get("email") or "").lower()
        if e and e not in seen and e != (exclude or "").lower():
            seen.add(e)
            targets.append(r)
    with _lock:
        items = _load()
        for r in targets:
            items.append({"id": uuid.uuid4().hex[:12], "to": r["email"].lower(), "at": now_iso(), "event": event,
                          "subject": subject, "body": body, "path": path, "read": False})
        _save(items)
    s = load_settings()
    if targets and s.get("smtp_user") and s.get("smtp_password") and s.get("notify_email", True):
        threading.Thread(target=_email, args=([r["email"] for r in targets], subject, body, path), daemon=True).start()
    if s.get("chat_webhook"):
        names = ", ".join(r.get("name") or r["email"] for r in targets) or "team"
        threading.Thread(target=_webhook, args=(f"*{subject}*\n{body}\nFor: {names}\n{link(path) if path else ''}",),
                         daemon=True).start()
    return len(targets)


def _email(to: list[str], subject: str, body: str, path: str) -> None:
    s = load_settings()
    url = link(path) if path else link("/")
    msg = EmailMessage()
    msg["Subject"] = f"[Galvor Studio] {subject}"
    msg["From"] = s.get("smtp_from") or s["smtp_user"]
    msg["To"] = ", ".join(to)
    msg.set_content(f"{body}\n\nOpen in Galvor Social Studio: {url}\n")
    msg.add_alternative(f"""<div style="font-family:Inter,Segoe UI,Arial,sans-serif;max-width:560px;color:#16131F">
<div style="font-weight:700;font-size:16px;color:#5B2BD6;margin-bottom:12px">Galvor Social Studio</div>
<div style="font-size:18px;font-weight:700;margin-bottom:8px">{escape(subject)}</div>
<div style="font-size:14px;line-height:1.55;white-space:pre-wrap">{escape(body)}</div>
<a href="{escape(url)}" style="display:inline-block;margin-top:18px;background:#5B2BD6;color:#fff;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:600">Open in the studio</a>
<div style="font-size:12px;color:#9B97A8;margin-top:20px">You get this because you're on the Galvor content team.</div></div>""", subtype="html")
    try:
        port = int(s.get("smtp_port") or 587)
        host = s.get("smtp_host") or "smtp.gmail.com"
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as srv:
                srv.login(s["smtp_user"], s["smtp_password"])
                srv.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as srv:
                srv.starttls(context=ssl.create_default_context())
                srv.login(s["smtp_user"], s["smtp_password"])
                srv.send_message(msg)
        _log(f"EMAIL ok → {to}: {subject}")
    except Exception as e:  # logged; shown on Settings
        _log(f"EMAIL FAILED → {to}: {subject}: {e}")


def _webhook(text: str) -> None:
    url = load_settings().get("chat_webhook")
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json; charset=UTF-8"}, method="POST")
        with urllib.request.urlopen(req, timeout=20):
            pass
        _log("WEBHOOK ok")
    except Exception as e:
        _log(f"WEBHOOK FAILED: {e}")


def recent_log(n: int = 8) -> list[str]:
    try:
        return (LOGS / "notify.log").read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
