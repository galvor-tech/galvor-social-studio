"""Seed the gaps checklist and analytics baseline from the LinkedIn tracker workbook.
Safe to re-run: keeps existing statuses/owners and never overwrites weekly rows."""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = Path("D:/galvor_linkedin/Galvor_LinkedIn_Tracker.xlsx")

G = []


def add(group, title, why, how="", priority="Medium"):
    G.append({"id": f"g{len(G) + 1:02d}", "group": group, "title": title, "why": why, "how": how,
              "priority": priority, "status": "todo", "owner": ""})


# ---------------------------------------------------------------- what the plan doesn't cover yet
add("Instagram foundation", "Set up the @galvor.ai profile for B2B",
    "Instagram has no plan yet; the profile is the landing page for every post.",
    "Name field: 'Galvor | Creative Intelligence'. Bio: 'Know why your ads win. Decoding D2C ads, every two weeks. "
    "Free category decode ↓'. Category: Software. Switch to a Business account (needed for Insights and the API).", "High")
add("Instagram foundation", "Link-in-bio page with UTM links",
    "Instagram captions can't link; every 'link in bio' needs a destination you can measure.",
    "One page (e.g. galvor.ai/links): Decoded archive, free category decode, brief template, book a call. "
    "UTM: ?utm_source=instagram&utm_medium=social&utm_campaign=<post id>.", "High")
add("Instagram foundation", "Story highlights",
    "Highlights are the permanent menu for new visitors.",
    "Decoded · Teardowns · Proof · Team · Ask us. Render covers in the studio theme (story size, festival or cover layout).")
add("Instagram foundation", "Reels production kit and a batching day",
    "Reels need faces and B-roll; without a routine they're the first thing to slip.",
    "Phone + clip-on mic + ring light. Film 4 reels every alternate Thursday afternoon from the scripts in the studio. "
    "Use Instagram's licensed audio only.", "High")
add("Instagram foundation", "Cross-post reels to YouTube Shorts (@galvor.ai)",
    "The YouTube channel exists but isn't in any plan; Shorts reuse costs nothing.",
    "Upload each reel to Shorts the same day with the same caption.", "Low")
add("Distribution", "Employee and founder advocacy rota",
    "Personal profiles drive most reach (plan, Review 3); the first hour decides distribution.",
    "Each author pings the team when a post goes live; 3 real comments inside 60 minutes. KC: 3–5 comments + 1 reshare a week.", "High")
add("Distribution", "LinkedIn Thought Leader Ads on the best founder post each month",
    "Boosting a proven organic post is the cheapest paid reach to exact job titles.",
    "Small monthly test aimed at D2C founders, CMOs and growth heads in India; boost only posts beating the median by 2×.")
add("Distribution", "Collab posts with clients and creators",
    "Instagram Collab posts and co-authored LinkedIn posts reach both audiences.",
    "Only with written permission; start with creator campaigns Shrutik runs.")
add("Distribution", "Subscribe CTA on every Decoded promo",
    "Newsletter subscribers are owned reach — notified of every issue.",
    "First comment + last slide: 'Subscribe to Decoded'.")
add("Conversion", "Lead magnets that match the soft asks",
    "Posts promise a one-page brief template and a free category decode; both must exist before those posts go out.",
    "Brief template as a PDF in the studio theme + a 'Get a free category decode' form on galvor.ai with a "
    "'Where did you hear about us?' field.", "High")
add("Conversion", "UTM convention for every link",
    "Without UTMs, LinkedIn and Instagram traffic is invisible in analytics.",
    "utm_source=linkedin|instagram · utm_medium=social · utm_campaign=<studio post id> · utm_content=<voice>.", "High")
add("Conversion", "'How did you first hear of Galvor?' field in the sales pipeline",
    "Day 90 is judged on pipeline, not likes (plan, Review 4).",
    "Required field in the Galvor CRM; Sunil and KC ask it on every first call.", "High")
add("Conversion", "Saved replies and a DM playbook",
    "Fast, consistent replies to 'decode', 'brief' and pricing DMs.",
    "Three saved replies per platform; reply within 2 business hours.")
add("Proof", "Written permission from 2 clients for named case studies",
    "January's theme is proof; without permission the stories stay anonymous and thinner.",
    "Ask in November; offer a co-branded carousel and a newsletter feature.", "High")
add("Proof", "Three client video testimonials (30–45 s)",
    "Faces plus results are the highest-trust content on both platforms.",
    "Shrutik records after a successful cycle. Three questions: before, what changed, what you'd tell a peer.")
add("Governance", "Second admin on every account",
    "86% of page posts came from one admin (metrics file) — a single point of failure.",
    "2+ super admins on the LinkedIn page; 2 people with Instagram access via Meta Business Suite.", "High")
add("Governance", "Negative comment and crisis policy",
    "A plan for criticism, spam and competitor jabs avoids rushed replies.",
    "Reply once with facts, move details to DM, never delete criticism (hide only spam/abuse), escalate to Sunil.")
add("Governance", "Claims and permissions check before approval",
    "No client names, no competitor spend claims, every number sourced — the studio's checks enforce most of it.",
    "Approver reviews the Quality check panel; Sunil approves anything that names a client or makes a claim.")
add("Measurement", "Monday 15-minute metrics ritual",
    "The weekly tracker only works if someone fills it in.",
    "Every Monday after the huddle: add the week on Analytics and enter 7-day results on last week's posts.", "High")
add("Measurement", "Monthly competitor social review",
    "Know what other ad-intelligence and martech brands post and what lands.",
    "Last Friday of the month: 30 minutes, 5 accounts, note 3 formats or angles to test.", "Low")
add("Events & PR", "Pick 2027 events (Goafest, D2C summits, SaaSBoomi)",
    "In-person events give the best content and the warmest leads; dates are still TBC in the key-dates calendar.",
    "Decide by January; plan before/during/after posts for each.")
add("Events & PR", "A founder podcast or LinkedIn Live once a quarter",
    "Long-form conversation builds authority faster than posts alone.",
    "Sunil plus a client or operator; cut into 5 clips for both platforms.", "Low")

# ---------------------------------------------------------------- LinkedIn page setup rows from the tracker
wb = None
if TRACKER.exists():
    import openpyxl
    wb = openpyxl.load_workbook(TRACKER, data_only=True)
    for r in wb["Page Setup Changes"].iter_rows(min_row=4, values_only=True):
        if not r or not isinstance(r[0], (int, float)) or not r[1]:
            continue
        add("LinkedIn page setup (from your tracker)", f"{r[1]}: {r[3]}", f"Now: {r[2]}. {r[4] or ''}".strip(), "",
            r[5] or "Medium")

path = ROOT / "data" / "gaps.json"
old = {g["title"]: g for g in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
for g in G:
    if g["title"] in old:
        g["status"], g["owner"] = old[g["title"]].get("status", "todo"), old[g["title"]].get("owner", "")
path.write_text(json.dumps(G, indent=2, ensure_ascii=False), encoding="utf-8")
print("gaps:", len(G))

# ---------------------------------------------------------------- analytics file
# NOTE: the tracker's "Week 1" row (w/c 9 Nov 2026) is example data dated in the future, so weekly rows are
# NOT imported. Real baseline (Current Metrics, 31 Oct 2026): 955 followers — shown on the Analytics page.
mpath = ROOT / "data" / "metrics.json"
if not mpath.exists():
    mpath.write_text(json.dumps({"weekly": [], "scorecard": {}}, indent=2), encoding="utf-8")
print("metrics file ready")
