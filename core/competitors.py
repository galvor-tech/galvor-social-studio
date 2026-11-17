"""Competition tracking.

Two files:
  data/competitors_research.json  the researched profiles (written in the Claude terminal from public pages;
                                  refreshed by asking there, so it costs nothing on the API)
  data/competitor_log.json        what the team notices week to week: a post, a launch, a price change

Rules carried from the content spec: public information only, every fact has a source link, and we never state
or guess a competitor's spend, revenue or ROAS.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from .config import DATA

RESEARCH = DATA / "competitors_research.json"
LOG = DATA / "competitor_log.json"
KINDS = ["Post or content", "Launch or feature", "Pricing", "Hiring or funding", "Customer or case study", "Other"]


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def research() -> dict:
    d = _read(RESEARCH, {})
    comps = d.get("competitors") or []
    comps.sort(key=lambda c: (c.get("tier") != "direct", (c.get("name") or "").lower()))
    return {"researched_on": d.get("researched_on", ""), "competitors": comps, "cross": d.get("cross_cutting") or {}}


def names() -> list[str]:
    return [c.get("name", "") for c in research()["competitors"]]


def log() -> list[dict]:
    return sorted(_read(LOG, []), key=lambda e: (e.get("date", ""), e.get("at", "")), reverse=True)


def add_log(competitor: str, what: str, url: str = "", kind: str = "", works: str = "", idea: str = "",
            day: str = "", by: str = "") -> dict:
    items = _read(LOG, [])
    e = {"id": f"cl{datetime.now().strftime('%y%m%d%H%M%S')}", "date": day or date.today().isoformat(),
         "at": datetime.now().isoformat(timespec="seconds"), "competitor": competitor.strip(), "kind": kind,
         "what": what.strip(), "url": url.strip(), "works": works.strip(), "idea": idea.strip(), "by": by}
    items.append(e)
    LOG.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return e


def delete_log(eid: str) -> None:
    items = [e for e in _read(LOG, []) if e.get("id") != eid]
    LOG.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def log_for(name: str) -> list[dict]:
    return [e for e in log() if e.get("competitor", "").lower() == (name or "").lower()]


# ---------------------------------------------------------------- live scan (paid APIs)
# Apify reads each competitor's LinkedIn company page and a month of Google results; Hiker reads their
# Instagram. Claude then reads the posts and says what is working. Every call goes through the ledger, so it
# shows on Costs and stops at the daily research limit.
POSTS = DATA / "competitor_posts.json"
LI_POSTS_EACH = 5
LI_ACTOR = "harvestapi~linkedin-company-posts"
GOOGLE_ACTOR = "apify~google-search-scraper"


def _handles() -> list[dict]:
    out = []
    for c in research()["competitors"]:
        h = {"name": c.get("name", ""), "short": (c.get("name") or "").split(" (")[0].split(" /")[0], "linkedin": "", "instagram": ""}
        for ch in c.get("channels") or []:
            u = (ch.get("url") or "").strip()
            if "linkedin.com/company/" in u and not h["linkedin"]:
                h["linkedin"] = u.rstrip("/")
            if "instagram.com/" in u and not h["instagram"]:
                h["instagram"] = u.rstrip("/").split("instagram.com/")[1].strip("/")
        out.append(h)
    return out


def scan_estimate() -> dict:
    from .discover import APIFY_USD_PER_RESULT, HIKER_USD_PER_REQUEST
    hs = _handles()
    li = sum(1 for h in hs if h["linkedin"])
    ig = sum(1 for h in hs if h["instagram"])
    usd = li * LI_POSTS_EACH * APIFY_USD_PER_RESULT[LI_ACTOR] + ig * 2 * HIKER_USD_PER_REQUEST + len(hs) * APIFY_USD_PER_RESULT[GOOGLE_ACTOR]
    return {"usd": round(usd, 3), "linkedin": li, "instagram": ig, "google": len(hs)}


def scan(parts=("linkedin", "instagram", "google")) -> dict:
    """Pull the competitors' latest public posts and news. Returns the saved result; errors are listed, not raised."""
    from . import discover as D
    hs = _handles()
    posts, news, errors = [], [], []
    if "linkedin" in parts:
        group = [h for h in hs if h["linkedin"]]
        by_url = {h["linkedin"]: h for h in group}
        try:
            res = D._apify(LI_ACTOR, {"targetUrls": [h["linkedin"] for h in group], "maxPosts": LI_POSTS_EACH,
                                      "scrapeReactions": False, "scrapeComments": False,
                                      "includeQuotePosts": True, "includeReposts": False},
                           LI_POSTS_EACH * len(group), f"Competitor LinkedIn posts ({len(group)} pages)")
            for p in res:
                if not p.get("linkedinUrl"):
                    continue
                q = p.get("query") or {}
                src = ((q.get("targetUrl") if isinstance(q, dict) else "") or "").rstrip("/")
                h = by_url.get(src)
                author = (p.get("author") or {}).get("name") or ""
                if not h:
                    h = next((x for x in group if x["short"].lower() in author.lower()), None)
                posted = (p.get("postedAt") or {}).get("date") if isinstance(p.get("postedAt"), dict) else p.get("postedAt")
                eng = p.get("engagement") or {}
                posts.append({"competitor": h["name"] if h else author, "channel": "LinkedIn", "url": p["linkedinUrl"],
                              "text": (p.get("content") or "")[:1500], "posted_at": str(posted or "")[:10],
                              "likes": int(eng.get("likes") or 0), "comments": int(eng.get("comments") or 0),
                              "shares": int(eng.get("shares") or 0), "views": 0})
        except (D.SourceError, ledger_mod().OverBudget, Exception) as e:
            errors.append(f"LinkedIn: {str(e)[:200]}")
    if "instagram" in parts:
        for h in hs:
            if not h["instagram"]:
                continue
            try:
                for it in D.fetch_instagram_account({"value": h["instagram"], "label": h["name"]}):
                    posts.append({"competitor": h["name"], "channel": "Instagram", "url": it["url"], "text": it["text"][:1500],
                                  "posted_at": (it.get("posted_at") or "")[:10], "likes": it["likes"], "comments": it["comments"],
                                  "shares": it["shares"], "views": it["views"]})
            except Exception as e:
                errors.append(f"Instagram @{h['instagram']}: {str(e)[:160]}")
    if "google" in parts:
        # one Apify run for every competitor (one query per line), not one run each
        try:
            res = D._apify(GOOGLE_ACTOR, {"queries": "\n".join(f'"{h["short"]}" ads creative' for h in hs),
                                          "maxPagesPerQuery": 1, "resultsPerPage": 10, "quickDateRange": "m1",
                                          "mobileResults": False},
                           len(hs), f"Competitor news search ({len(hs)} searches)")
            for page in res:
                term = ((page.get("searchQuery") or {}).get("term") or "").lower()
                h = next((x for x in hs if f'"{x["short"].lower()}"' in term), None)
                for o in (page.get("organicResults") or [])[:6]:
                    if o.get("url"):
                        news.append({"competitor": h["name"] if h else "", "title": o.get("title") or "", "url": o["url"],
                                     "text": (o.get("description") or "")[:300], "date": o.get("date") or ""})
        except Exception as e:
            errors.append(f"Google: {str(e)[:160]}")
    posts.sort(key=lambda p: (p["likes"] + 3 * p["comments"] + 5 * p["shares"]), reverse=True)
    old = _read(POSTS, {})
    out = {"scanned_at": datetime.now().isoformat(timespec="seconds"), "posts": posts or old.get("posts", []),
           "news": news or old.get("news", []), "errors": errors, "insight": old.get("insight") if not posts else None}
    POSTS.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def ledger_mod():
    from . import ledger
    return ledger


