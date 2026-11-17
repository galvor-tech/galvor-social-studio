"""End-to-end tests for review routing, permissions, sign-in gating and notifications.
Leaves posts, settings, team and inbox exactly as it found them."""
import json
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BACKUP = {f: (ROOT / "data" / f).read_bytes() if (ROOT / "data" / f).exists() else None
          for f in ("settings.json", "team.json", "notifications.json")}

from app import app                                       # noqa: E402
from core import auth, notify, team                       # noqa: E402
from core.config import load_settings, save_settings      # noqa: E402
from core.store import all_posts, folder_of, get_post, save_post  # noqa: E402

ok = True


def chk(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)


def pick(voice, platform="linkedin"):
    return next(p for p in all_posts(platform) if p.get("voice") == voice and p["status"] == "designed" and p["date"] >= "2026-11-20")


snap = {}
def remember(p):
    snap[p["id"]] = (folder_of(p) / "post.json").read_bytes()


try:
    team.save(team.DEFAULT_TEAM)
    c = app.test_client()
    # ---------------- routing
    sp, rp, cp, ip = pick("sunil"), pick("raj"), pick("company"), pick("company", "instagram")
    for p in (sp, rp, cp, ip):
        remember(p)
    chk([m["name"] for m in team.reviewers_for(sp)] == ["Sunil Humne"], "Sunil's post → Sunil reviews")
    chk([m["name"] for m in team.reviewers_for(rp)][0] == "Raj Dhakad", "Raj's post → Raj reviews")
    chk({m["name"] for m in team.reviewers_for(ip)} == {"Suyash", "Sunil Humne"}, "Instagram → brand sign-off (Suyash + Sunil)")
    q = dict(sp, caption=sp["caption"] + "\nWe worked with Blue Nectar on this.")
    chk({m["name"] for m in team.reviewers_for(q)} == {"Sunil Humne", "Suyash"}, "client name → brand sign-off added")

    # ---------------- local mode: send for review → notification
    j = c.post(f"/api/post/{sp['id']}/status", json={"status": "in_review"}).get_json()
    chk(j["ok"] and "Sunil Humne" in j["message"] and j["notified"] == 1, f"send for review notifies Sunil ({j.get('message')})")
    inbox = notify.inbox("sunil@galvor.com")
    chk(inbox and inbox[0]["subject"].startswith("Review needed") and inbox[0]["path"] == f"/post/{sp['id']}", "Sunil's inbox has the request + link")
    chk(get_post(sp["id"])["review"]["reviewers"] == ["sunil@galvor.com"], "reviewers stored on post")
    j = c.post(f"/api/post/{rp['id']}/status", json={"status": "in_review"}).get_json()
    chk(j["ok"] and "no email on file for Raj" in j["message"], "Raj without email → clear warning")
    j = c.post(f"/api/post/{sp['id']}/status", json={"status": "draft", "note": "Shorter hook please"}).get_json()
    chk(j["ok"], "admin can send back")
    chk(any("Shorter hook" in n["body"] for n in notify.inbox("sunil@galvor.com")), "author told about requested changes")

    # ---------------- sign-in ON
    s = load_settings()
    s.update(auth_mode="google", google_client_id="test-id.apps.googleusercontent.com", google_client_secret="x",
             base_url="https://studio.galvor.ai", allowed_domains=["galvor.com"])
    save_settings(s)
    chk(auth.enabled(), "auth enabled")
    c2 = app.test_client()
    r = c2.get("/")
    chk(r.status_code == 302 and "/login" in r.headers["Location"], "signed-out user → /login")
    chk(c2.post(f"/api/post/{sp['id']}/status", json={"status": "in_review"}).status_code == 401, "signed-out API → 401")
    img = next(f for f in sp["images"] if f.endswith(".png"))
    chk(c2.get(f"/media/{sp['id']}/{img}").status_code == 200, "/media stays public (Instagram needs it)")
    r = c2.get("/auth/login", base_url="https://studio.galvor.ai")
    loc = r.headers["Location"]
    chk(loc.startswith("https://accounts.google.com/") and "hd=galvor.com" in loc and
        "redirect_uri=https%3A%2F%2Fstudio.galvor.ai%2Fauth%2Fcallback" in loc, "Google redirect with domain hint + right callback")
    r = c2.get("/auth/login", base_url="http://127.0.0.1:5055")
    chk(r.headers["Location"].startswith("http://localhost:5055/"), "127.0.0.1 normalised to localhost")
    r = c2.get("/auth/callback?state=wrong&code=x", base_url="https://studio.galvor.ai")
    chk("/login?error=" in r.headers["Location"], "state mismatch rejected")

    real_finish = auth.finish
    def fake_finish(email):
        def f(args, host, sess):
            sess.pop("oauth_state", None)
            return {"email": email, "name": email}
        return f
    auth.finish = fake_finish("stranger@galvor.com")
    r = c2.get("/auth/callback?state=s&code=x")
    chk("isn't on the content team" in r.headers["Location"].replace("%20", " ").replace("%27", "'").replace("+", " "), "Galvor account not on Team → refused")
    auth.finish = fake_finish("sunil@galvor.com")
    r = c2.get("/auth/callback?state=s&code=x")
    chk(r.status_code == 302 and c2.get("/").status_code == 200, "team member signs in")
    auth.finish = real_finish

    # Sunil (approver): approve own, not Raj's; no settings
    cs = app.test_client()
    with cs.session_transaction() as ss:
        ss["email"] = "suyash@galvor.com"
    chk(cs.post(f"/api/post/{sp['id']}/status", json={"status": "in_review"}).get_json()["ok"], "Suyash (signed in) sends Sunil's post for review")
    chk(c2.post(f"/api/post/{sp['id']}/status", json={"status": "approved"}).get_json()["ok"], "Sunil approves his own post")
    chk(any(n["subject"].startswith("Approved") for n in notify.inbox("suyash@galvor.com")), "sender (Suyash) told it's approved")
    r = c2.post(f"/api/post/{rp['id']}/status", json={"status": "approved"})
    chk(r.status_code == 403 and "Raj Dhakad" in r.get_json()["error"], "Sunil can't approve Raj's post")
    chk(c2.get("/settings").status_code == 403 and c2.get("/team").status_code == 403, "approver can't open Settings/Team")
    chk(c2.post(f"/api/post/{sp['id']}/delete").status_code == 403, "non-admin can't delete")
    # Shrutik (editor)
    c3 = app.test_client()
    with c3.session_transaction() as ss:
        ss["email"] = "shrutik@galvor.com"
    chk(c3.post(f"/api/post/{cp['id']}/status", json={"status": "in_review"}).get_json()["ok"], "editor can send for review")
    chk(c3.post(f"/api/post/{cp['id']}/status", json={"status": "approved"}).status_code == 403, "editor can't approve")
    # viewer
    t = team.load(); t[4]["email"] = "kc@galvor.com"; team.save(t)
    c4 = app.test_client()
    with c4.session_transaction() as ss:
        ss["email"] = "kc@galvor.com"
    chk(c4.get("/calendar").status_code == 200 and c4.post(f"/api/post/{cp['id']}/save", json={"title": "x"}).status_code == 403, "viewer reads but can't edit")
    # tunnel safety with auth off
    s["auth_mode"] = "off"; save_settings(s)
    chk(app.test_client().get("/", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 403, "auth off + tunnel request → blocked")
    chk(app.test_client().get("/").status_code == 200, "auth off + local → works")

    # ---------------- email + webhook delivery
    import smtplib
    sent = []
    class FakeSMTP:
        def __init__(self, host, port, timeout=None): sent.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, context=None): sent.append(("tls",))
        def login(self, u, p): sent.append(("login", u))
        def send_message(self, m): sent.append(("msg", m["To"], m["Subject"], m.get_body(("html",)).get_content()))
    real_smtp = smtplib.SMTP
    smtplib.SMTP = FakeSMTP
    hits = []
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s.update(smtp_user="studio@galvor.com", smtp_password="app-pass", notify_email=True,
             chat_webhook=f"http://127.0.0.1:{srv.server_port}/hook", base_url="https://studio.galvor.ai")
    save_settings(s)
    notify.send([{"email": "sunil@galvor.com", "name": "Sunil"}], "Review needed: X", "Body", "/post/abc", "test")
    time.sleep(2)
    msgs = [x for x in sent if x[0] == "msg"]
    chk(("tls",) in sent and ("login", "studio@galvor.com") in sent, "SMTP uses STARTTLS + login")
    chk(msgs and msgs[0][1] == "sunil@galvor.com" and "https://studio.galvor.ai/post/abc" in msgs[0][3], "email sent with deep link")
    chk(hits and "Review needed: X" in hits[0]["text"], "Chat/Slack webhook posted")
    smtplib.SMTP = real_smtp
    srv.shutdown()
finally:
    for f, b in BACKUP.items():
        path = ROOT / "data" / f
        if b is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(b)
    for pid, raw in snap.items():
        cur = get_post(pid)
        if cur:
            (folder_of(cur) / "post.json").write_bytes(raw)
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)
