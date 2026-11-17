"""Discover: a daily scan of what people post about Meta ads, creators and D2C marketing.

Ported from galvor-cms sources.py. Source kinds:
- instagram_hashtag  HikerAPI top posts for a hashtag (Hiker has no keyword search for reels).
- instagram_account  HikerAPI recent posts of one account (competitor / peer watch).
- google             Apify google-search-scraper, results from the last 3 days (India).
- x                  Apify apidojo~tweet-scraper, top tweets for a search, last 3 days.
- linkedin_accounts  Apify harvestapi profile/company posts for a watchlist (one run per actor).
Every call is priced and checked against the daily cap (core.ledger) first.

Data: data/sources.json (list of sources), data/discover.json ({"items": [...], "scans": [...]}).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests

from . import ledger
from .config import DATA, load_env, load_settings

load_env()

SOURCES_FILE = DATA / "sources.json"
DISCOVER_FILE = DATA / "discover.json"

KINDS = {
    "instagram_hashtag": "Instagram hashtag",
    "instagram_account": "Instagram account",
    "google": "Google search",
    "x": "X search",
    "linkedin_accounts": "LinkedIn account",
}

# What each provider charges (same figures as the CMS config). Hiker bills every request, even an empty one.
HIKER_USD_PER_REQUEST = 0.001
APIFY_USD_PER_RESULT = {
    "apify~google-search-scraper": 0.0035,  # one result = one page of up to 10 links
    "apidojo~tweet-scraper": 0.0004,
    "harvestapi~linkedin-profile-posts": 0.002,
    "harvestapi~linkedin-company-posts": 0.002,
}

DEFAULT_SOURCES = [
    ("instagram_hashtag", "metaads", "#metaads"),
    ("instagram_hashtag", "facebookads", "#facebookads"),
    ("instagram_hashtag", "performancemarketing", "#performancemarketing"),
    ("instagram_hashtag", "influencermarketing", "#influencermarketing"),
    ("instagram_hashtag", "ugcads", "#ugcads"),
    ("instagram_hashtag", "creativestrategy", "#creativestrategy"),
    ("instagram_hashtag", "d2cbrands", "#d2cbrands"),
    ("google", "Meta ads update", "Meta ads update"),
    ("google", "Meta Andromeda creative", "Meta Andromeda creative"),
    ("google", "influencer marketing India D2C", "Influencer marketing India D2C"),
    ("google", "creator marketing ROI brands", "Creator marketing ROI"),
    ("x", "meta ads creative min_faves:50", "Meta ads creative (50+ likes)"),
    ("x", "ugc creators ads min_faves:50", "UGC creator ads (50+ likes)"),
    ("x", "creative strategy dtc min_faves:30", "DTC creative strategy (30+ likes)"),
]

PER_HASHTAG_KEEP = 12
PER_ACCOUNT_KEEP = 12
IG_MAX_AGE_DAYS = 21
X_PER_SEARCH = 15
LI_PER_ACCOUNT = 3
GOOGLE_RESULTS = 10
KEEP_DAYS = 30
KEEP_SCANS = 60

_lock = threading.RLock()
scan_lock = threading.Lock()  # held while a scan runs; the UI can check scan_lock.locked()


# ------------------------------------------------------------------ storage
def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path, data):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _db() -> dict:
    d = _read(DISCOVER_FILE, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("items", [])
    d.setdefault("scans", [])
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sid(kind, value) -> str:
    return hashlib.sha1(f"{kind}|{value}".lower().encode()).hexdigest()[:10]


def sources() -> list[dict]:
    """Every source: {id, kind, value, label, enabled[, user_id]}. Seeds the CMS defaults on first use."""
    with _lock:
        s = _read(SOURCES_FILE, None)
        if not isinstance(s, list):
            s = [{"id": _sid(k, v), "kind": k, "value": v, "label": lbl, "enabled": True}
                 for k, v, lbl in DEFAULT_SOURCES]
            _write(SOURCES_FILE, s)
        return s


def save_sources(lst: list[dict]) -> list[dict]:
    """Replace the source list. Validates kind/value, fills id/label/enabled, drops duplicates."""
    out, seen = [], set()
    for s in lst or []:
        kind, value = (s.get("kind") or "").strip(), str(s.get("value") or "").strip()
        if kind not in KINDS or not value:
            raise ValueError(f"Bad source: kind must be one of {list(KINDS)} and value must be set ({s!r}).")
        if kind == "instagram_hashtag":
            value = value.lstrip("#")
        if kind == "instagram_account":
            value = value.lstrip("@").strip("/").split("/")[-1]
        key = (kind, value.lower())
        if key in seen:
            continue
        seen.add(key)
        row = {"id": s.get("id") or _sid(kind, value), "kind": kind, "value": value,
               "label": s.get("label") or (f"#{value}" if kind == "instagram_hashtag" else
                                           f"@{value}" if kind == "instagram_account" else value),
               "enabled": bool(s.get("enabled", True))}
        if kind == "instagram_account" and s.get("user_id"):
            row["user_id"] = str(s["user_id"])
        out.append(row)
    with _lock:
        _write(SOURCES_FILE, out)
    return out


def estimate(srcs: list[dict] | None = None) -> float:
    """Cost in USD of one scan of the enabled sources (or of `srcs`)."""
    srcs = [s for s in (srcs if srcs is not None else sources()) if s.get("enabled", True)]
    usd = 0.0
    for s in srcs:
        k = s["kind"]
        if k == "instagram_hashtag":
            usd += HIKER_USD_PER_REQUEST
        elif k == "instagram_account":
            usd += HIKER_USD_PER_REQUEST * (1 if s.get("user_id") else 2)
        elif k == "google":
            usd += APIFY_USD_PER_RESULT["apify~google-search-scraper"]
        elif k == "x":
            usd += X_PER_SEARCH * APIFY_USD_PER_RESULT["apidojo~tweet-scraper"]
        elif k == "linkedin_accounts":
            usd += LI_PER_ACCOUNT * APIFY_USD_PER_RESULT["harvestapi~linkedin-profile-posts"]
    return round(usd, 4)


# ------------------------------------------------------------------ relevance
STRONG = [
    "meta ads", "facebook ads", "instagram ads", "performance marketing", "performance marketer", "roas", "cac",
    "cpa", "cpm", "ctr", "cpo", "cost per", "d2c", "dtc", "ugc", "influencer", "creator", "creative strategy",
    "ad creative", "ad creatives", "creative testing", "hook rate", "hold rate", "andromeda", "advantage+",
    "media buyer", "media buying", "paid social", "ad library", "ad account", "ecommerce", "e-commerce",
    "shopify", "conversion", "retargeting", "attribution", "brand marketing", "growth marketing", "funnel",
]
WEAK = ["ads", "ad", "meta", "marketing", "marketer", "brand", "brands", "creative", "creatives", "campaign",
        "audience", "content", "budget", "agency", "founder", "startup", "growth", "sales", "customer", "scale"]
_STRONG_RX = [re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])") for k in STRONG]
_WEAK_RX = [re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])") for k in WEAK]
RELEVANT_AT = 0.4

# Posts that use our keywords but are not about the work: job ads, people looking for work, giveaways.
NOISE = re.compile(
    r"(?i)(\bwe(?:'| a)?re hiring\b|\bhiring\b|\bnow hiring\b|\bjob (?:opening|alert|post|opportunit)|\bopen (?:position|role)s?\b"
    r"|\bvacanc(?:y|ies)\b|\bjoin our team\b|\bapply (?:now|here|today|via)\b|\bsend (?:your|us your) (?:cv|resume|portfolio)\b"
    r"|\b(?:cv|resume)s?\b.{0,30}\b(?:to|at)\b|\binternship\b|\bwalk[- ]in\b|\bfull[- ]time\b.{0,40}\b(?:role|position|remote)\b"
    r"|\b(?:base|salary|ctc|lpa)\b.{0,25}[$₹\d]|[$₹]\s?\d+\s?k?\s?[-–]\s?[$₹]?\s?\d+\s?k?\s?/\s?mo"
    r"|\bopen to work\b|\bavailable for (?:hire|work|freelance)\b|\blooking for (?:a |new )?(?:job|role|work|clients)\b"
    r"|\bgiveaway\b|\bwin a\b.{0,40}\b(?:follow|tag|comment)\b|#hiring|#jobs?\b|#jobopening|#vacancy)")


def is_noise(text: str) -> bool:
    return bool(NOISE.search(text or ""))


def relevance(text: str) -> float:
    """Cheap keyword relevance 0..1. Hashtags count half: off-topic viral reels stuff #marketing tags."""
    t = (text or "").lower()
    if is_noise(t):
        return 0.0
    tags = " ".join(re.findall(r"#(\w+)", t))
    body = re.sub(r"#\w+", " ", t)
    # split common concatenated hashtags so "#metaads" counts as "meta ads"
    tags = re.sub(r"(meta|facebook|instagram|ugc|performance|influencer|creator|creative|d2c|dtc|growth)",
                  r" \1 ", tags)
    score = 0.0
    for rx in _STRONG_RX:
        if rx.search(body):
            score += 1.0
        elif rx.search(tags):
            score += 0.3
    for rx in _WEAK_RX:
        if rx.search(body):
            score += 0.35
        elif rx.search(tags):
            score += 0.1
    return round(min(1.0, score / 2.5), 3)


