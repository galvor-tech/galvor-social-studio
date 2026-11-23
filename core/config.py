"""Central configuration for Galvor Social Studio: paths, brand, voices, strategy."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # .../studio
CONTENT = ROOT / "content"
DATA = ROOT / "data"
STATIC = ROOT / "static"
CREATIVES = ROOT / "creatives"
EXPORTS = ROOT / "exports"
LOGS = ROOT / "logs"
SETTINGS_FILE = DATA / "settings.json"
ENV_FILE = ROOT / ".env"

PLATFORMS = ("linkedin", "instagram", "newsletter")

# ---------------------------------------------------------------- brand
BRAND = {
    "name": "Galvor",
    "site": "galvor.ai",
    "brand": "#7A36EB",
    "gold": "#FFC43D",
    "violet_dark": "#160A33",
    "tagline": "Know why your ads win.",
    "linkedin": "https://www.linkedin.com/company/galvorai",
    "instagram": "https://www.instagram.com/galvor.ai/",
    "youtube": "https://www.youtube.com/@galvorai",
}

# ---------------------------------------------------------------- creative sizes
SIZES = {
    "feed": (1080, 1350),     # 4:5 — Instagram feed + LinkedIn image/carousel (mobile-optimal)
    "square": (1080, 1080),
    "story": (1080, 1920),    # Instagram story / reel cover / LinkedIn vertical video cover
}

# ---------------------------------------------------------------- voices (from the 90-day LinkedIn plan v3)
VOICES = {
    "company": {"name": "Galvor", "role": "Company page", "initials": "G", "lens": "Proof, product, launches, links, Decoded; posts 1-2 days after a team member covers the same news, and reshares the best personal post each week", "color": "#7A36EB"},
    "sunil":   {"name": "Sunil Humne", "role": "Co-founder, Galvor", "initials": "SH", "lens": "Executive voice: money, risk, teams, what CMOs and founders worry about", "series": "What I Heard in the Room", "color": "#2F6FDB"},
    "raj":     {"name": "Raj Dhakad", "role": "Founding AI Engineer, Galvor", "initials": "RD", "lens": "Builder voice: what the ads and numbers really say, how we built the engine", "series": "Ad of the Week", "color": "#14866D"},
    "shrutik": {"name": "Shrutik Rathod", "role": "Client Servicing, Galvor", "initials": "SR", "lens": "Client reality voice: briefs, creators, approvals, QC, brief to live", "series": "Brief to Live", "color": "#C2581B"},
}

JOBS = ["Attract", "Educate", "De-risk", "Convert"]
JOB_MIX = {"Attract": 35, "Educate": 35, "De-risk": 20, "Convert": 10}

FORMATS = {
    "linkedin": ["text", "image", "carousel", "poll", "video", "newsletter", "article"],
    "instagram": ["image", "carousel", "reel", "story"],
    "newsletter": ["issue"],
}
FORMAT_MIX_LINKEDIN = {"text": 45, "carousel": 25, "video": 20, "poll": 10}

PILLARS = {
    "linkedin": [
        "Decode Teardown", "Brand Memory / POV", "Marketing Money", "AI & the Team",
        "In the Room", "Building Galvor", "Public Data", "Measurement", "Creators & Testing",
        "Better Briefs", "Creator Ops India", "Feedback & Approvals", "Client Lessons",
        "Product / Demo", "Proof / Case Study", "Festival / Culture", "People / Team", "Newsletter",
    ],
    "instagram": [
        "Ad Breakdown", "Myth vs Fact", "Quick Tip", "Data Drop", "Framework",
        "Behind the Scenes", "Team & Culture", "Festival / Culture", "Product / Demo",
        "Proof / Case Study", "Meme / Relatable", "Newsletter",
    ],
    "newsletter": ["Newsletter"],
}

STATUSES = ["idea", "draft", "designed", "in_review", "approved", "scheduled", "published", "skipped"]
STATUS_LABEL = {
    "idea": "Idea", "draft": "Draft", "designed": "Designed", "in_review": "In review",
    "approved": "Approved", "scheduled": "Scheduled", "published": "Published", "skipped": "Skipped",
}

MONTHLY_THEMES = {
    "2026-11": "From dashboards to decisions",
    "2026-12": "People + agents",
    "2027-01": "The learning loop",
    "2027-02": "Proof season: pilots & client stories",
    "2027-03": "Year-end budgets: spend that teaches",
    "2027-04": "New FY, new creative system",
}

PHRASES = [
    "Every ad should make the next one better.",
    "Plenty of data, no memory.",
    "From dashboards to decisions.",
    "Scale, cut, refresh, test.",
    "Learn → create → measure → learn.",
]

POST_RULES = [
    "One post, one argument. Never pack five features into one post.",
    "Open with tension, an observation or a claim — never “Excited to share”.",
    "Start from something we really saw, measured, built or changed our mind about.",
    "Earn the product mention: the buyer's problem comes first.",
    "Never claim a competitor's spend or ROAS from public data.",
    "No client name or client numbers without written permission.",
    "Small samples are “a signal” or “a pattern to test”, never a rule.",
    "Three people, three voices. If posts start to sound the same, rewrite.",
    "Short paragraphs; written for mobile.",
    "End with a question only when there's a real conversation to have.",
    "Links go in the first comment, not the post body.",
    "The closing CTA always asks people to follow Galvor (@galvor.ai on Instagram), never an individual.",
]

# ---------------------------------------------------------------- posting rhythm (IST) — personal-first, 17 Nov 2026
# Personal profiles carry the reach (Aug-Nov 2026: Sunil median ~1,900 impressions a post vs ~270 for the page), so
# team members post first, natively, and the page follows 1-2 days later with the link / report / reshare.
# Previous rhythm (11 Nov 2026) had 3 personal + 3 page LinkedIn slots; now 5 personal + 3 page (incl. Decoded).
# Fixed slots so posting becomes a habit and time-slot results are comparable. Start here, then move to the
# hours Instagram Insights / LinkedIn exports show once there are ~4 weeks of data (Results → Patterns).
# (weekday 0=Mon, time, kind) — kind is a voice for LinkedIn, a format for Instagram.
SLOTS = {
    "linkedin": [                  # plan from 30 Nov 2026: Sunil 3, Raj 2, Shrutik 1; page reposts each ~4h later
        (0, "09:00", "sunil"),
        (0, "13:00", "company"),
        (1, "12:30", "raj"),
        (1, "16:30", "company"),
        (2, "09:00", "sunil"),
        (2, "13:00", "company"),
        (3, "09:00", "shrutik"),
        (3, "13:00", "company"),
        (3, "16:00", "raj"),
        (4, "09:00", "sunil"),
        (4, "13:00", "company"),
        (4, "16:00", "company"),
    ],
    "instagram": [                 # from 24 Nov 2026: 3 reels (Mon/Wed/Fri) + 2 posts (Tue/Thu) a week
        (0, "19:00", "reel"),
        (1, "13:00", "image"),
        (2, "19:00", "reel"),
        (3, "13:00", "carousel"),
        (4, "19:00", "reel"),
        (1, "10:00", "story"),
    ],
    "festival_time": {"linkedin": "09:00", "instagram": "11:00"},
    "story_time": "12:30",
    "newsletter": (1, "08:30"),   # Decoded: fortnightly Tuesdays from 1 Dec 2026, Galvor page + email
}

# Who posts first, and why (shown on Strategy). Numbers from the Studio's LinkedIn imports, 1 Aug-16 Nov 2026.
REACH_FACTS = {
    "as_of": "16 Nov 2026",
    "rows": [("Posts", "26", "23"), ("Total impressions", "9,839", "65,544"),
             ("Median impressions a post", "~270", "~1,914"), ("Best post", "2,029", "8,383"),
             ("Followers", "955", "2,505")],
    "example": "Same news, 8 Sep 2026 (HealthKart partnership): 877 impressions on the Galvor page, 8,383 on Sunil's profile.",
}
DISTRIBUTION = [
    "Personal profiles post first, as their own native post in their own voice: Sunil 3 a week, Raj 2, Shrutik 1.",
    "The Galvor page reposts every personal post with its own short line, about 4 hours later, once the first hour of comments is done (Raj's Thursday post is reposted Friday 16:00).",
    "Links never go in a personal post's body (they cut reach). Put them in the first comment.",
    "Decoded goes out fortnightly on Tuesday at 08:30 from the Galvor page (next: 1 Dec 2026). Raj, Sunil and Shrutik repost it with their own line or comment in the first hour.",
    "Every personal post still closes with Follow Galvor / @galvor.ai, so the founders' reach builds page followers.",
    "Series: Sunil's Monday 'What I heard this week' (a real client problem, nobody named); Raj's Tuesday Brand Breakdown carousel (one non-client brand's public Meta ads); Shrutik's Thursday 'New on Instagram'.",
    "Client stories never name the client, the people, or details that identify them. Brand Breakdowns never pick a Galvor client or any CRM account.",
    "The other team members leave a real comment in the first hour; the author replies to every comment.",
    "Spacing: one post per person per day, two people at least 3 hours apart.",
    "Holiday Fridays (25 Dec, 1 Jan): Sunil is off, the page posts the greeting at 12:30.",
]

WEEKDAYS_ONLY = True   # nothing is planned for Saturday or Sunday

RHYTHM = {
    "linkedin": [
        ("Mon", "09:00", "sunil", "Sunil — What I heard this week: one real client problem, nobody named"),
        ("Mon", "13:00", "company", "Galvor page — repost Sunil's post with its own line"),
        ("Tue", "08:30", "company", "Decoded — fortnightly LinkedIn newsletter from the Galvor page (+ email)"),
        ("Tue", "12:30", "raj", "Raj — Brand Breakdown carousel: one brand's public Meta ads, read in full"),
        ("Tue", "16:30", "company", "Galvor page — repost Raj's Brand Breakdown"),
        ("Wed", "09:00", "sunil", "Sunil — money, AI and the marketing team"),
        ("Wed", "13:00", "company", "Galvor page — repost Sunil's post"),
        ("Thu", "09:00", "shrutik", "Shrutik — New on Instagram this week"),
        ("Thu", "13:00", "company", "Galvor page — repost Shrutik's post"),
        ("Thu", "16:00", "raj", "Raj — creator data, measurement, how the AI works"),
        ("Fri", "09:00", "sunil", "Sunil — Galvor's view, a poll or a lesson"),
        ("Fri", "13:00", "company", "Galvor page — repost Sunil's post"),
        ("Fri", "16:00", "company", "Galvor page — repost Raj's Thursday post"),
    ],
    "instagram": [
        ("Mon", "19:00", "company", "Reel — 25-40 s, one idea, cover + Follow @galvor.ai end card"),
        ("Tue", "13:00", "company", "Image or carousel"),
        ("Tue", "10:00", "company", "Story — Decoded is out (link in bio), on Decoded Tuesdays (fortnightly)"),
        ("Wed", "19:00", "company", "Reel"),
        ("Thu", "13:00", "company", "Carousel — New on Instagram this week (mirrors Shrutik's LinkedIn post)"),
        ("Fri", "19:00", "company", "Reel"),
    ],
}


def load_settings() -> dict:
    defaults = {
        "ai_provider": "auto",            # auto | anthropic | gemini
        "anthropic_model": "claude-opus-5-5",
        "gemini_model": "",
        "chrome_path": "",
        "public_base_url": "",            # needed for Instagram Graph API (image_url must be public)
        "linkedin_access_token": "",
        "linkedin_org_urn": "",           # urn:li:organization:XXXX
        "linkedin_person_urns": {},       # {"sunil": "urn:li:person:..."}
        "instagram_access_token": "",
        "instagram_user_id": "",
        "auto_publish": False,
        "scheduler_enabled": True,
        "reminder_minutes": 30,
        # team access
        "auth_mode": "off",               # off (this laptop only) | google
        "google_client_id": "",
        "google_client_secret": "",
        "allowed_domains": ["galvor.com"],
        "base_url": "",                   # e.g. https://cms.galvor.ai — used in email links + sign-in
        # notifications
        "notify_email": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "",
        "chat_webhook": "",               # Google Chat or Slack incoming-webhook URL
    }
    if SETTINGS_FILE.exists():
        try:
            defaults.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return defaults


def save_settings(data: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)


def load_env() -> None:
    """Minimal .env loader (no external dependency)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:  # blank values must not shadow other credential sources
            os.environ.setdefault(k.strip(), v)
    # The Claude key may be saved as CLAUDE_API_KEY; the Anthropic SDK reads ANTHROPIC_API_KEY.
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("CLAUDE_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]
