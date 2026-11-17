"""Daily analytics for LinkedIn (file imports) and Instagram (Graph API).

Storage (all JSON, under data/analytics/):
    linkedin.json         per account ('company', 'sunil', ...): daily series, posts, demographics, follower totals, imports
    instagram.json        profile, daily account series, follower totals, media (+ latest / 24h / 7d snapshots)
    matches.json          external post -> studio post id mapping
    ig_metric_cache.json  Graph metrics Meta refused (error 100), per media kind / account call

LinkedIn's API needs partner approval, so LinkedIn data comes from the page / creator analytics exports
(.xls, .xlsx or .csv). Instagram uses the Graph API when a token + IG user id are in settings, and
degrades to {"ok": False, "reason": ...} otherwise.
"""
from __future__ import annotations

import csv
import difflib
import json
import math
import os
import re
import statistics
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import store
from .config import DATA, VOICES, load_settings

ANALYTICS_DIR = DATA / "analytics"           # tests monkeypatch this
UA = "GalvorSocialStudio/1.0"
IST = timezone(timedelta(hours=5, minutes=30))
_lock = threading.RLock()

IG_STALE_HOURS = 26
LI_STALE_DAYS = 8
MEDIA_WINDOW_DAYS = 120
COMMENT_WINDOW_DAYS = 14
READY_MIN_MATCHED = 12


class AnalyticsError(Exception):
    """Human-readable problem with an import or sync."""


class GraphError(Exception):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None, status: int | None = None):
        super().__init__(message)
        self.code, self.subcode, self.status = code, subcode, status


# ================================================================ storage helpers
def _path(name: str) -> Path:
    return Path(ANALYTICS_DIR) / name


def _load(name: str, default):
    f = _path(name)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(default))


def _save(name: str, data) -> None:
    f = _path(name)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(f)


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _now_iso() -> str:
    return _now().isoformat()


def _today() -> date:
    return date.today()