def live() -> dict:
    return _read(POSTS, {})


def insight() -> dict:
    """Claude reads the scanned posts and says what is working. One paid call, logged on Costs."""
    from . import ai
    d = live()
    if not d.get("posts"):
        raise ai.AIError("Run a scan first: there are no competitor posts saved yet.")
    rows = [{k: p[k] for k in ("competitor", "channel", "posted_at", "likes", "comments", "shares", "views", "text")} for p in d["posts"][:60]]
    prompt = ("These are recent public posts from Galvor's competitors, with their visible engagement, and recent search "
              "results about them. Read them as a skeptical marketing head.\n"
              "Rules: use only what is here; never state or guess anyone's spend, revenue or ROAS; small numbers are a "
              "signal, not a rule; say when the data is too thin to conclude.\n"
              "The ideas for Galvor must be angles only: no numbers, percentages, findings or claims about Galvor, "
              "its data, platforms or buyers, because you have none of that here. Do not say a competitor is wrong; "
              "say what question their post leaves open.\n"
              'Return ONE JSON object: {"working": ["4 to 7 findings: which formats, topics or voices got the most '
              'response, naming the competitor and the numbers"], "not_working": ["2 to 4"], "moves": ["what each '
              'competitor appears to be pushing right now, one line each"], "for_galvor": ["4 to 6 specific post or '
              'reel ideas for Sunil, Raj, Shrutik or the Galvor page that answer these, each naming the voice"], '
              '"thin": "one sentence on how much to trust this"}\n\n'
              f"POSTS:\n{json.dumps(rows, ensure_ascii=False)}\n\nNEWS:\n{json.dumps(d.get('news', [])[:50], ensure_ascii=False)}")
    data = ai._parse_json(ai.complete(prompt, max_tokens=6000, what="Competitor read: what is working"))
    data["at"] = datetime.now().isoformat(timespec="seconds")
    d["insight"] = data
    POSTS.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


# ---------------------------------------------------------------- run the scan without holding the page
import threading  # noqa: E402

_job = {"running": False, "started": "", "result": None}
_job_lock = threading.Lock()


def start_scan() -> bool:
    """Start a scan in the background. False if one is already running."""
    with _job_lock:
        if _job["running"]:
            return False
        _job.update(running=True, started=datetime.now().isoformat(timespec="seconds"), result=None)

    def work():
        try:
            d = scan()
            res = {"ok": bool(d.get("posts") or d.get("news")), "posts": len(d.get("posts") or []),
                   "news": len(d.get("news") or []), "errors": d.get("errors") or []}
        except Exception as e:
            res = {"ok": False, "posts": 0, "news": 0, "errors": [str(e)[:200]]}
        with _job_lock:
            _job.update(running=False, result=res)

    threading.Thread(target=work, daemon=True).start()
    return True


def scan_status() -> dict:
    with _job_lock:
        return dict(_job)