def engagement(likes=0, comments=0, shares=0, views=0, rank=None) -> float:
    """One sortable number: likes + 2*comments + 3*shares + views/100. Google results have no counts,
    so they get a nominal value from their rank (rank 1 = 100 ... rank 10 = 10)."""
    e = (likes or 0) + 2 * (comments or 0) + 3 * (shares or 0) + (views or 0) / 100
    if not e and rank:
        e = max(1, 11 - int(rank)) * 10
    return round(e, 1)


def _score(item) -> float:
    return round(item.get("relevance", 0) * math.log10((item.get("engagement") or 0) + 10), 4)


# ------------------------------------------------------------------ providers
class SourceError(RuntimeError):
    pass


def _secret(name):
    import os
    v = os.environ.get(name)
    if not v:
        raise SourceError(f"{name} is not set in studio/.env.")
    return v


def _hiker(path, params):
    key = _secret("HIKER_KEY")
    if path in ledger.HIKER_SEARCH_PATHS:
        ledger.reserve_hiker_search(path)  # daily search limit + spend cap; records the spend
    else:
        ledger.check(HIKER_USD_PER_REQUEST, "An Instagram request")
        ledger.record("hiker", path, HIKER_USD_PER_REQUEST)  # billed even when empty
    r = requests.get(f"https://api.hikerapi.com{path}", params=params, timeout=60,
                     headers={"x-access-key": key, "accept": "application/json"})
    if r.status_code >= 400:
        raise SourceError(f"Instagram (Hiker) answered {r.status_code}: {r.text[:160]}")
    return r.json()


