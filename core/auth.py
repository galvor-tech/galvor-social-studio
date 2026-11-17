"""Google sign-in (OAuth 2.0 / OpenID Connect, authorization-code flow) restricted to Galvor accounts.

Off by default: until a Google OAuth client is configured the studio only listens on 127.0.0.1 and
treats the laptop owner as the admin. Turn it on in Settings → Access once the client ID/secret exist.
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from .config import load_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class AuthError(RuntimeError):
    pass


def enabled() -> bool:
    s = load_settings()
    return s.get("auth_mode") == "google" and bool(s.get("google_client_id")) and bool(s.get("google_client_secret"))


def allowed_domains() -> list[str]:
    d = load_settings().get("allowed_domains") or ["galvor.com"]
    return [x.strip().lower().lstrip("@") for x in (d if isinstance(d, list) else str(d).split(",")) if x.strip()]


def redirect_uri(host_url: str) -> str:
    return host_url.rstrip("/") + "/auth/callback"


def login_url(host_url: str, session: dict) -> str:
    s = load_settings()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session["oauth_state"], session["oauth_nonce"] = state, nonce
    doms = allowed_domains()
    params = {
        "client_id": s["google_client_id"], "redirect_uri": redirect_uri(host_url), "response_type": "code",
        "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account",
    }
    if len(doms) == 1:
        params["hd"] = doms[0]          # hint only; enforced again below
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AuthError(f"Google rejected the sign-in ({e.code}).") from e
    except urllib.error.URLError as e:
        raise AuthError("Couldn't reach Google to finish sign-in.") from e


def _get_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AuthError(f"Google couldn't verify the sign-in token ({e.code}).") from e
    except urllib.error.URLError as e:
        raise AuthError("Couldn't reach Google to verify sign-in.") from e


def finish(args: dict, host_url: str, session: dict) -> dict:
    """Handle /auth/callback. Returns verified {'email','name','picture'} or raises AuthError."""
    s = load_settings()
    if args.get("error"):
        raise AuthError(f"Sign-in cancelled ({args['error']}).")
    state = session.pop("oauth_state", None)
    nonce = session.pop("oauth_nonce", None)
    if not state or args.get("state") != state:
        raise AuthError("Sign-in expired or was tampered with. Please try again.")
    tok = _post_form(TOKEN_URL, {
        "code": args.get("code", ""), "client_id": s["google_client_id"], "client_secret": s["google_client_secret"],
        "redirect_uri": redirect_uri(host_url), "grant_type": "authorization_code",
    })
    idt = tok.get("id_token")
    if not idt:
        raise AuthError("Google didn't return an identity token.")
    info = _get_json(TOKENINFO_URL + "?" + urllib.parse.urlencode({"id_token": idt}))
    if info.get("aud") != s["google_client_id"]:
        raise AuthError("Token was issued for a different app.")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise AuthError("Token issuer isn't Google.")
    if nonce and info.get("nonce") != nonce:
        raise AuthError("Sign-in nonce mismatch. Please try again.")
    if str(info.get("email_verified")).lower() != "true":
        raise AuthError("Your Google email isn't verified.")
    email = (info.get("email") or "").lower()
    domain = email.split("@")[-1]
    if domain not in allowed_domains() or (info.get("hd") or domain).lower() != domain:
        raise AuthError(f"Sign in with your {' / '.join('@' + d for d in allowed_domains())} account.")
    return {"email": email, "name": info.get("name") or email.split("@")[0], "picture": info.get("picture", "")}
