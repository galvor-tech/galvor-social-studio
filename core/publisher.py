"""Publishing to LinkedIn (Posts API) and Instagram (Graph API).

Nothing here runs unless Settings → Publishing has valid tokens AND auto-publish is on (or you click
"Publish now"). Without tokens, scheduled posts surface in Today as "Due — post manually" with
copy buttons and image downloads, so the workflow never stops.

LinkedIn needs: an app with the Community Management API (w_organization_social for the company page,
w_member_social for personal profiles) and an access token per author.
Instagram needs: an Instagram Business/Creator account linked to a Facebook Page, a long-lived token with
instagram_content_publish, the IG user id, and a PUBLIC base URL that serves this studio's images
(Instagram downloads images from a URL; it can't read files on this laptop).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from .config import load_settings
from .store import folder_of

UA = "GalvorSocialStudio/1.0"


class PublishError(RuntimeError):
    pass


def _req(method: str, url: str, headers: dict | None = None, body: bytes | dict | None = None, timeout=60):
    h = {"User-Agent": UA, **(headers or {})}
    data = None
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    elif body is not None:
        data = body
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, dict(r.headers), (json.loads(raw) if raw and raw[:1] in b"{[" else raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:500]
        raise PublishError(f"{method} {url.split('?')[0]} → HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise PublishError(f"Network error: {e.reason}") from e


# ================================================================ LinkedIn
def _li_version() -> str:
    v = load_settings().get("linkedin_api_version")
    if v:
        return v
    d = date.today()
    m = d.month - 2
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y}{m:02d}"


def _li_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "LinkedIn-Version": _li_version(),
            "X-Restli-Protocol-Version": "2.0.0"}


RESERVED = set("\\|{}@[]()<>#*_~")


def little_text(text: str) -> str:
    """Escape LinkedIn 'little text' reserved chars; turn #tags into real hashtags."""
    import re
    out, i = [], 0
    for m in re.finditer(r"(?<![\w&])#([A-Za-z0-9_]+)", text):
        out.append("".join("\\" + c if c in RESERVED else c for c in text[i:m.start()]))
        tag = "".join("\\" + c if c in RESERVED else c for c in m.group(1))
        out.append("{hashtag|\\#|" + tag + "}")
        i = m.end()
    out.append("".join("\\" + c if c in RESERVED else c for c in text[i:]))
    return "".join(out)


def _li_author(post: dict, s: dict) -> tuple[str, str]:
    voice = post.get("voice") or "company"
    if voice == "company":
        urn, token = s.get("linkedin_org_urn"), s.get("linkedin_access_token")
    else:
        urn = (s.get("linkedin_person_urns") or {}).get(voice)
        token = (s.get("linkedin_person_tokens") or {}).get(voice) or s.get("linkedin_access_token")
    if not urn or not token:
        raise PublishError(f"No LinkedIn author URN/token configured for “{voice}”. Add it in Settings → Publishing.")
    return urn, token


def _li_upload(kind: str, owner: str, token: str, path: Path) -> str:
    st, _, body = _req("POST", f"https://api.linkedin.com/rest/{kind}s?action=initializeUpload",
                       _li_headers(token), {"initializeUploadRequest": {"owner": owner}})
    val = body["value"]
    _req("PUT", val["uploadUrl"], {"Authorization": f"Bearer {token}"}, path.read_bytes(), timeout=180)
    return val[kind]