def _apify(actor, payload, max_results, what):
    unit = APIFY_USD_PER_RESULT[actor]
    ledger.check(unit * max_results, what)
    r = requests.post(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
                      params={"timeout": 150}, headers={"Authorization": f"Bearer {_secret('APIFY_API_TOKEN')}"},
                      json=payload, timeout=180)
    if r.status_code >= 400:  # say what failed without echoing the request URL
        raise SourceError(f"Apify answered {r.status_code} for {actor}: {r.text[:160]}")
    items = r.json()
    if not isinstance(items, list):
        items = []
    ledger.record("apify", actor, unit * max(len(items), 1))
    return items


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def _item(kind, source, url, author, text, posted_at, likes=0, comments=0, shares=0, views=0, rank=None,
          title=None, source_id=None):
    return {"source_kind": kind, "source": source, "source_id": source_id, "url": url, "author": author,
            "title": title, "text": text or "", "posted_at": posted_at,
            "likes": int(likes or 0), "comments": int(comments or 0), "shares": int(shares or 0),
            "views": int(views or 0), "rank": rank,
            "engagement": engagement(likes, comments, shares, views, rank)}


def _caption(m):
    c = m.get("caption")
    if isinstance(c, dict):
        return c.get("text") or ""
    if isinstance(c, str):
        return c
    return m.get("caption_text") or ""


