"""Team members, roles and review routing.

Roles: admin (everything incl. settings/team) · approver (can approve posts routed to them) ·
editor (create/edit/send for review) · viewer (read only).

Routing (who must approve a post):
  * Personal LinkedIn posts (sunil/raj/shrutik/kc) → the person whose name is on the post
    ("edit in your own voice" — plan §5). If the post names a client or makes a spend/ROAS claim,
    the brand sign-off owners are added too (plan: "Sunil gives final sign-off on anything that names
    a client or makes a claim").
  * Company page, Instagram and newsletter → everyone with brand_signoff = true.
  * Admins can always approve.
"""
from __future__ import annotations

import json
import threading

from .config import DATA

TEAM_FILE = DATA / "team.json"
ROLES = ["admin", "approver", "editor", "viewer"]
_lock = threading.RLock()

DEFAULT_TEAM = [
    {"email": "suyash@galvor.com", "name": "Suyash", "title": "Lead Marketing", "role": "admin", "voice": "", "brand_signoff": True, "active": True},
    {"email": "sunil@galvor.com", "name": "Sunil Humne", "title": "Co-founder", "role": "approver", "voice": "sunil", "brand_signoff": True, "active": True},
    {"email": "", "name": "Raj Dhakad", "title": "Founding AI Engineer", "role": "approver", "voice": "raj", "brand_signoff": False, "active": True},
    {"email": "shrutik@galvor.com", "name": "Shrutik Rathod", "title": "Client Servicing", "role": "editor", "voice": "shrutik", "brand_signoff": False, "active": True},
    {"email": "", "name": "KC", "title": "Investor & operator", "role": "viewer", "voice": "", "brand_signoff": False, "active": True},
]


def load() -> list[dict]:
    with _lock:
        if not TEAM_FILE.exists():
            save(DEFAULT_TEAM)
        try:
            return json.loads(TEAM_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return list(DEFAULT_TEAM)


def save(team: list[dict]) -> None:
    with _lock:
        for m in team:
            m["email"] = (m.get("email") or "").strip().lower()
            if m.get("role") not in ROLES:
                m["role"] = "viewer"
        tmp = TEAM_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(team, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(TEAM_FILE)


def by_email(email: str) -> dict | None:
    e = (email or "").strip().lower()
    return next((m for m in load() if m.get("email") == e and m.get("active", True)), None) if e else None


def by_voice(voice: str) -> dict | None:
    return next((m for m in load() if m.get("voice") == voice and m.get("active", True)), None)


def local_user() -> dict:
    """Identity used when sign-in is off (studio only reachable on this laptop)."""
    from .config import load_settings
    mine = (load_settings().get("local_user_email") or "").strip().lower()
    me = next((m for m in load() if mine and (m.get("email") or "").lower() == mine and m.get("active", True)), None)
    admins = [m for m in load() if m.get("role") == "admin" and m.get("active", True)]
    if me:
        u = dict(me)
        u["role"] = "admin"          # the person at the Studio laptop can always reach Settings
    else:
        u = dict(admins[0]) if admins else {"email": "", "name": "Local admin", "role": "admin"}
    u["local"] = True
    return u


def needs_brand_signoff(post: dict) -> bool:
    from .lint import lint_post
    return any("client permission" in i["message"] or "spend/ROAS claim" in i["message"] for i in lint_post(post))


def reviewers_for(post: dict) -> list[dict]:
    team = [m for m in load() if m.get("active", True)]
    voice = post.get("voice") or "company"
    out: list[dict] = []
    if post.get("platform") == "linkedin" and voice not in ("company", ""):
        owner = next((m for m in team if m.get("voice") == voice), None)
        if owner:
            out.append(owner)
        if needs_brand_signoff(post) or not owner:
            out += [m for m in team if m.get("brand_signoff") and m not in out]
    else:
        out += [m for m in team if m.get("brand_signoff")]
    if not out:
        out = [m for m in team if m.get("role") == "admin"]
    return out


def assigned(post: dict) -> list[dict]:
    """Who this post is waiting on: the people picked at "Send for review", else the routing rule."""
    picked = (post.get("review") or {}).get("reviewers") or []
    if post.get("status") == "in_review" and picked:
        out = [m for m in (by_email(e) for e in picked) if m]
        if out:
            return out
    return reviewers_for(post)


def pickable() -> list[dict]:
    """Team members who can be chosen as approver (active, with an email, not view-only)."""
    return [m for m in load() if m.get("active", True) and m.get("email") and m.get("role") != "viewer"]


def can_approve(user: dict, post: dict) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    picked = [e.lower() for e in ((post.get("review") or {}).get("reviewers") or [])]
    if post.get("status") == "in_review" and picked:
        # someone hand-picked as approver can review, edit and approve this post, whatever their role
        return can_edit(user) and (user.get("email") or "").lower() in picked
    if user.get("role") != "approver":
        return False
    return any(r.get("email") and r.get("email") == user.get("email") for r in reviewers_for(post))


def can_edit(user: dict) -> bool:
    return bool(user) and user.get("role") in ("admin", "approver", "editor")
