"""Tests for core.discover / core.ideas / core.guard / core.ledger.

    python tools/test_discover.py           # unit tests only (mocked HTTP + mocked AI, temp data dir)
    python tools/test_discover.py --live    # + one real smoke scan (1 hashtag + 1 Google query, < $0.05)
                                            #   and one real generate(n_ideas=3); results stay in data/
"""
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import discover, guard, ideas, ledger  # noqa: E402
from core.config import FORMATS, PILLARS, VOICES  # noqa: E402

NOW_TS = time.time()


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text = data, status, json.dumps(data)[:300]

    def json(self):
        return self._d


def ig_media(code, likes, caption, days_ago=1, plays=None, clips=False, user="creator1"):
    return {"code": code, "like_count": likes, "comment_count": 10, "play_count": plays,
            "taken_at": NOW_TS - days_ago * 86400, "product_type": "clips" if clips else "feed",
            "caption": {"text": caption}, "user": {"username": user}}


HASHTAG_RESP = {"response": {"sections": [
    {"layout_content": {"medias": [
        {"media": ig_media("AAA", 500, "Meta ads creative testing: 3 hooks that cut our CAC for a D2C brand", clips=True, plays=90000)},
        {"media": ig_media("BBB", 90000, "Cute puppy dance 🐶 #marketing #viral #reels", plays=5_000_000)},
        {"media": ig_media("OLD", 9000, "Old meta ads post", days_ago=60)},
    ]}},
    {"layout_content": {"medias": [{"media": ig_media("AAA", 500, "dupe in same response")}]}},
]}}

USER_RESP = {"pk": "12345", "username": "peerbrand"}
USER_MEDIAS_RESP = {"response": {"items": [
    ig_media("UUU", 120, "UGC creator brief template for influencer marketing", user="peerbrand"),
    ig_media("VVV", 40, "Team lunch!", user="peerbrand"),
]}, "next_page_id": "x"}

GOOGLE_RESP = [{"organicResults": [
    {"url": "https://example.com/meta-andromeda", "title": "Meta Andromeda changes creative", "description":
     "Meta says Andromeda now scores ads faster; advertisers see 22% more conversions on Advantage+.",
     "position": 1, "displayedUrl": "example.com", "date": "2 days ago"},
    {"url": "https://example.com/recipe", "title": "Best biryani recipe", "description": "Cook rice.", "position": 2},
    {"title": "no url"},
]}]

X_RESP = [
    {"id": 1, "url": "https://x.com/a/status/1", "author": {"userName": "adguy"}, "fullText":
     "UGC creators: paid 1,200 per hook. ROAS on creator ads beats studio ads for D2C.", "likeCount": 300,
     "retweetCount": 20, "replyCount": 15, "viewCount": 40000, "createdAt": "Mon Nov 09 10:00:00 +0000 2026"},
    {"id": 2, "url": None},
]

LI_RESP = [
    {"id": "li1", "linkedinUrl": "https://www.linkedin.com/posts/abc", "author": {"name": "Jane"},
     "content": "Creative strategy for D2C: we killed 40% of ads after the creator brief changed.",
     "engagement": {"likes": 80, "comments": 12, "shares": 3},
     "postedAt": {"date": datetime.now(timezone.utc).isoformat()}, "query": {"targetUrl": "https://www.linkedin.com/in/jane"}},
    {"id": "li2", "linkedinUrl": "https://www.linkedin.com/posts/old", "content": "old",
     "postedAt": {"date": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}},
]


def fake_get(url, params=None, **kw):
    if url.endswith("/v2/hashtag/medias/top"):
        return FakeResp(HASHTAG_RESP)
    if url.endswith("/v1/user/by/username"):
        return FakeResp(USER_RESP)
    if url.endswith("/g2/user/medias"):
        assert params["user_id"] == "12345"
        return FakeResp(USER_MEDIAS_RESP)
    return FakeResp({"detail": "nope"}, 404)