def publish_linkedin(post: dict) -> dict:
    s = load_settings()
    author, token = _li_author(post, s)
    folder = folder_of(post) / "images"
    caption = post.get("caption", "").rstrip()
    tags = " ".join(t if t.startswith("#") else "#" + t for t in post.get("hashtags") or [])
    text = little_text(f"{caption}\n\n{tags}".strip() if tags else caption)
    payload = {
        "author": author, "commentary": text, "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
    }
    fmt = post.get("format")
    images = [f for f in post.get("images") or [] if f.endswith(".png")]
    alt = (post.get("alt_text") or "")[:4000]
    if fmt == "poll":
        poll = post.get("poll") or {}
        payload["content"] = {"poll": {"question": poll["question"],
                                       "options": [{"text": o} for o in poll["options"]],
                                       "settings": {"duration": {"1 day": "ONE_DAY", "3 days": "THREE_DAYS",
                                                                 "2 weeks": "TWO_WEEKS"}.get(poll.get("duration"), "ONE_WEEK")}}}
    elif fmt == "carousel" and (folder / "carousel.pdf").exists():
        doc = _li_upload("document", author, token, folder / "carousel.pdf")
        payload["content"] = {"media": {"title": (post.get("title") or "Galvor")[:400], "id": doc}}
    elif fmt == "video":
        raise PublishError("LinkedIn video: upload the edited video manually (the studio provides script + cover).")
    elif images and fmt in ("image", "text", "newsletter", "article"):
        img = _li_upload("image", author, token, folder / images[0])
        payload["content"] = {"media": {"id": img, "altText": alt[:4086]}}
    st, headers, _ = _req("POST", "https://api.linkedin.com/rest/posts", _li_headers(token), payload)
    urn = headers.get("x-restli-id") or headers.get("X-RestLi-Id") or ""
    result = {"platform": "linkedin", "urn": urn, "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else ""}
    if post.get("first_comment") and urn:
        try:
            enc = urllib.parse.quote(urn, safe="")
            _req("POST", f"https://api.linkedin.com/rest/socialActions/{enc}/comments", _li_headers(token),
                 {"actor": author, "object": urn, "message": {"text": post["first_comment"]}})
            result["first_comment"] = "posted"
        except PublishError as e:
            result["first_comment"] = f"failed: {e}"
    return result


# ================================================================ Instagram
def _graph() -> str:
    return f"https://graph.facebook.com/{load_settings().get('graph_api_version') or 'v23.0'}"


def _ig_wait(container: str, token: str, tries: int = 30) -> None:
    for _ in range(tries):
        _, _, body = _req("GET", f"{_graph()}/{container}?fields=status_code&access_token={token}")
        code = body.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram container {container} status {code}.")
        time.sleep(4)
    raise PublishError("Instagram took too long to process the media.")


def publish_instagram(post: dict) -> dict:
    s = load_settings()
    token, uid, base = s.get("instagram_access_token"), s.get("instagram_user_id"), (s.get("public_base_url") or "").rstrip("/")
    if not (token and uid):
        raise PublishError("Instagram token / user id missing. Add them in Settings → Publishing.")
    if not base.startswith("https://"):
        raise PublishError("Instagram needs a public https URL for images (Settings → Public base URL).")
    fmt = post.get("format")
    if fmt == "reel":
        raise PublishError("Reels need the edited video — upload manually (script + cover are in the post folder).")
    images = [f for f in post.get("images") or [] if f.endswith(".png")]
    if not images:
        raise PublishError("Render the images first.")
    url = lambda f: f"{base}/media/{urllib.parse.quote(post['id'])}/{f}"  # noqa: E731
    caption = post.get("caption", "").rstrip()
    tags = " ".join(t if t.startswith("#") else "#" + t for t in post.get("hashtags") or [])
    caption = f"{caption}\n\n{tags}".strip() if tags else caption

    def create(params):
        params["access_token"] = token
        _, _, b = _req("POST", f"{_graph()}/{uid}/media", body=urllib.parse.urlencode(params).encode(),
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
        return b["id"]

    if fmt == "story":
        ids = []
        for f in images:
            c = create({"image_url": url(f), "media_type": "STORIES"})
            _ig_wait(c, token)
            _, _, b = _req("POST", f"{_graph()}/{uid}/media_publish",
                           body=urllib.parse.urlencode({"creation_id": c, "access_token": token}).encode(),
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
            ids.append(b["id"])
        return {"platform": "instagram", "media_ids": ids, "url": ""}
    if len(images) == 1:
        container = create({"image_url": url(images[0]), "caption": caption, "alt_text": (post.get("alt_text") or "")[:1000]})
    else:
        children = [create({"image_url": url(f), "is_carousel_item": "true"}) for f in images[:20]]
        for c in children:
            _ig_wait(c, token)
        container = create({"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})
    _ig_wait(container, token)
    _, _, b = _req("POST", f"{_graph()}/{uid}/media_publish",
                   body=urllib.parse.urlencode({"creation_id": container, "access_token": token}).encode(),
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
    media_id = b["id"]
    result = {"platform": "instagram", "media_id": media_id, "url": ""}
    try:
        _, _, pl = _req("GET", f"{_graph()}/{media_id}?fields=permalink&access_token={token}")
        result["url"] = pl.get("permalink", "")
    except PublishError:
        pass
    if post.get("first_comment"):
        try:
            _req("POST", f"{_graph()}/{media_id}/comments",
                 body=urllib.parse.urlencode({"message": post["first_comment"], "access_token": token}).encode(),
                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        except PublishError as e:
            result["first_comment"] = f"failed: {e}"
    return result


def can_auto_publish(post: dict) -> tuple[bool, str]:
    s = load_settings()
    if post["platform"] == "linkedin":
        if post.get("format") == "video":
            return False, "Video needs a manual upload."
        try:
            _li_author(post, s)
        except PublishError as e:
            return False, str(e)
        return True, ""
    if post["platform"] == "instagram":
        if post.get("format") == "reel":
            return False, "Reels need a manual upload."
        if not (s.get("instagram_access_token") and s.get("instagram_user_id") and (s.get("public_base_url") or "").startswith("https://")):
            return False, "Instagram API not configured."
        return True, ""
    return False, "Newsletters are sent from your email tool."


def publish(post: dict) -> dict:
    if post["platform"] == "linkedin":
        return publish_linkedin(post)
    if post["platform"] == "instagram":
        return publish_instagram(post)
    raise PublishError("Newsletters are sent from your email tool / LinkedIn newsletter editor.")
