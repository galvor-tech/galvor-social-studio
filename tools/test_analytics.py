"""Tests for core/analytics.py.

1. Imports the 4 real LinkedIn exports from D:/Downloads into a TEMP analytics dir (+ temp content dir),
   checks counts / ranges / idempotency / CSV / errors.
2. Mocks the Instagram Graph API (incl. an error-100 unsupported metric) to test sync, snapshots,
   backfill, comments, replies and matching against fabricated studio posts.
3. Finally does ONE real import into data/analytics/ so the app has history (idempotent; safe to rerun).

Run:  C:/Users/mihir/AppData/Local/Programs/Python/Python315/python.exe tools/test_analytics.py
"""
import csv
import json
import shutil
import sys
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import analytics as A  # noqa: E402
from core import store  # noqa: E402

DL = Path("D:/Downloads")
F_CONTENT = DL / "galvor_linkedin_data.xls"
F_FOLLOW = DL / "galvor_followers_data.xls"
F_VISIT = DL / "galvor_visitors_data.xls"
F_SUNIL = DL / "LinkedinAnalytics_Sunil Humne_2025-11-06_2026-11-05 (1).xlsx"
REAL_FILES = [F_CONTENT, F_FOLLOW, F_VISIT, F_SUNIL]

REAL_ANALYTICS = A.ANALYTICS_DIR
REAL_CONTENT = store.CONTENT
REAL_SETTINGS = A.load_settings

ok = True


def chk(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)


def use_temp():
    tmp = Path(tempfile.mkdtemp(prefix="galvor_an_"))
    A.ANALYTICS_DIR = tmp / "analytics"
    store.CONTENT = tmp / "content"
    return tmp


def li():
    return json.loads((A.ANALYTICS_DIR / "linkedin.json").read_text(encoding="utf-8"))


def stable(d):
    """linkedin.json minus import bookkeeping (for idempotency comparison)."""
    d = json.loads(json.dumps(d))
    for a in d["accounts"].values():
        a.pop("imports", None)
        a.pop("last_imported", None)
        a.get("summary", {}).pop("imported_at", None)
        for g in a.get("demographics", {}).values():
            g.pop("imported_at", None)
        for p in a["posts"].values():
            p.pop("updated_at", None)
            for s in ("snap_24h", "snap_7d"):
                if s in p:
                    p[s].pop("at", None)
    return d


# ====================================================================== 1. parsers
def test_parsers():
    chk(A._num("73%") == 0.73, "'73%' -> 0.73")
    chk(A._num("12m 25s") == 745 and A._num("1h 59m") == 7140 and A._num("23s") == 23, "durations -> seconds")
    chk(A._num(float("nan")) is None and A._num("") is None and A._num("< 1%") is None, "NaN/''/'<1%' -> None")
    chk(A._num("1,234") == 1234 and A._num("641.0") == 641, "numbers")
    chk(A._date("08/01/2026") == "2026-08-01" and A._date("11/5/2026") == "2026-11-05", "US dates")
    chk(A._post_key("https://www.linkedin.com/feed/update/urn:li:activity:7518590069503397889") == "activity:7518590069503397889", "post key (feed url)")
    chk(A._post_key("https://www.linkedin.com/posts/sunil-humne-6a_x-y-ugcPost-7523669705916669952-2SdD") == "ugcPost:7523669705916669952", "post key (posts url)")
    chk(A._account_from_filename(F_SUNIL.name) == "sunil", "account from filename")