def _ig_items(medias, kind, src, default_author=None, keep=PER_HASHTAG_KEEP):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=IG_MAX_AGE_DAYS)).timestamp()
    medias = [m for m in medias if (m.get("taken_at") or 0) >= cutoff]
    medias.sort(key=lambda m: m.get("play_count") or m.get("like_count") or 0, reverse=True)
    out = []
    for m in medias[:keep]:
        user = m.get("user") or {}
        code = m["code"]
        out.append(_item(
            kind, src["label"],
            f"https://www.instagram.com/reel/{code}/" if m.get("product_type") == "clips"
            else f"https://www.instagram.com/p/{code}/",
            user.get("username") or default_author, _caption(m)[:2000], _iso(m.get("taken_at")),
            likes=m.get("like_count"), comments=m.get("comment_count"), shares=m.get("reshare_count"),
            views=m.get("play_count") or m.get("view_count") or m.get("ig_play_count"), source_id=src.get("id")))
    return out


def fetch_instagram_hashtag(src):
    tag = src["value"].lstrip("#")
    data = _hiker("/v2/hashtag/medias/top", {"name": tag})
    found, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            m = o.get("media")
            if isinstance(m, dict) and m.get("code") and m["code"] not in seen:
                seen.add(m["code"])
                found.append(m)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data.get("response", data) if isinstance(data, dict) else data)
    return _ig_items(found, "instagram_hashtag", src)