def _d(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _li_store() -> dict:
    return _load("linkedin.json", {"accounts": {}})


def _li_account(data: dict, account: str) -> dict:
    a = data["accounts"].setdefault(account, {})
    for k, v in (("daily", {}), ("posts", {}), ("demographics", {}), ("follower_totals", {}), ("imports", []), ("summary", {})):
        a.setdefault(k, v)
    return a


def _ig_store() -> dict:
    d = _load("instagram.json", {})
    for k, v in (("profile", {}), ("daily", {}), ("follower_totals", {}), ("media", {}), ("last_synced", None)):
        d.setdefault(k, v)
    return d


# ================================================================ value parsing
_DUR = re.compile(r"(\d+(?:\.\d+)?)\s*(h|m|s)\b")


def _num(v):
    """Tolerant number parser: '73%' -> 0.73, '12m 25s' -> 745, '1,234' -> 1234, NaN/''/'-' -> None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return int(v) if float(v).is_integer() else float(v)
    s = str(v).strip().replace(" ", " ")
    if not s or s.lower() in ("-", "--", "n/a", "na", "nan", "none", "null"):
        return None
    if s.startswith("<"):
        return None
    if s.endswith("%"):
        try:
            return float(s[:-1].replace(",", "").strip()) / 100
        except ValueError:
            return None
    if _DUR.search(s) and re.fullmatch(r"(\s*\d+(?:\.\d+)?\s*[hms]\s*)+", s):
        mult = {"h": 3600, "m": 60, "s": 1}
        return int(sum(float(n) * mult[u] for n, u in _DUR.findall(s)))
    try:
        f = float(s.replace(",", ""))
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def _date(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d %b %Y", "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _norm_header(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


# ================================================================ file reading
def _read_sheets(path: Path) -> dict[str, list[list]]:
    ext = path.suffix.lower()
    if ext == ".csv":
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise AnalyticsError(f"Couldn't read {path.name}: unknown text encoding.")
        return {path.stem: [list(r) for r in csv.reader(text.splitlines())]}
    if ext == ".xls":
        try:
            import xlrd
            wb = xlrd.open_workbook(str(path))
        except Exception as e:  # noqa: BLE001
            raise AnalyticsError(f"Couldn't open {path.name} as an Excel 97 (.xls) file: {e}") from e
        out = {}
        for sh in wb.sheets():
            rows = []
            for r in range(sh.nrows):
                row = []
                for c in range(sh.ncols):
                    cell = sh.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        row.append(xlrd.xldate_as_datetime(cell.value, wb.datemode))
                    else:
                        row.append(cell.value)
                rows.append(row)
            out[sh.name] = rows
        return out
    if ext in (".xlsx", ".xlsm"):
        import warnings
        try:
            import openpyxl
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise AnalyticsError(f"Couldn't open {path.name} as an .xlsx file: {e}") from e
        out = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
        wb.close()
        return out
    raise AnalyticsError(f"{path.name}: unsupported file type. Use the .xls / .xlsx / .csv export from LinkedIn.")


def _find_header(rows: list[list], *required: str, scan: int = 15) -> int | None:
    """Index of the first row (within `scan`) whose normalised cells contain every keyword
    (substring match; a keyword starting with '=' must equal a whole cell)."""
    def hit(k, c):
        return c == k[1:] if k.startswith("=") else k in c
    for i, r in enumerate(rows[:scan]):
        cells = [_norm_header(c) for c in r]
        if all(any(hit(k, c) for c in cells) for k in required):
            return i
    return None


def _colmap(header: list, spec: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """spec: field -> candidate header names (exact, normalised; first match wins)."""
    cells = [_norm_header(c) for c in header]
    out = {}
    for field, cands in spec.items():
        for cand in cands:
            if cand in cells:
                out[field] = cells.index(cand)
                break
    return out


def _cell(row: list, idx: int | None):
    if idx is None or idx >= len(row):
        return None
    return row[idx]


# ================================================================ LinkedIn sheet parsers
CO_DAILY = {
    "impressions": ("impressions (total)", "impressions"),
    "impressions_organic": ("impressions (organic)",),
    "unique_impressions": ("unique impressions (organic)", "unique impressions"),
    "clicks": ("clicks (total)", "clicks"),
    "reactions": ("reactions (total)", "reactions"),
    "comments": ("comments (total)", "comments"),
    "reposts": ("reposts (total)", "reposts", "shares (total)", "shares"),
    "engagement_rate": ("engagement rate (total)", "engagement rate"),
}
CO_POSTS = {
    "title": ("post title",), "url": ("post link",), "post_type": ("post type",), "posted_by": ("posted by",),
    "date": ("created date",), "impressions": ("impressions",), "views": ("views",), "clicks": ("clicks",),
    "ctr": ("click through rate (ctr)",), "reactions": ("likes", "reactions"), "comments": ("comments",),
    "reposts": ("reposts",), "follows": ("follows",), "engagement_rate": ("engagement rate",),
    "content_type": ("content type",),
}
CO_FOLLOWERS = {
    "new_followers": ("total followers",), "new_followers_organic": ("organic followers",),
    "new_followers_sponsored": ("sponsored followers",), "new_followers_auto_invited": ("auto-invited followers",),
}
CO_VISITORS = {
    "page_views": ("total page views (total)",), "unique_visitors": ("total unique visitors (total)",),
    "page_views_desktop": ("total page views (desktop)",), "page_views_mobile": ("total page views (mobile)",),
    "overview_page_views": ("overview page views (total)",),
}
CR_POSTS = {
    "url": ("post url",), "date": ("post publish date",), "post_type": ("post type",), "impressions": ("impressions",),
    "members_reached": ("members reached",), "views": ("views",), "watch_time_s": ("watch time",),
    "avg_watch_time_s": ("avg watch time",), "follows": ("followers gained",), "profile_viewers": ("profile viewers",),
    "reactions": ("reactions",), "comments": ("comments",), "reposts": ("reposts",), "saves": ("saves",),
    "sends": ("sends",), "link_visits": ("visits to links",), "engagements": ("engagements",),
}


def _parse_daily(rows, hdr, spec) -> dict[str, dict]:
    cols = _colmap(rows[hdr], spec)
    dcol = _colmap(rows[hdr], {"date": ("date",)}).get("date", 0)
    out = {}
    for r in rows[hdr + 1:]:
        d = _date(_cell(r, dcol))
        if not d:
            continue
        vals = {f: _num(_cell(r, i)) for f, i in cols.items()}
        out[d] = {k: v for k, v in vals.items() if v is not None}
    return out


def _post_key(url: str) -> str:
    """Stable id from a LinkedIn post URL: 'activity:752...' / 'ugcPost:752...' / 'share:750...'."""
    u = str(url or "")
    m = re.search(r"urn:li:(activity|ugcPost|share):(\d+)", u) or re.search(r"[-_](activity|ugcPost|share)-(\d{15,})", u)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = re.search(r"(\d{15,})", u)
    return f"id:{m.group(1)}" if m else u.strip().rstrip("/")


def _slug_text(url: str) -> str:
    """Words LinkedIn put into a /posts/<author>_<slug>-share-<id> URL (best available text for creator exports)."""
    m = re.search(r"/posts/[^_/]+_([^/?]+)", str(url or ""))
    if not m:
        return ""
    s = re.sub(r"-(activity|ugcPost|share)-\d+.*$", "", m.group(1))
    return s.replace("-", " ")


def _parse_posts(rows, hdr, spec, start_col=0, end_col=None) -> list[dict]:
    header = rows[hdr][start_col:end_col]
    cols = _colmap(header, spec)
    if "url" not in cols:
        return []
    out = []
    for r in rows[hdr + 1:]:
        r = list(r)[start_col:end_col]
        url = _cell(r, cols["url"])
        if not url or "linkedin.com" not in str(url):
            continue
        rec = {"url": str(url).strip(), "date": _date(_cell(r, cols.get("date")))}
        for f in ("title", "post_type", "posted_by", "content_type"):
            if f in cols:
                v = _cell(r, cols[f])
                rec[f] = str(v).strip() if v not in (None, "") else None
        m = {}
        for f, i in cols.items():
            if f in ("url", "date", "title", "post_type", "posted_by", "content_type"):
                continue
            v = _num(_cell(r, i))
            if v is not None:
                m[f] = v
        rec["metrics"] = m
        out.append(rec)
    return out


def _parse_demographics(rows, hdr) -> list[dict]:
    out = []
    for r in rows[hdr + 1:]:
        if not r or r[0] in (None, ""):
            continue
        out.append({"name": str(r[0]).strip(), "value": _num(_cell(r, 1))})
    return out


def _creator_demographics(rows, hdr) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in rows[hdr + 1:]:
        if len(r) < 3 or not r[0]:
            continue
        raw = str(r[2] or "").strip()
        out.setdefault(str(r[0]).strip(), []).append({"name": str(r[1] or "").strip(), "pct": _num(raw), "raw": raw})
    return out


def _account_from_filename(name: str) -> str | None:
    m = re.search(r"LinkedinAnalytics_(.+?)_\d{4}-\d{2}-\d{2}", name, re.I)
    if not m:
        return None
    person = m.group(1).strip().lower()
    first = person.split()[0] if person.split() else ""
    if first in VOICES and first != "company":
        return first
    for key, v in VOICES.items():
        if key != "company" and v.get("name", "").lower() == person:
            return key
    return None


def _analyse_workbook(path: Path, sheets: dict[str, list[list]]) -> dict:
    """Classify every sheet by its header keywords and parse it. Returns a parsed bundle."""
    b = {"daily": {}, "posts": [], "demographics": {}, "follower_total": None, "summary": {}, "kinds": set(), "creator": False}

    def merge_daily(rows: dict):
        for d, vals in rows.items():
            b["daily"].setdefault(d, {}).update(vals)

    for name, rows in sheets.items():
        rows = [list(r) for r in rows if r is not None]
        if not rows:
            continue
        lname = name.strip().lower()
        # ---- company: daily content metrics
        h = _find_header(rows, "=date", "impressions (")
        if h is not None and _find_header(rows, "post title") is None and _find_header(rows, "post url") is None:
            daily = _parse_daily(rows, h, CO_DAILY)
            for vals in daily.values():
                vals["engagements"] = sum(vals.get(k) or 0 for k in ("clicks", "reactions", "comments", "reposts"))
            merge_daily(daily)
            b["kinds"].add("company_content")
            continue
        # ---- company: posts
        h = _find_header(rows, "post title", "post link")
        if h is not None:
            b["posts"] += _parse_posts(rows, h, CO_POSTS)
            b["kinds"].add("company_content")
            continue
        # ---- company: new followers
        h = _find_header(rows, "=date", "organic followers")
        if h is not None:
            merge_daily(_parse_daily(rows, h, CO_FOLLOWERS))
            b["kinds"].add("company_followers")
            continue
        # ---- company: visitors
        h = _find_header(rows, "=date", "page views")
        if h is not None:
            merge_daily(_parse_daily(rows, h, CO_VISITORS))
            b["kinds"].add("company_visitors")
            continue
        # ---- creator: top posts (two side-by-side tables) / most recent posts
        h = _find_header(rows, "post url", "post publish date")
        if h is not None:
            cells = [_norm_header(c) for c in rows[h]]
            starts = [i for i, c in enumerate(cells) if c == "post url"]
            for j, s in enumerate(starts):
                e = starts[j + 1] if j + 1 < len(starts) else None
                for p in _parse_posts(rows, h, CR_POSTS, s, e):
                    p["from_sheet"] = lname
                    b["posts"].append(p)
            b["creator"] = True
            b["kinds"].add("creator")
            continue
        # ---- creator: followers
        h = _find_header(rows, "=date", "new followers")
        if h is not None:
            merge_daily(_parse_daily(rows, h, {"new_followers": ("new followers",)}))
            for r in rows[:h]:
                if r and isinstance(r[0], str) and r[0].lower().startswith("total followers on"):
                    d = _date(r[0][len("total followers on"):].strip())
                    v = _num(_cell(r, 1))
                    if d and v is not None:
                        b["follower_total"] = (d, v)
            b["creator"] = True
            b["kinds"].add("creator")
            continue
        # ---- creator: daily impressions / engagements
        h = _find_header(rows, "=date", "=impressions", "=engagements")
        if h is not None:
            merge_daily(_parse_daily(rows, h, {"impressions": ("impressions",), "engagements": ("engagements",)}))
            b["creator"] = True
            b["kinds"].add("creator")
            continue
        # ---- creator: demographics
        h = _find_header(rows, "top demographics", "percentage")
        if h is not None:
            b["demographics"][lname] = _creator_demographics(rows, h)
            b["creator"] = True
            continue
        # ---- creator: discovery summary
        if lname == "discovery" or (rows and _norm_header(rows[0][0] if rows[0] else "") == "overall performance"):
            for r in rows:
                if len(r) >= 2 and r[0]:
                    k = _norm_header(r[0]).replace(" ", "_")
                    b["summary"][k] = r[1] if k == "overall_performance" else _num(r[1])
            b["creator"] = True
            continue
        # ---- company: demographics (2 columns: <category>, Total followers / Total views)
        h = _find_header(rows, "total followers", scan=3)
        h2 = _find_header(rows, "total views", scan=3)
        hh = h if h is not None else h2
        if hh is not None and len([c for c in rows[hh] if c not in (None, "")]) == 2:
            group = "followers" if h is not None else "visitors"
            cat = str(rows[hh][0]).strip() or name
            b["demographics"].setdefault(group, {})[cat] = _parse_demographics(rows, hh)
            continue
    return b


def import_linkedin_file(path: str, account: str | None = None, match: bool = True) -> dict:
    """Import a LinkedIn analytics export (company content / followers / visitors, or a personal creator export).

    Idempotent: daily values are replaced per date+field and posts per post URL, so re-importing the same or an
    overlapping file never double counts; the latest import wins.
    """
    p = Path(path)
    if not p.exists():
        raise AnalyticsError(f"File not found: {path}")
    b = _analyse_workbook(p, _read_sheets(p))
    if not b["kinds"]:
        raise AnalyticsError(
            f"{p.name} doesn't look like a LinkedIn analytics export. Expected the company page Content, "
            "Followers or Visitors export, or a personal 'LinkedinAnalytics_<name>' export.")
    if b["creator"]:
        acct = _account_from_filename(p.name) or (account if account and account != "company" else None)
        if not acct:
            raise AnalyticsError(f"{p.name} is a personal LinkedIn export, but I can't tell whose. "
                                 f"Pick the person ({', '.join(k for k in VOICES if k != 'company')}).")
        kind = "linkedin_creator"
    else:
        acct = "company"
        kind = "linkedin_" + "+".join(sorted(b["kinds"]))
    at = _now_iso()
    with _lock:
        data = _li_store()
        a = _li_account(data, acct)
        for d, vals in b["daily"].items():
            a["daily"].setdefault(d, {}).update(vals)
        days = sorted(b["daily"])
        file_end = days[-1] if days else None
        # posts: merge by key, newer import wins per field
        n_posts = 0
        seen = set()
        for rec in b["posts"]:
            key = _post_key(rec["url"])
            old = a["posts"].get(key, {})
            new = {**old, "key": key, "url": old.get("url") or rec["url"], "account": acct}
            for f in ("date", "title", "post_type", "posted_by", "content_type"):
                if rec.get(f):
                    new[f] = rec[f]
            if not new.get("title"):
                st = _slug_text(rec["url"])
                if st:
                    new["slug_text"] = st
            metrics = dict(old.get("metrics") or {})
            metrics.update(rec["metrics"])
            if acct != "company" and metrics.get("impressions"):
                eng = sum(metrics.get(k) or 0 for k in ("reactions", "comments", "reposts", "saves", "sends"))
                if any(k in metrics for k in ("reactions", "comments", "reposts")):
                    metrics["engagement_rate"] = round(eng / metrics["impressions"], 4)
            new["metrics"] = metrics
            new["updated_at"] = at
            # frozen snapshots from the export's age (exports are cumulative; date-granular)
            ref = file_end or _today().isoformat()
            if new.get("date"):
                age = (_d(ref) - _d(new["date"])).days
                if age == 1 and "snap_24h" not in new:
                    new["snap_24h"] = {**_li_eng(metrics), "at": at, "estimated": False}
                if 7 <= age <= 8 and "snap_7d" not in new:
                    new["snap_7d"] = {**_li_eng(metrics), "at": at, "estimated": age != 7}
            a["posts"][key] = new
            if key not in seen:
                seen.add(key)
                n_posts += 1
        if b["demographics"]:
            for group, cats in b["demographics"].items():
                a["demographics"][group] = {"as_of": file_end or _today().isoformat(), "imported_at": at, "data": cats}
        if b["summary"]:
            a["summary"] = {**b["summary"], "imported_at": at}
        if b["follower_total"]:
            d, v = b["follower_total"]
            a["follower_totals"][d] = v
        summary = {"kind": kind, "account": acct, "days": len(days), "posts": n_posts,
                   "range": [days[0], days[-1]] if days else None, "file": p.name}
        a["imports"].append({"at": at, **summary})
        a["imports"] = a["imports"][-50:]
        a["last_imported"] = at
        _save("linkedin.json", data)
    if match:
        try:
            summary["matched"] = len(match_posts().get("matched", []))
        except Exception as e:  # noqa: BLE001 - matching must never break an import
            summary["match_error"] = str(e)
    return summary


def _li_eng(m: dict) -> dict:
    keep = ("impressions", "members_reached", "views", "reactions", "comments", "reposts", "saves", "sends", "clicks", "follows")
    out = {k: m[k] for k in keep if m.get(k) is not None}
    out["engagements"] = _li_post_engagements(m)
    return out


def _li_post_engagements(m: dict) -> int | float | None:
    keys = ("reactions", "comments", "reposts", "saves", "sends")
    if any(m.get(k) is not None for k in keys):
        return sum(m.get(k) or 0 for k in keys)
    return m.get("engagements")


# ================================================================ follower totals + series
def set_follower_total(platform: str, account: str, day: str, total: int) -> None:
    """Record a known absolute follower count (end of `day`). Used to rebuild the daily follower series."""
    day = _date(day) or day
    with _lock:
        if platform == "linkedin":
            data = _li_store()
            _li_account(data, account)["follower_totals"][day] = int(total)
            _save("linkedin.json", data)
        elif platform == "instagram":
            data = _ig_store()
            data["follower_totals"][day] = int(total)
            _save("instagram.json", data)
        else:
            raise AnalyticsError(f"Unknown platform {platform}")


def _follower_series(daily: dict, anchors: dict) -> dict[str, int]:
    """total(d) = total(anchor) + cum_new(d) - cum_new(anchor), using the nearest anchor."""
    if not anchors:
        return {}
    keys = sorted(set(daily) | set(anchors))
    start, end = _d(keys[0]), _d(keys[-1])
    cum, run, d = {}, 0, start
    while d <= end:
        s = d.isoformat()
        run += (daily.get(s) or {}).get("new_followers") or 0
        cum[s] = run
        d += timedelta(days=1)
    anc = sorted((_d(k), v) for k, v in anchors.items())
    out = {}
    for s in cum:
        ds = _d(s)
        if s in anchors:
            out[s] = int(anchors[s])
            continue
        a_d, a_v = min(anc, key=lambda x: (abs((x[0] - ds).days), -x[0].toordinal()))
        out[s] = int(a_v + cum[s] - cum[a_d.isoformat()])
    return out


# ================================================================ Instagram Graph API
def _ig_creds() -> tuple[str, str]:
    s = load_settings()
    token = s.get("instagram_access_token") or os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    uid = s.get("instagram_user_id") or os.environ.get("INSTAGRAM_USER_ID", "")
    return str(token or "").strip(), str(uid or "").strip()


def _graph_base(token: str = "") -> str:
    s = load_settings()
    host = s.get("instagram_api_host") or ("graph.instagram.com" if token.startswith("IG") else "graph.facebook.com")
    return f"https://{host}/{s.get('graph_api_version') or 'v23.0'}"


def _http(method: str, url: str, params: dict | None = None) -> dict:
    """Single HTTP entry point (tests monkeypatch this). Returns parsed JSON or raises GraphError."""
    data = None
    if params:
        enc = urllib.parse.urlencode(params)
        if method == "GET":
            url = url + ("&" if "?" in url else "?") + enc
        else:
            data = enc.encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        try:
            err = json.loads(body).get("error", {})
        except json.JSONDecodeError:
            err = {"message": body[:300]}
        raise GraphError(err.get("message", f"HTTP {e.code}"), err.get("code"), err.get("error_subcode"), e.code) from e
    except urllib.error.URLError as e:
        raise GraphError(f"Network error: {e.reason}") from e


class _Graph:
    def __init__(self, token: str):
        self.token, self.base, self.calls = token, _graph_base(token), 0

    def get(self, path: str, **params) -> dict:
        self.calls += 1
        if path.startswith("http"):
            return _http("GET", path)            # paging 'next' URLs already carry the token
        return _http("GET", f"{self.base}/{path.lstrip('/')}", {**params, "access_token": self.token})

    def post(self, path: str, **params) -> dict:
        self.calls += 1
        return _http("POST", f"{self.base}/{path.lstrip('/')}", {**params, "access_token": self.token})


MEDIA_METRICS = {
    "FEED": ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions", "profile_visits", "follows"],
    "REELS": ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions",
              "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"],
    "STORY": ["reach", "views", "replies", "navigation", "shares", "total_interactions", "follows", "profile_visits"],
}
ACCOUNT_DAY_METRICS = ["reach", "follower_count"]
ACCOUNT_TOTAL_METRICS = ["profile_views", "website_clicks", "accounts_engaged", "total_interactions"]
METRIC_RENAME = {"saved": "saves", "ig_reels_avg_watch_time": "avg_watch_time_ms",
                 "ig_reels_video_view_total_time": "watch_time_ms", "follower_count": "new_followers"}
MEDIA_FIELDS = "id,caption,media_type,media_product_type,timestamp,permalink,thumbnail_url,media_url,like_count,comments_count"


def _metric_value(item: dict):
    if isinstance(item.get("total_value"), dict):
        return item["total_value"].get("value")
    vals = item.get("values") or []
    return vals[-1].get("value") if vals else None


def _insights(g: _Graph, path: str, metrics: list[str], cache: dict, cache_key: str, new_unsupported: list,
              **params) -> dict:
    """Fetch insights; on error 100 retry one by one and remember metrics Meta refuses (per cache_key).
    Returns {"values": {metric: insights item}, "error": str|None}."""
    bad = set(cache.get(cache_key, []))
    wanted = [m for m in metrics if m not in bad]
    if not wanted:
        return {"values": {}, "error": None}
    try:
        res = g.get(path, metric=",".join(wanted), **params)
        return {"values": {it["name"]: it for it in res.get("data", [])}, "error": None}
    except GraphError as e:
        if e.code != 100 or len(wanted) == 1:
            return {"values": {}, "error": str(e), "code": e.code, "subcode": e.subcode}
    got, failed, last = {}, [], None
    for m in wanted:
        try:
            res = g.get(path, metric=m, **params)
            for it in res.get("data", []):
                got[it["name"]] = it
        except GraphError as e:
            last = e
            if e.code == 100:
                failed.append(m)
    if got and failed:                     # media-specific failures (all metrics fail) are not cached
        cache[cache_key] = sorted(bad | set(failed))
        new_unsupported += [f"{cache_key}:{m}" for m in failed]
    return {"values": got, "error": None if got else str(last)}


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def _end_time_day(end_time: str) -> str:
    """Graph daily values carry end_time = midnight Pacific of the next day."""
    return (_parse_ts(end_time) - timedelta(hours=8, seconds=1)).date().isoformat()


def _ig_engagements(m: dict):
    if m.get("total_interactions") is not None:
        return m["total_interactions"]
    keys = ("likes", "comments", "saves", "shares", "replies")
    return sum(m.get(k) or 0 for k in keys) if any(m.get(k) is not None for k in keys) else None


def sync_instagram(match: bool = True) -> dict:
    token, uid = _ig_creds()
    if not token or not uid:
        return {"ok": False, "reason": "Instagram isn't connected yet: add the access token and IG user id in Settings → Publishing."}
    g = _Graph(token)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    errors, new_unsupported = [], []
    cache = _load("ig_metric_cache.json", {})
    with _lock:
        data = _ig_store()
        # ---- profile
        try:
            prof = g.get(uid, fields="username,followers_count,follows_count,media_count")
        except GraphError as e:
            return {"ok": False, "reason": f"Instagram API refused the request: {e}", "code": e.code}
        data["profile"] = {**prof, "at": now.isoformat()}
        today_ist = now.astimezone(IST).date().isoformat()
        if prof.get("followers_count") is not None:
            data["follower_totals"][today_ist] = prof["followers_count"]
        # ---- media list (feed + reels), last 120 days, then current stories
        cutoff = now - timedelta(days=MEDIA_WINDOW_DAYS)
        media_list = []
        try:
            page = g.get(f"{uid}/media", fields=MEDIA_FIELDS, limit=50)
            while True:
                stop = False
                for m in page.get("data", []):
                    if m.get("timestamp") and _parse_ts(m["timestamp"]) < cutoff:
                        stop = True
                        continue
                    media_list.append(m)
                nxt = (page.get("paging") or {}).get("next")
                if stop or not nxt:
                    break
                page = g.get(nxt)
        except GraphError as e:
            errors.append(f"media list: {e}")
        try:
            st = g.get(f"{uid}/stories", fields=MEDIA_FIELDS)
            for m in st.get("data", []):
                m.setdefault("media_product_type", "STORY")
                media_list.append(m)
        except GraphError as e:
            errors.append(f"stories: {e}")
        # ---- per-media insights + snapshots
        snaps = {"24h": 0, "7d": 0}
        ok_ins = 0
        for m in media_list:
            mid = m["id"]
            rec = data["media"].get(mid, {})
            rec.update({k: v for k, v in m.items() if k != "id"})
            rec["id"] = mid
            kind = (m.get("media_product_type") or "FEED").upper()
            kind = kind if kind in MEDIA_METRICS else "FEED"
            ts = _parse_ts(m["timestamp"]) if m.get("timestamp") else now
            age_h = (now - ts).total_seconds() / 3600
            # older posts change slowly: refresh at most daily after 30 days
            last = rec.get("latest_at")
            if age_h > 30 * 24 and last and (now - datetime.fromisoformat(last)).total_seconds() < 20 * 3600:
                data["media"][mid] = rec
                continue
            res = _insights(g, f"{mid}/insights", MEDIA_METRICS[kind], cache, f"media:{kind}", new_unsupported)
            latest = {"likes": m.get("like_count"), "comments": m.get("comments_count")}
            for name, it in res["values"].items():
                latest[METRIC_RENAME.get(name, name)] = _metric_value(it)
            latest = {k: v for k, v in latest.items() if v is not None}
            latest["engagements"] = _ig_engagements(latest)
            if res["values"]:
                ok_ins += 1
            elif res.get("error"):
                errors.append(f"insights {mid}: {res['error']}")
            rec["latest"] = latest
            rec["latest_at"] = now.isoformat()
            rec["age_hours"] = round(age_h, 1)
            if "snap_24h" not in rec and age_h >= 24:
                rec["snap_24h"] = {**latest, "at": now.isoformat(), "age_hours": round(age_h, 1), "estimated": age_h >= 48}
                snaps["24h"] += 1
            if "snap_7d" not in rec and age_h >= 7 * 24:
                rec["snap_7d"] = {**latest, "at": now.isoformat(), "age_hours": round(age_h, 1), "estimated": age_h >= 8 * 24}
                snaps["7d"] += 1
            data["media"][mid] = rec
        # ---- account daily insights (IG keeps ~30 days; fills gaps after time offline)
        since = int((now - timedelta(days=29)).timestamp())
        until = int(now.timestamp())
        res = _insights(g, f"{uid}/insights", ACCOUNT_DAY_METRICS, cache, "account:day", new_unsupported,
                        period="day", since=since, until=until)
        if res.get("error"):
            errors.append(f"account daily: {res['error']}")
        days_filled = set()
        for name, it in res["values"].items():
            for v in it.get("values") or []:
                if v.get("end_time") is None or v.get("value") is None:
                    continue
                day = _end_time_day(v["end_time"])
                data["daily"].setdefault(day, {})[METRIC_RENAME.get(name, name)] = v["value"]
                days_filled.add(day)
        # total_value metrics: one call per day; backfill missing days, always refresh the last 2
        today = now.astimezone(IST).date()
        for back in range(1, 30):
            day = (today - timedelta(days=back)).isoformat()
            have = data["daily"].get(day, {})
            if back > 2 and all(METRIC_RENAME.get(k, k) in have for k in ACCOUNT_TOTAL_METRICS
                                if k not in cache.get("account:total_value", [])):
                continue
            d0 = datetime.combine(_d(day), datetime.min.time(), IST)
            r = _insights(g, f"{uid}/insights", ACCOUNT_TOTAL_METRICS, cache, "account:total_value", new_unsupported,
                          metric_type="total_value", period="day",
                          since=int(d0.timestamp()), until=int((d0 + timedelta(days=1)).timestamp()))
            if r.get("error"):
                errors.append(f"account totals {day}: {r['error']}")
                if r.get("code") in (190, 4, 17, 32, 613):      # auth / rate limit: stop hammering
                    break
                continue
            for name, it in r["values"].items():
                val = _metric_value(it)
                if val is not None:
                    data["daily"].setdefault(day, {})[name] = val
                    days_filled.add(day)
        data["last_synced"] = _now_iso()
        result = {"ok": True, "username": prof.get("username"), "followers": prof.get("followers_count"),
                  "media": len(media_list), "insights_ok": ok_ins, "daily_days": len(days_filled),
                  "snapshots": snaps, "unsupported_new": new_unsupported, "errors": errors[:20], "calls": g.calls}
        data["last_sync_result"] = {**result, "at": data["last_synced"]}
        _save("instagram.json", data)
        _save("ig_metric_cache.json", cache)
    if match:
        try:
            result["matched"] = len(match_posts().get("matched", []))
        except Exception as e:  # noqa: BLE001
            result["match_error"] = str(e)
    return result


def instagram_comments(media_id: str | None = None, unanswered_only: bool = True) -> list:
    token, uid = _ig_creds()
    if not token or not uid:
        return []
    g = _Graph(token)
    data = _ig_store()
    me = (data.get("profile") or {}).get("username")
    if not me:
        try:
            me = g.get(uid, fields="username").get("username")
        except GraphError:
            me = None
    now = datetime.now(timezone.utc)
    if media_id:
        targets = [data["media"].get(media_id) or {"id": media_id}]
    else:
        targets = [m for m in data["media"].values()
                   if m.get("timestamp") and now - _parse_ts(m["timestamp"]) <= timedelta(days=COMMENT_WINDOW_DAYS)
                   and (m.get("media_product_type") or "").upper() != "STORY"]
    out = []
    for m in targets:
        try:
            page = g.get(f"{m['id']}/comments", fields="id,text,username,timestamp,replies{id,username,text,timestamp}")
        except GraphError:
            continue
        while True:
            for c in page.get("data", []):
                if me and c.get("username") == me:
                    continue
                replies = (c.get("replies") or {}).get("data", [])
                answered = bool(me) and any(r.get("username") == me for r in replies)
                if unanswered_only and answered:
                    continue
                out.append({"id": c["id"], "media_id": m["id"], "permalink": m.get("permalink"),
                            "caption": (m.get("caption") or "")[:80], "username": c.get("username"),
                            "text": c.get("text"), "timestamp": c.get("timestamp"), "replies": replies,
                            "answered": answered})
            nxt = (page.get("paging") or {}).get("next")
            if not nxt:
                break
            try:
                page = g.get(nxt)
            except GraphError:
                break
    out.sort(key=lambda c: c.get("timestamp") or "", reverse=True)
    return out


def reply_instagram_comment(comment_id: str, text: str) -> dict:
    token, uid = _ig_creds()
    if not token or not uid:
        return {"ok": False, "reason": "Instagram isn't connected yet."}
    if not (text or "").strip():
        return {"ok": False, "reason": "Reply text is empty."}
    try:
        res = _Graph(token).post(f"{comment_id}/replies", message=text.strip())
        return {"ok": True, "id": res.get("id")}
    except GraphError as e:
        return {"ok": False, "reason": str(e), "code": e.code}


# ================================================================ external posts (uniform view)
IG_FORMAT = {"REELS": "reel", "STORY": "story", "CAROUSEL_ALBUM": "carousel", "IMAGE": "image", "VIDEO": "reel"}


def _externals() -> list[dict]:
    """Every external post as {key, platform, account, date, time, text, url, format, ts, metrics, snaps}."""
    out = []
    ig = _ig_store()
    synced = ig.get("last_synced")
    for mid, m in ig["media"].items():
        if not m.get("timestamp"):
            continue
        ts = _parse_ts(m["timestamp"]).astimezone(IST)
        kind = (m.get("media_product_type") or "").upper()
        fmt = "story" if kind == "STORY" else "reel" if kind == "REELS" else IG_FORMAT.get((m.get("media_type") or "").upper(), "image")
        out.append({"key": f"instagram:{mid}", "id": mid, "platform": "instagram", "account": "company",
                    "date": ts.date().isoformat(), "time": ts.strftime("%H:%M"), "ts": ts.replace(tzinfo=None).isoformat(),
                    "text": m.get("caption") or "", "url": m.get("permalink") or "", "format": fmt,
                    "metrics": m.get("latest") or {}, "snap_24h": m.get("snap_24h"), "snap_7d": m.get("snap_7d"),
                    "synced_at": m.get("latest_at") or synced})
    li = _li_store()
    for acct, a in li["accounts"].items():
        for key, p in a.get("posts", {}).items():
            if not p.get("date"):
                continue
            m = dict(p.get("metrics") or {})
            m["engagements"] = _li_post_engagements(m)
            out.append({"key": f"linkedin:{acct}:{key}", "id": key, "platform": "linkedin", "account": acct,
                        "date": p["date"], "time": None, "ts": p["date"] + "T00:00:00",
                        "text": p.get("title") or p.get("slug_text") or "", "has_text": bool(p.get("title")),
                        "url": p.get("url", ""), "format": _li_format(p), "metrics": m,
                        "snap_24h": p.get("snap_24h"), "snap_7d": p.get("snap_7d"),
                        "synced_at": p.get("updated_at") or a.get("last_imported")})
    return out


def _li_format(p: dict) -> str | None:
    t = f"{p.get('post_type') or ''} {p.get('content_type') or ''}".lower()
    for k, v in (("video", "video"), ("poll", "poll"), ("document", "carousel"), ("carousel", "carousel"),
                 ("image", "image"), ("article", "article"), ("text", "text")):
        if k in t:
            return v
    return None


# ================================================================ matching
def _norm_text(s: str, n: int = 80) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()[:n]


def _sim(ext_text: str, post: dict) -> float:
    a = _norm_text(ext_text)
    if not a:
        return 0.0
    best = 0.0
    for f in ("caption", "hook", "title"):
        b = _norm_text(post.get(f) or "")
        if b:
            best = max(best, difflib.SequenceMatcher(None, a, b[:len(a) + 10] if f == "caption" else b).ratio())
    return best


def _metrics_for_post(exts: list[dict]) -> dict:
    """Studio post['metrics'] from one (or several story frames) external post(s)."""
    def agg(dicts):
        dicts = [d for d in dicts if d]
        if not dicts:
            return None
        if len(dicts) == 1:
            return {k: v for k, v in dicts[0].items()}
        out = {}
        for d in dicts:
            for k, v in d.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[k] = max(out.get(k, 0), v) if k == "reach" else out.get(k, 0) + v
        out["estimated"] = any(d.get("estimated") for d in dicts)
        return out

    e0 = exts[0]
    m = agg([e["metrics"] for e in exts]) or {}
    if e0["platform"] == "instagram":
        out = {"reach": m.get("reach"), "views": m.get("views"), "impressions": m.get("views"),
               "likes": m.get("likes"), "reactions": m.get("likes"), "comments": m.get("comments"),
               "shares": m.get("shares"), "saves": m.get("saves"), "follows": m.get("follows"),
               "profile_visits": m.get("profile_visits"), "replies": m.get("replies"),
               "engagements": _ig_engagements(m)}
        base = out["reach"] or out["views"]
        source = "instagram_api"
    else:
        out = {"impressions": m.get("impressions"), "reach": m.get("members_reached"), "views": m.get("views"),
               "reactions": m.get("reactions"), "likes": m.get("reactions"), "comments": m.get("comments"),
               "reposts": m.get("reposts"), "saves": m.get("saves"), "clicks": m.get("clicks"),
               "follows": m.get("follows"), "engagements": _li_post_engagements(m)}
        base = out["impressions"]
        source = "linkedin_import"
    if m.get("engagement_rate") is not None:
        out["engagement_rate"] = m["engagement_rate"]
    elif base and out.get("engagements") is not None:
        out["engagement_rate"] = round(out["engagements"] / base, 4)
    out = {k: v for k, v in out.items() if v is not None}
    for s in ("snap_24h", "snap_7d"):
        v = agg([e.get(s) for e in exts])
        if v:
            out[s] = v
    out["source"] = source
    out["synced_at"] = max((e.get("synced_at") or "") for e in exts) or _now_iso()
    return out


def match_posts(dry_run: bool = False) -> dict:
    """Link external posts to studio posts (same platform/voice, date ±1, best caption similarity)."""
    exts = _externals()
    by_key = {e["key"]: e for e in exts}
    with _lock:
        mp = _load("matches.json", {"map": {}})
        studio = {p["id"]: p for p in store.all_posts() if p.get("platform") in ("instagram", "linkedin")}
        # drop mappings whose studio post or external vanished
        mp["map"] = {k: v for k, v in mp["map"].items() if v.get("post_id") in studio and k in by_key}
        taken_posts = {}
        for k, v in mp["map"].items():
            taken_posts.setdefault(v["post_id"], []).append(k)
        cands = []
        for e in exts:
            if e["key"] in mp["map"]:
                continue
            ed = _d(e["date"])
            pool = []
            for p in studio.values():
                if p["platform"] != e["platform"] or p.get("status") == "skipped":
                    continue
                if e["platform"] == "linkedin" and (p.get("voice") or "company") != e["account"]:
                    continue
                try:
                    dd = abs((_d(p["date"]) - ed).days)
                except (KeyError, ValueError):
                    continue
                if dd > 1:
                    continue
                pool.append((p, dd))
            is_story = e["format"] == "story"
            has_text = bool(_norm_text(e["text"]))
            for p, dd in pool:
                fmt_ok = (p.get("format") == e["format"]) if e["format"] else None
                if is_story:
                    if p.get("format") == "story" and dd == 0:
                        cands.append((0.6, e["key"], p["id"]))
                    continue
                if p.get("format") == "story":
                    continue
                if has_text:
                    sim = _sim(e["text"], p)
                    if sim >= 0.55:
                        cands.append((sim + (0.1 if dd == 0 else 0) + (0.05 if fmt_ok else 0), e["key"], p["id"]))
            if not has_text and not is_story:
                exact = [p for p, dd in pool if dd == 0 and p.get("format") != "story"]
                if len(exact) == 1:
                    cands.append((0.5, e["key"], exact[0]["id"]))
        cands.sort(reverse=True)
        new_keys = []
        for score, key, pid in cands:
            if key in mp["map"]:
                continue
            is_story = by_key[key]["format"] == "story"
            if pid in taken_posts and not is_story:
                continue
            if pid in taken_posts and is_story and any(by_key[k]["format"] != "story" for k in taken_posts[pid]):
                continue
            mp["map"][key] = {"post_id": pid, "score": round(score, 3), "at": _now_iso()}
            taken_posts.setdefault(pid, []).append(key)
            new_keys.append(key)
        # write metrics into the studio posts
        updated, matched = 0, []
        for pid, keys in taken_posts.items():
            p = studio[pid]
            ex = sorted((by_key[k] for k in keys), key=lambda e: e["ts"])
            metrics = _metrics_for_post(ex)
            changed = False
            old = {k: v for k, v in (p.get("metrics") or {}).items() if k != "synced_at"}
            if old != {k: v for k, v in metrics.items() if k != "synced_at"}:
                p["metrics"] = metrics
                changed = True
            if not p.get("published_url") and ex[0]["url"]:
                p["published_url"] = ex[0]["url"]
                changed = True
            ext_id = ex[0]["id"] if len(ex) == 1 else ",".join(e["id"] for e in ex)
            if p.get("external_id") != ext_id:
                p["external_id"] = ext_id
                changed = True
            first_match = any(k in new_keys for k in keys)
            if p.get("status") != "published":
                p["status"] = "published"
                ts = ex[0]["ts"]
                if ex[0]["platform"] == "linkedin":
                    ts = f"{ex[0]['date']}T{(p.get('time') or '09:00')}:00"
                p["published_at"] = ts
                changed = True
            for k in keys:
                matched.append({"external_key": k, "post_id": pid, "score": mp["map"][k]["score"], "new": k in new_keys})
            if changed and not dry_run:
                note = f"Matched from {'Instagram' if ex[0]['platform'] == 'instagram' else 'LinkedIn'} analytics" if first_match else None
                store.save_post(p, note=note)
                updated += 1
        outside = [_ext_summary(e) for e in exts if e["key"] not in mp["map"]]
        mp["outside_plan"] = [o["key"] for o in outside]
        mp["matched_at"] = _now_iso()
        if not dry_run:
            _save("matches.json", mp)
    return {"matched": matched, "new": len(new_keys), "updated_posts": updated,
            "outside_plan": sorted(outside, key=lambda o: o["date"], reverse=True), "dry_run": dry_run}


def link_post(external_key: str, post_id: str | None) -> dict:
    """Manually fix a match (post_id=None unlinks). Re-runs matching so metrics land on the studio post."""
    with _lock:
        mp = _load("matches.json", {"map": {}})
        if post_id is None:
            mp["map"].pop(external_key, None)
        else:
            mp["map"][external_key] = {"post_id": post_id, "score": 1.0, "at": _now_iso(), "manual": True}
        _save("matches.json", mp)
    return match_posts()


def _ext_summary(e: dict) -> dict:
    return {"key": e["key"], "platform": e["platform"], "account": e["account"], "date": e["date"], "time": e["time"],
            "format": e["format"], "url": e["url"], "text": (e["text"] or "")[:120],
            "engagements": (e["metrics"] or {}).get("engagements"),
            "reach": (e["metrics"] or {}).get("reach") or (e["metrics"] or {}).get("impressions")}


# ================================================================ read API
def _median(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def _sum(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return sum(xs) if xs else None


def _cmp(value, prev) -> dict:
    out = {"value": value, "prev": prev, "change": None, "pct": None}
    if isinstance(value, (int, float)) and isinstance(prev, (int, float)):
        out["change"] = round(value - prev, 4)
        out["pct"] = round((value - prev) / prev, 4) if prev else None
    return out


def _window(as_of: date, days: int, offset: int = 0) -> list[str]:
    end = as_of - timedelta(days=offset * days)
    return [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _platform_daily(platform: str, account: str = "company") -> tuple[dict, dict]:
    if platform == "instagram":
        d = _ig_store()
        return d["daily"], d["follower_totals"]
    a = _li_store()["accounts"].get(account) or {}
    return a.get("daily", {}), a.get("follower_totals", {})


def _period_kpis(platform: str, account: str, days: int, exts: list[dict]) -> dict:
    daily, anchors = _platform_daily(platform, account)
    reach_key = "reach" if platform == "instagram" else "impressions"
    eng_key = "total_interactions" if platform == "instagram" else "engagements"
    with_data = sorted(d for d, v in daily.items() if v.get(reach_key) is not None)
    my_ext = [e for e in exts if e["platform"] == platform and e["account"] == account]
    if with_data:
        as_of = _d(with_data[-1])
    elif my_ext:
        as_of = max(_d(e["date"]) for e in my_ext)
    else:
        as_of = _today()
    if platform == "instagram":
        as_of = max(as_of, _today() - timedelta(days=1))
    series = _follower_series(daily, anchors)
    cur, prev = _window(as_of, days), _window(as_of, days, 1)

    def total(win, key):
        return _sum((daily.get(d) or {}).get(key) for d in win)

    def fchange(win):
        before = (_d(win[0]) - timedelta(days=1)).isoformat()
        if win[-1] in series and before in series:
            return series[win[-1]] - series[before]
        nf = total(win, "new_followers")
        return nf

    def posts(win):
        s = set(win)
        return [e for e in my_ext if e["date"] in s and e["format"] != "story"]

    def post_eng(win):
        return _sum(e["metrics"].get("engagements") for e in posts(win))

    r_cur, r_prev = total(cur, reach_key), total(prev, reach_key)
    e_cur, e_prev = total(cur, eng_key), total(prev, eng_key)
    if e_cur is None and platform == "instagram":
        e_cur, e_prev = post_eng(cur), post_eng(prev)
    rate = lambda e, r: round(e / r, 4) if isinstance(e, (int, float)) and r else None  # noqa: E731
    latest_f = series[max(series)] if series else None
    out = {
        "account": account, "as_of": as_of.isoformat(), "period": [cur[0], cur[-1]], "prev_period": [prev[0], prev[-1]],
        "followers": {"latest": latest_f, "latest_date": max(series) if series else None,
                      **_cmp(fchange(cur), fchange(prev))},
        "reach" if platform == "instagram" else "impressions": _cmp(r_cur, r_prev),
        "engagements": _cmp(e_cur, e_prev),
        "engagement_rate": _cmp(rate(e_cur, r_cur), rate(e_prev, r_prev)),
        "posts_published": _cmp(len(posts(cur)), len(posts(prev))),
    }
    if platform == "instagram":
        ss = lambda win: _sum((e["metrics"].get("saves") or 0) + (e["metrics"].get("shares") or 0) for e in posts(win))  # noqa: E731
        out["saves_shares"] = _cmp(ss(cur), ss(prev))
        out["profile_views"] = _cmp(total(cur, "profile_views"), total(prev, "profile_views"))
    else:
        out["page_views"] = _cmp(total(cur, "page_views"), total(prev, "page_views"))
    return out


def kpis(days: int = 7) -> dict:
    exts = _externals()
    li = _li_store()
    ig = _ig_store()
    now = _now()
    li_last = max((a.get("last_imported") or "" for a in li["accounts"].values()), default="") or None
    ig_last = ig.get("last_synced")
    li_accounts = {acct: _period_kpis("linkedin", acct, days, exts) for acct in li["accounts"]}
    linkedin = dict(li_accounts.get("company") or _period_kpis("linkedin", "company", days, exts))
    linkedin["accounts"] = li_accounts
    linkedin["last_imported"] = li_last
    linkedin["last_imported_by_account"] = {k: a.get("last_imported") for k, a in li["accounts"].items()}
    linkedin["stale"] = not li_last or (now - datetime.fromisoformat(li_last)) > timedelta(days=LI_STALE_DAYS)
    instagram = _period_kpis("instagram", "company", days, exts)
    instagram["last_synced"] = ig_last
    instagram["connected"] = all(_ig_creds())
    instagram["stale"] = not ig_last or (now - datetime.fromisoformat(ig_last)) > timedelta(hours=IG_STALE_HOURS)
    return {"days": days, "linkedin": linkedin, "instagram": instagram,
            "sources": {"linkedin_import": {"last": li_last, "stale": linkedin["stale"]},
                        "instagram_api": {"last": ig_last, "stale": instagram["stale"]}}}


METRIC_ALIASES = {"impressions": ("impressions", "reach"), "reach": ("reach", "impressions"),
                  "engagements": ("engagements", "total_interactions")}


def daily_series(platform: str, metric: str, days: int = 60, account: str = "company") -> list:
    daily, anchors = _platform_daily(platform, account)
    end = _today()
    win = _window(end, days)
    if metric == "followers":
        s = _follower_series(daily, anchors)
        return [{"date": d, "value": s.get(d)} for d in win]
    keys = METRIC_ALIASES.get(metric, (metric,))
    key = metric
    for k in keys:
        if any(k in v for v in daily.values()):
            key = k
            break
    return [{"date": d, "value": (daily.get(d) or {}).get(key)} for d in win]


def post_table(platform: str | None = None, days: int = 60) -> list:
    exts = _externals()
    mp = _load("matches.json", {"map": {}})["map"]
    studio = {p["id"]: p for p in store.all_posts()} if mp else {}
    cutoff = (_today() - timedelta(days=days)).isoformat()
    med_cut = (_today() - timedelta(days=60)).isoformat()
    medians = {}
    for e in exts:
        if e["date"] >= med_cut and e["format"] != "story":
            medians.setdefault((e["platform"], e["account"]), []).append(_score_eng(e))
    medians = {k: _median(v) for k, v in medians.items()}
    rows = []
    for e in exts:
        if (platform and e["platform"] != platform) or e["date"] < cutoff:
            continue
        eng = _score_eng(e)
        med = medians.get((e["platform"], e["account"]))
        score = round(eng / med, 2) if isinstance(eng, (int, float)) and med else None
        flag = None if score is None or e["format"] == "story" else "winner" if score >= 1.5 else "flop" if score <= 0.5 else None
        m = e["metrics"] or {}
        row = {**_ext_summary(e), "metrics": m, "snap_24h": e.get("snap_24h"), "snap_7d": e.get("snap_7d"),
               "score": score, "flag": flag, "score_basis": "7d" if e.get("snap_7d") else "latest",
               "synced_at": e.get("synced_at"), "post": None}
        hit = mp.get(e["key"])
        if hit and hit["post_id"] in studio:
            p = studio[hit["post_id"]]
            row["post"] = {"id": p["id"], "title": p.get("title") or p.get("hook"), "format": p.get("format"),
                           "pillar": p.get("pillar"), "voice": p.get("voice"), "date": p.get("date"),
                           "time": p.get("time"), "slot": _slot(p.get("date"), p.get("time"))}
        rows.append(row)
    rows.sort(key=lambda r: (r["date"], r["time"] or ""), reverse=True)
    return rows


def _score_eng(e: dict):
    snap = e.get("snap_7d") or {}
    v = snap.get("engagements")
    return v if v is not None else (e["metrics"] or {}).get("engagements")


def _slot(day: str | None, t: str | None) -> str | None:
    if not day:
        return None
    wd = _d(day).strftime("%a")
    return f"{wd} {t}" if t else wd


def patterns(platform: str, min_posts: int = 3) -> dict:
    rows = [r for r in post_table(platform, days=3650) if r["format"] != "story"]
    matched = [r for r in rows if r["post"]]
    groups: dict[str, dict[str, list]] = {"format": {}, "pillar": {}, "slot": {}, "voice": {}}
    for r in rows:
        p = r["post"] or {}
        eng = _score_eng({"metrics": r["metrics"], "snap_7d": r["snap_7d"]})
        reach = r["metrics"].get("reach") or r["metrics"].get("impressions")
        keys = {"format": p.get("format") or r["format"],
                "pillar": p.get("pillar"),
                "slot": p.get("slot") or (_slot(r["date"], r["time"]) if r["time"] else None),
                "voice": p.get("voice") or r["account"]}
        for g, k in keys.items():
            if k:
                groups[g].setdefault(k, []).append((eng, reach))
    out = {}
    for g, d in groups.items():
        out[g] = sorted(
            [{"key": k, "n": len(v), "median_engagement": _median([x[0] for x in v]),
              "median_reach": _median([x[1] for x in v])} for k, v in d.items() if len(v) >= min_posts],
            key=lambda x: -(x["median_engagement"] or 0))
    return {"platform": platform, "posts": len(rows), "matched_posts": len(matched),
            "ready": len(matched) >= READY_MIN_MATCHED, "min_posts": min_posts,
            "needs": None if len(matched) >= READY_MIN_MATCHED else
            f"needs ~4 weeks of data ({len(matched)}/{READY_MIN_MATCHED} matched posts)", "groups": out}


def weekly_digest_data() -> dict:
    k = kpis(7)
    rows = post_table(days=14)
    week = (_today() - timedelta(days=7)).isoformat()
    out = {"generated_at": _now_iso(), "period": [week, _today().isoformat()], "platforms": {}}
    for pl in ("linkedin", "instagram"):
        cur = [r for r in rows if r["platform"] == pl and r["date"] > week and r["format"] != "story"
               and isinstance(r["engagements"], (int, float))]
        cur.sort(key=lambda r: r["score"] if r["score"] is not None else (r["engagements"] or 0), reverse=True)
        kk = k[pl]
        reach_key = "reach" if pl == "instagram" else "impressions"
        out["platforms"][pl] = {
            "followers": kk["followers"], reach_key: kk[reach_key], "engagements": kk["engagements"],
            "engagement_rate": kk["engagement_rate"], "posts_published": kk["posts_published"],
            "as_of": kk["as_of"], "stale": kk["stale"],
            "top_post": cur[0] if cur else None, "worst_post": cur[-1] if len(cur) > 1 else None,
            "outside_plan": [r for r in rows if r["platform"] == pl and r["date"] > week and not r["post"]],
        }
        if pl == "linkedin":
            out["platforms"][pl]["accounts"] = {a: {"followers": v["followers"], "impressions": v["impressions"],
                                                    "engagements": v["engagements"], "as_of": v["as_of"]}
                                                for a, v in kk["accounts"].items()}
    return out


def demographics(account: str = "company") -> dict:
    return (_li_store()["accounts"].get(account) or {}).get("demographics", {})