# ====================================================================== 2. LinkedIn imports
def test_linkedin():
    use_temp()
    res = [A.import_linkedin_file(str(f)) for f in REAL_FILES]
    for r in res:
        print("   ", r)
    c, fo, v, s = res
    chk(c["kind"] == "linkedin_company_content" and c["account"] == "company", "content export detected")
    chk(c["days"] == 92 and c["range"] == ["2026-08-01", "2026-10-31"], "content: 92 days Aug 1 – Oct 31")
    chk(c["posts"] == 21, "content: 21 posts")
    chk(fo["kind"] == "linkedin_company_followers" and fo["days"] == 92, "followers export: 92 days")
    chk(v["kind"] == "linkedin_company_visitors" and v["days"] == 92, "visitors export: 92 days")
    chk(s["kind"] == "linkedin_creator" and s["account"] == "sunil", "creator export -> sunil")
    chk(s["days"] == 365 and s["range"] == ["2025-11-06", "2026-11-05"], "sunil: 365 days")
    chk(s["posts"] >= 15, f"sunil: {s['posts']} posts (most recent + top posts)")

    d = li()
    co, su = d["accounts"]["company"], d["accounts"]["sunil"]
    day = co["daily"]["2026-08-03"]
    chk(day.get("impressions") == 41 and day.get("clicks") == 9 and abs(day["engagement_rate"] - 0.2195) < 1e-3,
        "company 2026-08-03 impressions/clicks/ER")
    chk(co["daily"]["2026-10-31"].get("page_views") == 12 and co["daily"]["2026-10-31"].get("unique_visitors") == 4,
        "visitors 2026-10-31: 12 views / 4 unique")
    chk(co["daily"]["2026-10-30"].get("new_followers") == 2, "new followers 2026-10-30 = 2")
    chk(set(co["demographics"]) == {"followers", "visitors"} and "Seniority" in co["demographics"]["followers"]["data"],
        "company demographics snapshot")
    p = co["posts"]["activity:7518590069503397889"]
    chk(p["date"] == "2026-10-21" and p["metrics"]["impressions"] == 641 and p["metrics"]["reactions"] == 5
        and p["posted_by"] == "Raj Dhakad", "company post metrics")
    chk(su["follower_totals"].get("2026-11-05") == 2429, "sunil follower total 2429 on 2026-11-05")
    rp = su["posts"]["ugcPost:7523669705916669952"]
    chk(rp["metrics"].get("members_reached") == 359 and rp["metrics"].get("reactions") == 17, "sunil recent post metrics")
    vp = su["posts"]["activity:7524020337303478274"]
    chk(vp["metrics"].get("watch_time_s") == 745 and vp["metrics"].get("avg_watch_time_s") == 23, "watch time parsed")
    chk(su["summary"].get("impressions") == 61115, "discovery summary")
    tot_imp = sum(x.get("impressions") or 0 for x in co["daily"].values())

    # idempotency: import everything again (and in a different order)
    before = stable(d)
    for f in reversed(REAL_FILES):
        A.import_linkedin_file(str(f))
    after = stable(li())
    chk(before == after, "re-import is idempotent (identical store)")
    chk(sum(x.get("impressions") or 0 for x in li()["accounts"]["company"]["daily"].values()) == tot_imp,
        f"company impressions total unchanged ({tot_imp})")

    # follower series: anchor 955 on 2026-11-04
    A.set_follower_total("linkedin", "company", "2026-11-04", 955)
    fs = A.daily_series("linkedin", "followers", days=120)
    vals = {r["date"]: r["value"] for r in fs}
    new_total = sum(x.get("new_followers") or 0 for x in li()["accounts"]["company"]["daily"].values())
    chk(vals["2026-11-04"] == 955 and vals["2026-10-31"] == 955, "company followers 955 at anchor (no data after Oct 31)")
    chk(vals["2026-08-01"] == 955 - new_total, f"company followers rebuilt backwards: Aug 1 = {955 - new_total}")
    chk(vals["2026-11-10"] is None, "no invented followers after last data/anchor")
    sf = {r["date"]: r["value"] for r in A.daily_series("linkedin", "followers", days=400, account="sunil")}
    chk(sf["2026-11-05"] == 2429 and sf["2026-11-04"] == 2429 - 12, "sunil follower series")
    imp = A.daily_series("linkedin", "impressions", days=120)
    chk(len(imp) == 120 and {"date", "value"} <= set(imp[0]), "daily_series shape")

    # CSV version of the Metrics sheet (with description row) gives the same daily numbers
    tmp = A.ANALYTICS_DIR.parent
    sheets = A._read_sheets(F_CONTENT)
    csv_path = tmp / "metrics_export.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(sheets["Metrics"])
    saved = A.ANALYTICS_DIR
    A.ANALYTICS_DIR = tmp / "analytics_csv"
    r = A.import_linkedin_file(str(csv_path), match=False)
    chk(r["days"] == 92 and li()["accounts"]["company"]["daily"]["2026-08-03"]["impressions"] == 41, "CSV import works")
    A.ANALYTICS_DIR = saved

    # bad files
    junk = tmp / "junk.csv"
    junk.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    try:
        A.import_linkedin_file(str(junk))
        chk(False, "unrecognised file raises AnalyticsError")
    except A.AnalyticsError as e:
        chk("doesn't look like" in str(e), "unrecognised file raises AnalyticsError")
    anon = tmp / "export.xlsx"
    shutil.copy(F_SUNIL, anon)
    try:
        A.import_linkedin_file(str(anon), match=False)
        chk(False, "personal export without a name needs account")
    except A.AnalyticsError:
        chk(True, "personal export without a name needs account")
    r = A.import_linkedin_file(str(anon), account="raj", match=False)
    chk(r["account"] == "raj", "account arg used when filename has no name")