def fetch_instagram_account(src):
    """Recent posts of one account: /v1/user/by/username once (user_id is cached on the source),
    then /g2/user/medias (one page). Two Hiker requests the first time, one after."""
    username = src["value"].lstrip("@")
    if not src.get("user_id"):
        u = _hiker("/v1/user/by/username", {"username": username})
        pk = (u or {}).get("pk") or (u or {}).get("id") or ((u or {}).get("user") or {}).get("pk")
        if not pk:
            raise SourceError(f"Instagram account @{username} not found.")
        src["user_id"] = str(pk)
    data = _hiker("/g2/user/medias", {"user_id": src["user_id"]})
    resp = data.get("response", data) if isinstance(data, dict) else data
    medias = resp.get("items", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
    medias = [m.get("media", m) if isinstance(m, dict) else {} for m in medias]
    medias = [m for m in medias if m.get("code")]
    return _ig_items(medias, "instagram_account", src, default_author=username, keep=PER_ACCOUNT_KEEP)


def fetch_google(src):
    res = _apify("apify~google-search-scraper",
                 {"queries": src["value"], "maxPagesPerQuery": 1, "resultsPerPage": GOOGLE_RESULTS,
                  "countryCode": "in", "quickDateRange": src.get("range") or "d3", "mobileResults": False},
                 1, "A Google search")
    out = []
    for page in res:
        for o in page.get("organicResults") or []:
            if not o.get("url"):
                continue
            title, desc = o.get("title") or "", o.get("description") or ""
            out.append(_item("google", src["label"], o["url"], o.get("displayedUrl"),
                             f"{title}\n{desc}".strip(), o.get("date"), rank=o.get("position"),
                             title=title or None, source_id=src.get("id")))
    return out


def fetch_x(src):
    since = (datetime.now() - timedelta(days=int(src.get("days") or 3))).strftime("%Y-%m-%d")
    res = _apify("apidojo~tweet-scraper",
                 {"searchTerms": [f"{src['value']} since:{since}"], "maxItems": X_PER_SEARCH, "sort": "Top"},
                 X_PER_SEARCH, "An X search")
    out = []
    for t in res:
        if not t.get("id") or not t.get("url"):
            continue
        author = t.get("author") or {}
        out.append(_item("x", src["label"], t["url"], author.get("userName") or author.get("name"),
                         (t.get("fullText") or t.get("text") or "")[:2000], t.get("createdAt"),
                         likes=t.get("likeCount"), comments=t.get("replyCount"),
                         shares=(t.get("retweetCount") or 0) + (t.get("quoteCount") or 0),
                         views=t.get("viewCount"), source_id=src.get("id")))
    return out


def fetch_linkedin_batch(accounts):
    """One Apify run per actor for the whole watchlist, not one per account."""
    out = []
    labels = {a["value"].rstrip("/"): a for a in accounts}
    for actor, group in (("harvestapi~linkedin-company-posts", [a for a in accounts if "/company/" in a["value"]]),
                         ("harvestapi~linkedin-profile-posts", [a for a in accounts if "/company/" not in a["value"]])):
        if not group:
            continue
        res = _apify(actor, {"targetUrls": [a["value"] for a in group], "maxPosts": LI_PER_ACCOUNT,
                             "scrapeReactions": False, "scrapeComments": False,
                             "includeQuotePosts": True, "includeReposts": False},
                     LI_PER_ACCOUNT * len(group), f"LinkedIn posts for {len(group)} accounts")
        cutoff = datetime.now(timezone.utc) - timedelta(days=4)
        for p in res:
            posted = (p.get("postedAt") or {}).get("date") if isinstance(p.get("postedAt"), dict) else p.get("postedAt")
            try:
                if posted and datetime.fromisoformat(str(posted).replace("Z", "+00:00")) < cutoff:
                    continue
            except ValueError:
                pass
            if not p.get("linkedinUrl"):
                continue
            eng = p.get("engagement") or {}
            q = p.get("query") or {}
            src_url = ((q.get("targetUrl") if isinstance(q, dict) else None) or "").rstrip("/")
            acc = labels.get(src_url) or {}
            out.append(_item("linkedin_accounts", acc.get("label") or "LinkedIn watchlist", p["linkedinUrl"],
                             (p.get("author") or {}).get("name") or acc.get("label"),
                             (p.get("content") or "")[:3000], posted,
                             likes=eng.get("likes"), comments=eng.get("comments"), shares=eng.get("shares"),
                             source_id=acc.get("id")))
    return out


FETCHERS = {
    "instagram_hashtag": fetch_instagram_hashtag,
    "instagram_account": fetch_instagram_account,
    "google": fetch_google,
    "x": fetch_x,
}


# ------------------------------------------------------------------ scan
def norm_url(url: str) -> str:
    u = urlsplit((url or "").strip())
    return f"{u.scheme.lower()}://{u.netloc.lower()}{u.path.rstrip('/')}" + (f"?{u.query}" if u.query else "")


def item_id(url: str) -> str:
    return hashlib.sha1(norm_url(url).encode()).hexdigest()[:12]


def _merge(db: dict, rows: list[dict], now: str) -> tuple[int, int]:
    """Dedupe by URL: a known URL gets fresh counts; hidden / used_in_ideas are kept."""
    by_id = {i["id"]: i for i in db["items"]}
    new = updated = 0
    for r in rows:
        if not r.get("url"):
            continue
        iid = item_id(r["url"])
        r["relevance"] = relevance(" ".join([r.get("title") or "", r.get("text") or ""]))
        r["relevant"] = r["relevance"] >= RELEVANT_AT
        if iid in by_id:
            old = by_id[iid]
            for k in ("likes", "comments", "shares", "views", "engagement", "rank"):
                if r.get(k) is not None:
                    old[k] = r[k]
            old["updated_at"] = now
            old["score"] = _score(old)
            updated += 1
            continue
        r.update(id=iid, fetched_at=now, updated_at=now, hidden=False, used_in_ideas=[])
        r["score"] = _score(r)
        db["items"].append(r)
        by_id[iid] = r
        new += 1
    return new, updated


def _prune(db: dict) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    db["items"] = [i for i in db["items"] if (i.get("fetched_at") or "") >= cutoff]
    db["scans"] = db["scans"][-KEEP_SCANS:]


def run_scan(trigger: str = "manual", kinds=None, srcs: list[dict] | None = None) -> dict:
    """One pass over every enabled source (optionally only `kinds`). A failing source is recorded
    and skipped; it never stops the others. Returns the scan record."""
    if not scan_lock.acquire(blocking=False):
        raise RuntimeError("A scan is already running.")
    try:
        all_src = sources() if srcs is None else srcs
        todo = [s for s in all_src if s.get("enabled", True) and (not kinds or s["kind"] in kinds)]
        before = ledger.spent_today()
        started = _now()
        jobs = [(s["label"], (lambda s=s: FETCHERS[s["kind"]](s))) for s in todo if s["kind"] in FETCHERS]
        li = [s for s in todo if s["kind"] == "linkedin_accounts"]
        if li:
            jobs.append((f"LinkedIn watchlist ({len(li)} accounts)", lambda: fetch_linkedin_batch(li)))
        rows, errors, per_source = [], [], {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(fn): label for label, fn in jobs}
            for fut in as_completed(futures):
                label = futures[fut]
                try:
                    got = fut.result()
                except Exception as e:  # one source down must not end the scan
                    errors.append({"source": label, "error": f"{type(e).__name__}: {str(e)[:200]}"})
                    continue
                per_source[label] = len(got)
                rows.extend(got)
        # instagram_account fetches cache user_id on the source dict; persist that.
        if srcs is None and any(s["kind"] == "instagram_account" for s in todo):
            with _lock:
                save_sources(all_src)
        with _lock:
            db = _db()
            now = _now()
            new, updated = _merge(db, rows, now)
            _prune(db)
            scan = {"id": hashlib.sha1(started.encode()).hexdigest()[:8], "started_at": started,
                    "finished_at": _now(), "trigger": trigger, "kinds": list(kinds) if kinds else None,
                    "sources": len(jobs), "seen": len(rows), "new": new, "updated": updated,
                    "per_source": per_source, "errors": errors,
                    "cost_usd": round(ledger.spent_today() - before, 4),
                    "status": "done" if not errors else ("partial" if rows else "failed")}
            db["scans"].append(scan)
            _write(DISCOVER_FILE, db)
        return scan
    finally:
        scan_lock.release()


# ------------------------------------------------------------------ search on demand
SEARCH_KINDS = {"google": "Google (last month, India)", "x": "X (last 14 days, 20+ likes)",
                "instagram_hashtag": "Instagram hashtag", "instagram_account": "Instagram account",
                "linkedin_accounts": "LinkedIn page or profile (paste the link)"}


def search_sources(q: str, kinds) -> list[dict]:
    """The one-off sources for a search the user typed. Nothing here is saved to the source list."""
    q = (q or "").strip()
    label = f"Search: {q}"
    out = []
    for k in kinds or []:
        if k == "google":
            out.append({"kind": k, "value": q, "label": label, "enabled": True, "range": "m1"})
        elif k == "x":
            out.append({"kind": k, "value": f"{q} min_faves:20", "label": label, "enabled": True, "days": 14})
        elif k == "instagram_hashtag":
            out.append({"kind": k, "value": re.sub(r"[^a-z0-9_]", "", q.lower()), "label": label, "enabled": True})
        elif k == "instagram_account":
            out.append({"kind": k, "value": q.lstrip("@").strip("/").split("/")[-1], "label": label, "enabled": True})
        elif k == "linkedin_accounts" and "linkedin.com/" in q:
            out.append({"kind": k, "value": q.split("?")[0].rstrip("/"), "label": label, "enabled": True})
    return [s for s in out if s["value"]]


def rescore() -> int:
    """Re-apply the relevance rules to everything stored (after the rules change). Returns how many flipped to off-topic."""
    with _lock:
        db = _db()
        flipped = 0
        for i in db["items"]:
            was = i.get("relevant")
            i["relevance"] = relevance(" ".join([i.get("title") or "", i.get("text") or ""]))
            i["relevant"] = i["relevance"] >= RELEVANT_AT
            i["score"] = _score(i)
            flipped += bool(was and not i["relevant"])
        _write(DISCOVER_FILE, db)
    return flipped


# ------------------------------------------------------------------ reads
def items(kind=None, q=None, include_hidden=False, limit=200, sort="score", relevant_only=False, source=None) -> list[dict]:
    """Stored items, default-sorted by relevance x engagement (`score`). sort: score|engagement|recent."""
    with _lock:
        rows = _db()["items"]
    if kind:
        kinds = {kind} if isinstance(kind, str) else set(kind)
        rows = [i for i in rows if i.get("source_kind") in kinds]
    if not include_hidden:
        rows = [i for i in rows if not i.get("hidden")]
    if relevant_only:
        rows = [i for i in rows if i.get("relevant")]
    if source:
        rows = [i for i in rows if i.get("source") == source]
    if q:
        ql = q.lower()
        rows = [i for i in rows if ql in " ".join(str(i.get(k) or "") for k in
                                                  ("title", "text", "author", "source", "url")).lower()]
    key = {"engagement": lambda i: i.get("engagement") or 0,
           "recent": lambda i: i.get("posted_at") or i.get("fetched_at") or ""}.get(
        sort, lambda i: (i.get("score") or 0, i.get("engagement") or 0))
    return sorted(rows, key=key, reverse=True)[:limit] if limit else sorted(rows, key=key, reverse=True)


def get_items(ids) -> list[dict]:
    want = list(ids or [])
    with _lock:
        by = {i["id"]: i for i in _db()["items"]}
    return [by[i] for i in want if i in by]


def hide(item_id_: str, hidden: bool = True) -> dict | None:
    with _lock:
        db = _db()
        for i in db["items"]:
            if i["id"] == item_id_:
                i["hidden"] = bool(hidden)
                _write(DISCOVER_FILE, db)
                return i
    return None


def mark_used(item_ids, idea_ids) -> None:
    """Record which ideas came from which items (used by core.ideas)."""
    with _lock:
        db = _db()
        want = set(item_ids)
        for i in db["items"]:
            if i["id"] in want:
                i["used_in_ideas"] = list(dict.fromkeys((i.get("used_in_ideas") or []) + list(idea_ids)))
        _write(DISCOVER_FILE, db)


def scans(limit=30) -> list[dict]:
    with _lock:
        return list(reversed(_db()["scans"]))[:limit]


def last_scan() -> dict | None:
    s = scans(1)
    return s[0] if s else None


def scan_due(now: datetime | None = None) -> bool:
    """True if no scan has run today (local time) and it is past settings `discover_scan_time` (default 07:30)."""
    now = now or datetime.now()
    t = str(load_settings().get("discover_scan_time") or "07:30")
    try:
        hh, mm = (int(x) for x in t.split(":"))
    except ValueError:
        hh, mm = 7, 30
    if (now.hour, now.minute) < (hh, mm):
        return False
    last = last_scan()
    if not last:
        return True
    try:
        started = datetime.fromisoformat(last["started_at"]).astimezone().replace(tzinfo=None)
    except (KeyError, ValueError):
        return True
    return started.date() < now.date()