def fake_post(url, json=None, **kw):
    if "google-search-scraper" in url:
        return FakeResp(GOOGLE_RESP)
    if "tweet-scraper" in url:
        return FakeResp(X_RESP)
    if "linkedin-profile-posts" in url:
        return FakeResp(LI_RESP)
    return FakeResp({"error": "x"}, 400)


SRC = {
    "instagram_hashtag": {"id": "s1", "kind": "instagram_hashtag", "value": "metaads", "label": "#metaads", "enabled": True},
    "instagram_account": {"id": "s2", "kind": "instagram_account", "value": "peerbrand", "label": "@peerbrand", "enabled": True},
    "google": {"id": "s3", "kind": "google", "value": "Meta Andromeda", "label": "Meta Andromeda", "enabled": True},
    "x": {"id": "s4", "kind": "x", "value": "ugc creators", "label": "UGC creators", "enabled": True},
    "linkedin_accounts": {"id": "s5", "kind": "linkedin_accounts", "value": "https://www.linkedin.com/in/jane", "label": "Jane", "enabled": True},
}


class TempData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(discover, "SOURCES_FILE", self.tmp / "sources.json"),
            mock.patch.object(discover, "DISCOVER_FILE", self.tmp / "discover.json"),
            mock.patch.object(ideas, "IDEAS_FILE", self.tmp / "ideas.json"),
            mock.patch.object(ledger, "SPEND_FILE", self.tmp / "spend.json"),
            mock.patch.object(ledger, "cap", lambda: 2.0),
            mock.patch.object(discover, "DATA", self.tmp),
            mock.patch.object(ideas, "DATA", self.tmp),
            mock.patch.object(ledger, "DATA", self.tmp),
            mock.patch.object(discover.requests, "get", side_effect=fake_get),
            mock.patch.object(discover.requests, "post", side_effect=fake_post),
            mock.patch.dict("os.environ", {"HIKER_KEY": "test", "APIFY_API_TOKEN": "test"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()


class DiscoverTests(TempData):
    def scan(self, *kinds):
        return discover.run_scan("test", srcs=[dict(SRC[k]) for k in kinds])

    def test_instagram_hashtag(self):
        s = self.scan("instagram_hashtag")
        self.assertEqual(s["status"], "done")
        rows = discover.items(include_hidden=True)
        urls = {r["url"] for r in rows}
        self.assertEqual(urls, {"https://www.instagram.com/reel/AAA/", "https://www.instagram.com/p/BBB/"})  # OLD dropped, dupe merged
        a = next(r for r in rows if "AAA" in r["url"])
        self.assertEqual((a["likes"], a["comments"], a["views"], a["author"]), (500, 10, 90000, "creator1"))
        self.assertEqual(a["engagement"], 500 + 20 + 900)
        for k in ("id", "source_kind", "source", "url", "author", "text", "posted_at", "likes", "comments", "shares",
                  "views", "engagement", "fetched_at", "hidden", "used_in_ideas", "relevant"):
            self.assertIn(k, a)
        self.assertAlmostEqual(ledger.spent_today(), 0.001)

    def test_relevance_beats_viral_offtopic(self):
        self.scan("instagram_hashtag")
        rows = discover.items()
        self.assertIn("AAA", rows[0]["url"])  # relevant one first, despite 180x less engagement
        pup = next(r for r in rows if "BBB" in r["url"])
        self.assertFalse(pup["relevant"])
        self.assertTrue(rows[0]["relevant"])
        self.assertEqual([r["url"] for r in discover.items(relevant_only=True)], [rows[0]["url"]])

    def test_instagram_account_caches_user_id(self):
        src = dict(SRC["instagram_account"])
        got = discover.fetch_instagram_account(src)
        self.assertEqual(src["user_id"], "12345")
        self.assertEqual({g["url"] for g in got}, {"https://www.instagram.com/p/UUU/", "https://www.instagram.com/p/VVV/"})
        self.assertEqual(got[0]["author"], "peerbrand")
        self.assertAlmostEqual(ledger.spent_today(), 0.002)
        discover.fetch_instagram_account(src)  # second time: one request only
        self.assertAlmostEqual(ledger.spent_today(), 0.003)
        self.assertEqual(discover.estimate([src]), 0.001)

    def test_google(self):
        self.scan("google")
        rows = discover.items(kind="google", include_hidden=True)
        self.assertEqual(len(rows), 2)
        top = rows[0]
        self.assertEqual(top["url"], "https://example.com/meta-andromeda")
        self.assertTrue(top["relevant"])
        self.assertEqual(top["engagement"], 100)  # rank 1 nominal
        self.assertFalse(next(r for r in rows if "recipe" in r["url"])["relevant"])
        self.assertAlmostEqual(ledger.spent_today(), 0.0035)

    def test_x(self):
        self.scan("x")
        (t,) = discover.items(kind="x")
        self.assertEqual((t["likes"], t["comments"], t["shares"], t["views"], t["author"]), (300, 15, 20, 40000, "adguy"))
        self.assertTrue(t["relevant"])
        self.assertAlmostEqual(ledger.spent_today(), 0.0008)  # billed per returned result (2 rows, one unusable)

    def test_linkedin(self):
        self.scan("linkedin_accounts")
        (p,) = discover.items(kind="linkedin_accounts")  # 30-day-old post skipped
        self.assertEqual((p["author"], p["likes"], p["shares"], p["source"]), ("Jane", 80, 3, "Jane"))

    def test_dedupe_and_keep_flags(self):
        self.scan("instagram_hashtag")
        a = next(r for r in discover.items() if "AAA" in r["url"])
        discover.hide(a["id"])
        discover.mark_used([a["id"]], ["idea-1"])
        s2 = self.scan("instagram_hashtag")
        self.assertEqual((s2["new"], s2["updated"]), (0, 2))
        self.assertEqual(len(discover.items(include_hidden=True)), 2)
        a2 = next(r for r in discover.items(include_hidden=True) if "AAA" in r["url"])
        self.assertTrue(a2["hidden"])
        self.assertEqual(a2["used_in_ideas"], ["idea-1"])
        self.assertNotIn(a["id"], [r["id"] for r in discover.items()])
        discover.hide(a["id"], False)
        self.assertIn(a["id"], [r["id"] for r in discover.items()])
        self.assertEqual(discover.norm_url("https://WWW.instagram.com/p/X/"), discover.norm_url("https://www.instagram.com/p/X"))

    def test_prune_30_days(self):
        self.scan("google")
        db = json.loads(discover.DISCOVER_FILE.read_text(encoding="utf-8"))
        db["items"][0]["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        discover.DISCOVER_FILE.write_text(json.dumps(db), encoding="utf-8")
        self.scan("x")
        self.assertEqual(len(discover.items(kind="google", include_hidden=True)), 1)

    def test_budget_refusal(self):
        ledger.record("test", "earlier calls", 1.9995)
        s = self.scan("instagram_hashtag", "google")
        self.assertEqual(s["status"], "failed")
        self.assertEqual(len(s["errors"]), 2)
        self.assertTrue(all("OverBudget" in e["error"] for e in s["errors"]))
        self.assertAlmostEqual(ledger.spent_today(), 1.9995)
        with self.assertRaises(ledger.OverBudget):
            ledger.check(0.01, "x")

    def test_failing_source_does_not_stop_others(self):
        with mock.patch.object(discover.requests, "post", return_value=FakeResp({"error": "bad"}, 500)):
            s = self.scan("instagram_hashtag", "google")
        self.assertEqual(s["status"], "partial")
        self.assertEqual(s["new"], 2)

    def test_sources_seed_save_estimate(self):
        seeded = discover.sources()
        self.assertEqual(len(seeded), len(discover.DEFAULT_SOURCES))
        self.assertAlmostEqual(discover.estimate(), 7 * 0.001 + 4 * 0.0035 + 3 * 15 * 0.0004)
        saved = discover.save_sources(seeded + [{"kind": "instagram_account", "value": "https://instagram.com/peer/"},
                                               {"kind": "instagram_hashtag", "value": "#metaads"}])
        self.assertEqual(saved[-1]["value"], "peer")
        self.assertEqual(len(saved), len(seeded) + 1)
        with self.assertRaises(ValueError):
            discover.save_sources([{"kind": "tiktok", "value": "x"}])

    def test_scan_due(self):
        with mock.patch.object(discover, "load_settings", return_value={"discover_scan_time": "07:30"}):
            self.assertFalse(discover.scan_due(datetime.now().replace(hour=7, minute=0)))
            self.assertTrue(discover.scan_due(datetime.now().replace(hour=8, minute=0)))
            self.scan("google")
            self.assertFalse(discover.scan_due(datetime.now().replace(hour=23, minute=0)))
            self.assertTrue(discover.scan_due(datetime.now().replace(hour=8) + timedelta(days=1)))
        self.assertEqual(discover.last_scan()["trigger"], "test")


class NumberCheckTests(unittest.TestCase):
    item = {"id": "i1", "title": "", "text": "Creators charge ₹1,200 per hook; 36% of brands use UGC. 2.5x ROAS in 2026.",
            "likes": 4500, "comments": 0, "shares": 0, "views": 0}

    def test_present(self):
        for v in ("₹1,200", "1200", "1,200", "36%", "36", "2.5x", "2.5", "4500", "4,500", "2026"):
            self.assertTrue(ideas._value_in_source(v, self.item), v)

    def test_absent(self):
        for v in ("47%", "12", "3", "6", "120", "1.2", "", None, "a lot", "2.6x"):
            self.assertFalse(ideas._value_in_source(v, self.item), v)


class GuardTests(unittest.TestCase):
    def rules(self, t):
        return {f["rule"] for f in guard.check(t)}

    def test_rules(self):
        self.assertEqual(self.rules("This ad won the quarter"), {"results-claim"})
        self.assertEqual(self.rules("Our best-performing hook"), {"results-claim"})
        self.assertEqual(self.rules("It won't work"), set())
        self.assertEqual(self.rules("What Traya learned"), {"client-name"})
        self.assertEqual(self.rules("How DaMENSCH briefs"), {"client-name"})  # CMS list
        self.assertEqual(self.rules("Physics Wallah ads"), {"client-name"})  # studio list
        self.assertEqual(self.rules("We guarantee 10x ROAS"), {"overclaim"})
        self.assertEqual(self.rules("Plain useful advice about creator briefs."), set())

    def test_shape(self):
        (f,) = guard.check("winning creative")
        self.assertEqual(f["severity"], "warn")
        self.assertTrue(f["message"] and f["why"] and f["rule"] == "results-claim")


class IdeaTests(TempData):
    def setUp(self):
        super().setUp()
        discover.run_scan("test", srcs=[dict(SRC["instagram_hashtag"]), dict(SRC["x"]), dict(SRC["google"])])
        self.items = {i["source_kind"]: i for i in discover.items(relevant_only=True)}

    def fake_ai(self, payload):
        return mock.patch("core.ai.complete", return_value=json.dumps(payload))

    def test_generate_validates(self):
        x, ig = self.items["x"], self.items["instagram_hashtag"]
        payload = {"ideas": [
            {"title": "Creator hooks", "hook": "Most UGC hooks are priced wrong.", "angle": "a", "outline": ["one", "Follow Galvor"],
             "platform": "linkedin", "format": "short video", "pillar": "creators and testing", "voice": "raj", "job": "Educate",
             "why_now": "x", "source_item_ids": [x["id"], "bogus"],
             "numbers": [{"value": "1,200", "source_item_id": x["id"], "quote": "paid 1,200 per hook"},
                         {"value": "47%", "source_item_id": x["id"], "quote": "made up"},
                         {"value": "500", "source_item_id": "bogus"}]},
            {"hook": "IG idea", "platform": "instagram", "format": "poll", "pillar": "Nonsense Pillar", "voice": "sunil",
             "source_item_ids": [ig["id"]], "numbers": [{"value": "90000", "source_item_id": ig["id"]}]},
            {"hook": "Both", "platform": "both", "format": "reel", "pillar": "Measurement", "voice": "kc"},
            {"hook": "", "platform": "linkedin"},  # rejected: no hook
            {"hook": "Our winning ad for Traya", "platform": "tiktok", "format": "?", "voice": "?"},
        ]}
        with self.fake_ai(payload):
            got = ideas.generate(n_ideas=5)
        self.assertEqual(len(got), 4)
        a, b, c, d = got
        self.assertEqual((a["format"], a["pillar"], a["voice"], a["platform"]), ("video", "Creators & Testing", "raj", "linkedin"))
        self.assertEqual(a["source_item_ids"], [x["id"]])
        self.assertEqual([n["value"] for n in a["numbers"]], ["1,200"])
        self.assertEqual(a["numbers"][0]["quote"], "paid 1,200 per hook")
        self.assertEqual((b["format"], b["voice"]), ("carousel", "company"))
        self.assertIn(b["pillar"], PILLARS["instagram"])
        self.assertEqual(b["numbers"][0]["quote"], "(from the post's counts: 90000)")
        self.assertEqual((c["format"], c["voice"], c["pillar"]), ("carousel", "company", "Measurement"))
        self.assertIn(c["pillar_instagram"], PILLARS["instagram"])
        self.assertEqual(d["platform"], "linkedin")
        self.assertEqual({f["rule"] for f in d["flags"]}, {"results-claim", "client-name"})
        for i in got:
            self.assertIn(i["format"], FORMATS["linkedin" if i["platform"] == "both" else i["platform"]])
            self.assertIn(i["voice"], VOICES)
            self.assertEqual(i["status"], "new")
        self.assertIn(a["id"], discover.get_items([x["id"]])[0]["used_in_ideas"])
        self.assertEqual(len(ideas.list_ideas()), 4)
        self.assertGreater(ledger.spent_today(), 0.0045)  # AI call priced in

    def test_prompt_has_rules(self):
        p = ideas.build_prompt(list(self.items.values()), 3)
        for s in ("63 sales meetings", "never name a Galvor client", "No invented numbers", "Follow Galvor", "@galvor.ai"):
            self.assertIn(s, p)
        self.assertNotIn("@galvorai", p)

    def test_bad_json_and_budget(self):
        from core import ai
        with mock.patch("core.ai.complete", return_value="not json at all"):
            with self.assertRaises(ai.AIError):
                ideas.generate(n_ideas=2)
        ledger.record("test", "x", 1.999)
        with mock.patch("core.ai.complete") as m:
            with self.assertRaises(ledger.OverBudget):
                ideas.generate(n_ideas=2)
            m.assert_not_called()

    def test_update_and_brief(self):
        x = self.items["x"]
        with self.fake_ai({"ideas": [{"hook": "H", "angle": "Say A", "outline": ["b1", "b2"], "platform": "instagram",
                                       "format": "reel", "pillar": "Quick Tip", "source_item_ids": [x["id"]],
                                       "numbers": [{"value": "1,200", "source_item_id": x["id"]}]}]}):
            (i,) = ideas.generate(item_ids=[x["id"]], n_ideas=1)
        i2 = ideas.update_idea(i["id"], status="shortlisted", hook="This ad won")
        self.assertEqual(i2["status"], "shortlisted")
        self.assertEqual(i2["flags"][0]["rule"], "results-claim")
        with self.assertRaises(ValueError):
            ideas.update_idea(i["id"], status="bogus")
        with self.assertRaises(ValueError):
            ideas.update_idea(i["id"], id="x")
        self.assertEqual(ideas.update_idea(i["id"], post_id="p1")["status"], "used")
        b = ideas.idea_to_post_brief(ideas.get_idea(i["id"]))
        self.assertEqual(set(b) >= {"platform", "format", "pillar", "voice", "hook", "title", "brief", "job"}, True)
        self.assertEqual((b["platform"], b["format"], b["voice"]), ("instagram", "reel", "company"))
        self.assertIn("1,200", b["brief"])
        self.assertIn("Follow @galvor.ai", b["brief"])
        self.assertIn("b2", b["brief"])

    def test_from_topics(self):
        with mock.patch("core.store.all_posts", return_value=[{"topic_ref": "S1"}]):
            got = ideas.from_topics(4)
            self.assertEqual(len(got), 4)
            self.assertNotIn("S1", [g["topic_ref"] for g in got])
            self.assertEqual(len({g["voice"] for g in got}), 3)  # spread across sunil/raj/shrutik
            for g in got:
                self.assertIn(g["pillar"], PILLARS["linkedin"])
                self.assertIn(g["format"], FORMATS["linkedin"])
            again = ideas.from_topics(4)
            self.assertFalse({g["topic_ref"] for g in got} & {g["topic_ref"] for g in again})
        self.assertEqual(ideas.idea_to_post_brief(got[0])["topic_ref"], got[0]["topic_ref"])


def live():
    """Real calls: 1 hashtag + 1 Google query, then generate(n_ideas=3)."""
    from core import ai
    print("\n=== LIVE smoke run ===")
    before = ledger.spent_today()
    srcs = [{"id": "live-ig", "kind": "instagram_hashtag", "value": "performancemarketing", "label": "#performancemarketing", "enabled": True},
            {"id": "live-g", "kind": "google", "value": "Meta ads update", "label": "Meta ads update", "enabled": True}]
    est = discover.estimate(srcs)
    assert est < 0.05, est
    scan = discover.run_scan("smoke-test", srcs=srcs)
    cost = round(ledger.spent_today() - before, 4)
    print(f"scan: status={scan['status']} seen={scan['seen']} new={scan['new']} updated={scan['updated']} "
          f"per_source={scan['per_source']} cost=${cost} (estimate ${est})")
    for e in scan["errors"]:
        print("  ERROR", e)
    assert cost < 0.05, cost
    rows = discover.items()
    print(f"items stored: {len(discover.items(include_hidden=True, limit=0))}, relevant: {len(discover.items(relevant_only=True, limit=0))}")
    for r in rows[:6]:
        print(f"  [{r['source_kind']}] rel={r['relevance']} eng={r['engagement']} {r['url']} :: {r['text'][:70]!r}")
    st = ai.status()
    print(f"AI provider: {st['provider']} model={st['model'] or '(default)'}")
    if not st["ready"]:
        print("No AI provider; skipping generate().")
        return
    b2 = ledger.spent_today()
    try:
        got = ideas.generate(n_ideas=3)
    except Exception as e:
        print(f"generate() FAILED: {type(e).__name__}: {e}")
        return
    print(f"generate(): {len(got)} ideas, est. AI cost ${round(ledger.spent_today() - b2, 4)}")
    for i in got:
        print(f"  - [{i['platform']}/{i['format']}/{i['pillar']}/{i['voice']}] {i['hook']}")
        print(f"    numbers kept={[n['value'] for n in i['numbers']]} dropped={i.get('numbers_dropped')} flags={[f['rule'] for f in i['flags']]}")
    print("spend summary:", ledger.summary())


if __name__ == "__main__":
    want_live = "--live" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--live"]
    res = unittest.main(exit=False, verbosity=1).result
    if not res.wasSuccessful():
        sys.exit(1)
    if want_live:
        live()