# ====================================================================== 3. Instagram (mocked Graph API)
UID = "17841400000000001"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def ts(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


class FakeGraph:
    """Minimal Graph API. 'profile_visits' is unsupported for FEED media (error 100)."""

    def __init__(self):
        self.calls, self.posted = [], []
        self.media = {
            "m1": {"id": "m1", "caption": "30 new ads. One buyer. One reason. Meta counts that as close to one ad.",
                   "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "timestamp": ts(30),
                   "permalink": "https://www.instagram.com/p/AAA/", "like_count": 40, "comments_count": 3},
            "m2": {"id": "m2", "caption": "The 3-second check we run on every ad before it goes live",
                   "media_type": "VIDEO", "media_product_type": "REELS", "timestamp": ts(24 * 7 + 3),
                   "permalink": "https://www.instagram.com/reel/BBB/", "like_count": 90, "comments_count": 8},
            "m3": {"id": "m3", "caption": "Something we posted that was never in the plan",
                   "media_type": "IMAGE", "media_product_type": "FEED", "timestamp": ts(5),
                   "permalink": "https://www.instagram.com/p/CCC/", "like_count": 5, "comments_count": 0},
            "old": {"id": "old", "caption": "ancient", "media_type": "IMAGE", "media_product_type": "FEED",
                    "timestamp": ts(24 * 130), "permalink": "x", "like_count": 1, "comments_count": 0},
        }
        self.stories = [{"id": "s1", "media_type": "IMAGE", "timestamp": ts(2), "permalink": "https://instagram.com/stories/s1"}]
        self.reach_bump = 0

    def __call__(self, method, url, params=None):
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        q.update({k: str(v) for k, v in (params or {}).items()})
        path = u.path.split("/v23.0/", 1)[1]
        self.calls.append((method, path, q))
        if q.get("access_token") != "EAAtesttoken":
            raise A.GraphError("Invalid OAuth access token.", 190, None, 400)
        if method == "POST":
            self.posted.append((path, q))
            return {"id": "reply_1"}
        if path == UID:
            return {"id": UID, "username": "galvor.ai", "followers_count": 1200, "follows_count": 50, "media_count": 40}
        if path == f"{UID}/media":
            order = ["m3", "m1", "m2", "old"]
            if q.get("after") == "p2":
                return {"data": [self.media[i] for i in order[2:]], "paging": {}}
            nxt = f"https://graph.facebook.com/v23.0/{UID}/media?after=p2&access_token=EAAtesttoken"
            return {"data": [self.media[i] for i in order[:2]], "paging": {"next": nxt}}
        if path == f"{UID}/stories":
            return {"data": self.stories}
        if path.endswith("/insights") and path.startswith(UID):
            metrics = q["metric"].split(",")
            if q.get("metric_type") == "total_value":
                base = {"profile_views": 30, "website_clicks": 4, "accounts_engaged": 25, "total_interactions": 60}
                return {"data": [{"name": m, "period": "day", "total_value": {"value": base[m]}} for m in metrics]}
            out = []
            for m in metrics:
                vals = []
                for i in range(1, 30):
                    end = (NOW - timedelta(days=i - 1)).astimezone(timezone(timedelta(hours=-8)))
                    end = end.replace(hour=0, minute=0, second=0).astimezone(timezone.utc)
                    vals.append({"value": (100 + i if m == "reach" else 2), "end_time": end.strftime("%Y-%m-%dT%H:%M:%S+0000")})
                out.append({"name": m, "period": "day", "values": vals})
            return {"data": out}
        if path.endswith("/insights"):
            mid = path.split("/")[0]
            metrics = q["metric"].split(",")
            kind = (self.media.get(mid) or {}).get("media_product_type", "STORY")
            if kind == "FEED" and "profile_visits" in metrics:
                raise A.GraphError("(#100) The Media Insights API does not support the profile_visits metric", 100, None, 400)
            vals = {"reach": 500 + self.reach_bump, "views": 900 + self.reach_bump, "likes": 40, "comments": 3,
                    "saved": 12, "shares": 6, "total_interactions": 61 + self.reach_bump, "follows": 2,
                    "ig_reels_avg_watch_time": 4200, "ig_reels_video_view_total_time": 900000, "replies": 1,
                    "navigation": 30, "profile_visits": 9}
            return {"data": [{"name": m, "period": "lifetime", "values": [{"value": vals[m]}]} for m in metrics]}
        if path.endswith("/comments"):
            return {"data": [
                {"id": "c1", "text": "Great post!", "username": "fan1", "timestamp": ts(3),
                 "replies": {"data": [{"id": "r1", "username": "galvor.ai", "text": "Thanks!"}]}},
                {"id": "c2", "text": "How do I try Galvor?", "username": "fan2", "timestamp": ts(2)},
                {"id": "c3", "text": "our own comment", "username": "galvor.ai", "timestamp": ts(1)},
            ]}
        raise A.GraphError(f"unknown path {path}", 803, None, 404)


def make_post(platform, day, title, caption, fmt, voice="company", time="19:00", pillar="Quick Tip"):
    p = store.blank_post(platform, day, title=title, hook=caption.split("\n")[0], caption=caption, format=fmt,
                         voice=voice, time=time, pillar=pillar, status="approved")
    return store.save_post(p)


def test_instagram_and_matching():
    use_temp()
    # --- no token: degrade gracefully
    A.load_settings = lambda: {**REAL_SETTINGS(), "instagram_access_token": "", "instagram_user_id": ""}
    import os
    os.environ.pop("INSTAGRAM_ACCESS_TOKEN", None)
    os.environ.pop("INSTAGRAM_USER_ID", None)
    r = A.sync_instagram()
    chk(r["ok"] is False and "reason" in r, "no token -> {'ok': False, 'reason': ...}")
    chk(A.instagram_comments() == [] and A.reply_instagram_comment("c", "x")["ok"] is False, "comments degrade without token")
    k = A.kpis()
    chk(k["instagram"]["stale"] is True and k["instagram"]["connected"] is False, "kpis works with no data")

    # --- fabricated studio posts
    ist = lambda h: (NOW - timedelta(hours=h)).astimezone(A.IST)  # noqa: E731
    d1, d2, d3 = ist(30).date().isoformat(), ist(24 * 7 + 3).date().isoformat(), ist(2).date().isoformat()
    d2_plus1 = (ist(24 * 7 + 3) + timedelta(days=1)).date().isoformat()
    p1 = make_post("instagram", d1, "30 new ads isn't 30 new ideas",
                   "30 new ads. One buyer. One reason. Meta counts that as close to one ad.\n\nMore text.", "carousel")
    decoy = make_post("instagram", d1, "Festival greeting", "Wishing everyone a very happy festival from Team Galvor", "image",
                      pillar="Festival / Culture")
    p2 = make_post("instagram", d2_plus1, "Reel: the 3-second check",
                   "The 3-second check we run on every ad before it goes live. Watch till the end.", "reel", pillar="Ad Breakdown")
    p3 = make_post("instagram", d3, "Story pack", "", "story", pillar="Behind the Scenes")
    li1 = make_post("linkedin", "2026-10-22", "False bangers",
                    "An ad stops 40% people mid-scroll. The Hook Works!\nTeam doubles the budget.", "text", time="09:00",
                    pillar="Decode Teardown")
    li2 = make_post("linkedin", "2026-11-05", "Sunil video", "A short video about creative fatigue", "video",
                    voice="sunil", time="08:30", pillar="In the Room")
    for f in (F_CONTENT, F_SUNIL):
        A.import_linkedin_file(str(f), match=False)

    # --- mocked Graph
    fake = FakeGraph()
    A._http = fake
    A.load_settings = lambda: {**REAL_SETTINGS(), "instagram_access_token": "EAAtesttoken", "instagram_user_id": UID,
                               "graph_api_version": "v23.0"}
    r = A.sync_instagram()
    print("    sync:", {k: v for k, v in r.items() if k != "errors"}, r["errors"][:3])
    chk(r["ok"] and r["username"] == "galvor.ai" and r["followers"] == 1200, "sync ok + profile")
    chk(r["media"] == 4, "3 media in window + 1 story (130-day-old post skipped, pagination followed)")
    chk(not r["errors"], "no errors (error 100 handled by per-metric retry)")
    chk("media:FEED:profile_visits" in r["unsupported_new"], "unsupported metric detected")
    cache = json.loads((A.ANALYTICS_DIR / "ig_metric_cache.json").read_text(encoding="utf-8"))
    chk(cache.get("media:FEED") == ["profile_visits"], "unsupported metric cached")
    ig = json.loads((A.ANALYTICS_DIR / "instagram.json").read_text(encoding="utf-8"))
    m1, m2, m3 = ig["media"]["m1"], ig["media"]["m2"], ig["media"]["m3"]
    chk(m1["latest"]["reach"] == 500 and m1["latest"]["saves"] == 12 and "profile_visits" not in m1["latest"],
        "media latest metrics (saved -> saves)")
    chk(m1.get("snap_24h", {}).get("estimated") is False and "snap_7d" not in m1, "m1 (30h): fresh 24h snapshot, no 7d")
    chk(m2["snap_24h"]["estimated"] is True and m2["snap_7d"]["estimated"] is False, "m2 (7d+3h): 24h estimated, 7d fresh")
    chk(m2["latest"].get("avg_watch_time_ms") == 4200, "reel watch-time metrics")
    chk("snap_24h" not in m3 and ig["media"]["s1"]["media_product_type"] == "STORY", "young post: no snapshots; story stored")
    chk(len([d for d, v in ig["daily"].items() if "reach" in v]) == 29, "29 days of daily reach backfilled")
    chk(len([d for d, v in ig["daily"].items() if "accounts_engaged" in v]) == 29, "29 days of total_value metrics")
    chk(any(v.get("new_followers") == 2 for v in ig["daily"].values()), "follower_count -> new_followers")
    chk(ig["follower_totals"].get(NOW.astimezone(A.IST).date().isoformat()) == 1200, "followers snapshot for today")

    # second sync: no repeat of the failing metric, only 2 days of totals re-fetched, frozen snaps unchanged
    fake.calls.clear()
    fake.reach_bump = 100
    r2 = A.sync_instagram()
    pv_calls = [c for c in fake.calls if "profile_visits" in c[2].get("metric", "") and c[1].startswith("m")]
    tv_calls = [c for c in fake.calls if c[2].get("metric_type") == "total_value"]
    chk(r2["ok"] and not pv_calls, "cached unsupported metric not requested again for FEED")
    chk(len(tv_calls) == 2, f"incremental: only last 2 days of totals refreshed ({len(tv_calls)})")
    ig = json.loads((A.ANALYTICS_DIR / "instagram.json").read_text(encoding="utf-8"))
    chk(ig["media"]["m1"]["latest"]["reach"] == 600 and ig["media"]["m1"]["snap_24h"]["reach"] == 500,
        "latest updates, frozen 24h snapshot stays")

    # comments + reply
    cm = A.instagram_comments()
    chk([c["id"] for c in cm if c["media_id"] == "m1"] == ["c2"], "unanswered = no reply from galvor.ai, own comments excluded")
    chk(len(A.instagram_comments("m1", unanswered_only=False)) == 2, "all comments for one media")
    chk(all(c["media_id"] != "s1" for c in cm) and not any(c["media_id"] == "old" for c in cm), "comments only recent feed media")
    rr = A.reply_instagram_comment("c2", "Thanks! Link in bio.")
    chk(rr == {"ok": True, "id": "reply_1"} and fake.posted[-1][0] == "c2/replies"
        and fake.posted[-1][1]["message"] == "Thanks! Link in bio.", "reply posts to /{comment-id}/replies")

    # --- matching (sync already ran match_posts; run again to check stability)
    res = A.match_posts()
    mp = json.loads((A.ANALYTICS_DIR / "matches.json").read_text(encoding="utf-8"))["map"]
    by_ext = {k: v["post_id"] for k, v in mp.items()}
    chk(by_ext.get("instagram:m1") == p1["id"], "IG carousel matched by caption, same day")
    chk(by_ext.get("instagram:m2") == p2["id"], "IG reel matched with ±1 day")
    chk(by_ext.get("instagram:s1") == p3["id"], "story matched to the day's story pack")
    chk("instagram:m3" not in by_ext and any(o["key"] == "instagram:m3" for o in res["outside_plan"]),
        "unrelated post -> posted outside the plan")
    chk(decoy["id"] not in by_ext.values(), "decoy studio post not matched")
    chk(by_ext.get("linkedin:company:activity:7518590069503397889") == li1["id"], "LinkedIn company post matched by title")
    chk(by_ext.get("linkedin:sunil:activity:7524020337303478274") == li2["id"], "Sunil post matched by date + voice")
    vals = list(by_ext.values())
    chk(len(set(k for k in by_ext)) == len(by_ext), "no external post mapped twice")
    chk(len([v for v in vals if v != p3["id"]]) == len(set(v for v in vals if v != p3["id"])), "one external per non-story post")
    chk(res["new"] == 0, "re-running match_posts adds nothing new")

    q1 = store.get_post(p1["id"])
    mt = q1["metrics"]
    chk(q1["status"] == "published" and q1["published_url"] == "https://www.instagram.com/p/AAA/"
        and q1["external_id"] == "m1", "studio post -> published + url + external_id")
    chk(q1["published_at"].startswith(d1), "published_at = platform timestamp (IST)")
    chk(mt["reach"] == 600 and mt["saves"] == 12 and mt["source"] == "instagram_api" and mt["snap_24h"]["reach"] == 500,
        "post metrics written (+24h snapshot)")
    chk(sum(1 for a in q1["approvals"] if "Matched from Instagram" in a["action"]) == 1, "match note logged once")
    ql = store.get_post(li1["id"])
    chk(ql["metrics"]["impressions"] == 641 and ql["metrics"]["source"] == "linkedin_import" and ql["status"] == "published",
        "LinkedIn metrics written")
    chk(store.get_post(decoy["id"])["status"] == "approved", "decoy untouched")

    # --- read API
    k = A.kpis(7)
    chk(k["instagram"]["followers"]["latest"] == 1200 and k["instagram"]["stale"] is False, "kpis IG followers + fresh")
    chk(k["instagram"]["reach"]["value"] is not None and k["instagram"]["saves_shares"]["value"] is not None, "kpis IG reach / saves+shares")
    chk("sunil" in k["linkedin"]["accounts"] and k["linkedin"]["last_imported"], "kpis LinkedIn accounts + last_imported")
    pt = A.post_table(days=400)
    row = next(r for r in pt if r["key"] == "instagram:m1")
    chk(row["post"] and row["post"]["id"] == p1["id"] and row["post"]["slot"].endswith("19:00"), "post_table joins studio post")
    chk(all(r["flag"] in (None, "winner", "flop") for r in pt), "post_table flags")
    chk(any(r["flag"] == "winner" for r in pt) and any(r["flag"] == "flop" for r in pt), "winners and flops present")
    pat = A.patterns("linkedin", min_posts=3)
    chk(pat["ready"] is False and pat["needs"], "patterns not ready with few matched posts")
    wd = A.weekly_digest_data()
    chk(wd["platforms"]["instagram"]["top_post"] is not None, "weekly digest has a top IG post")
    for name, obj in (("kpis", k), ("post_table", pt), ("patterns", pat), ("digest", wd),
                      ("series", A.daily_series("instagram", "reach", 30))):
        try:
            json.dumps(obj, allow_nan=False)
            chk(True, f"{name} JSON-safe")
        except (TypeError, ValueError) as e:
            chk(False, f"{name} JSON-safe ({e})")
    ser = {x["date"]: x["value"] for x in A.daily_series("instagram", "followers", 5)}
    chk(ser[NOW.astimezone(A.IST).date().isoformat()] == 1200, "IG follower series ends at today's snapshot")

    # bad token -> ok False, no raise
    A.load_settings = lambda: {**REAL_SETTINGS(), "instagram_access_token": "EAAbad", "instagram_user_id": UID}
    r = A.sync_instagram()
    chk(r["ok"] is False and r.get("code") == 190, "invalid token -> ok False with code")


# ====================================================================== 4. real seed
def seed_real():
    A.ANALYTICS_DIR = REAL_ANALYTICS
    store.CONTENT = REAL_CONTENT
    A.load_settings = REAL_SETTINGS
    print("\n--- real import into", REAL_ANALYTICS)
    for f in REAL_FILES:
        print("   ", A.import_linkedin_file(str(f), match=False))
    A.set_follower_total("linkedin", "company", "2026-11-04", 955)
    dry = A.match_posts(dry_run=True)
    print(f"    match dry-run against real studio posts: {len(dry['matched'])} matches, "
          f"{len(dry['outside_plan'])} outside the plan")
    if dry["matched"]:
        res = A.match_posts()
        print(f"    applied matches: {len(res['matched'])}, updated posts: {res['updated_posts']}")
    else:
        A.match_posts()          # persists the (empty) mapping + outside-plan list
    fs = A.daily_series("linkedin", "followers", days=110)
    known = [x for x in fs if x["value"] is not None]
    print(f"    company followers: {known[0]['date']} {known[0]['value']} -> {known[-1]['date']} {known[-1]['value']}")


if __name__ == "__main__":
    for f in REAL_FILES:
        if not f.exists():
            print("missing sample file", f)
            sys.exit(2)
    real_http = A._http
    try:
        test_parsers()
        test_linkedin()
        test_instagram_and_matching()
    finally:
        A._http = real_http
        A.load_settings = REAL_SETTINGS
        A.ANALYTICS_DIR = REAL_ANALYTICS
        store.CONTENT = REAL_CONTENT
    if ok and "--no-seed" not in sys.argv:
        seed_real()
    print("\nALL PASS" if ok else "\nSOME TESTS FAILED")
    sys.exit(0 if ok else 1)
