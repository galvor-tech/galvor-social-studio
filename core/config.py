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
    "linkedin": [
        (0, "12:30", "shrutik"),
        (1, "09:00", "sunil"),
        (2, "09:00", "raj"),
        (3, "09:00", "sunil"),
        (3, "12:30", "company"),
        (4, "09:00", "shrutik"),
        (4, "12:30", "company"),
    ],
    "instagram": [
        (0, "19:00", "carousel"),
        (2, "19:00", "reel"),
        (4, "13:00", "carousel"),
        (3, "13:00", "image"),     # was Saturday 11:00; posting is Monday to Friday only (16 Nov 2026)
        (1, "12:30", "story"),
    ],
    "festival_time": {"linkedin": "09:00", "instagram": "11:00"},
    "story_time": "12:30",
    "newsletter": (2, "08:30"),   # Decoded: every Wednesday, LinkedIn newsletter from the Galvor page + email
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
    "Personal profiles post first, as their own native post in their own voice. Never a plain repost of a company post (little reach).",
    "The Galvor page follows 1-2 days later with the link, report, launch or carousel, or reshares the personal post with its own line.",
    "Links never go in a personal post's body (they cut reach). Put them in the first comment, or point to the Galvor page post.",
    "Links, Decoded, reports, launches and carousels belong on the Galvor page (links help reach there).",
    "Decoded is always posted from the Galvor page (Wed 08:30), never from Raj's handle. Raj, Sunil and Shrutik repost it with their own line or comment in the first hour.",
    "Every personal post still closes with Follow Galvor / @galvor.ai, so the founders' reach builds page followers.",
    "Same news, different angle per person: Sunil money and risk, Raj product and data, Shrutik marketing craft and behind the scenes.",
    "The other team members leave a real comment in the first hour; the author replies to every comment.",
    "Weekly target: Sunil 2, Raj 1 (+ Decoded), Shrutik 2, Galvor page 3 (Decoded + 2). About three-quarters of reach should come from personal profiles.",
]

WEEKDAYS_ONLY = True   # nothing is planned for Saturday or Sunday

RHYTHM = {
    "linkedin": [
        ("Mon", "12:30", "shrutik", "Shrutik — Brief to Live / client reality"),
        ("Tue", "09:00", "sunil", "Sunil — What I Heard in the Room (money, risk, CMO worries)"),
        ("Wed", "08:30", "company", "Decoded — LinkedIn newsletter from the Galvor page (+ email). Team comments/reposts in the first hour"),
        ("Wed", "09:00", "raj", "Raj — Ad of the Week / building the engine"),
        ("Thu", "09:00", "sunil", "Sunil — his own take on the week's Galvor news or launch (link in first comment)"),
        ("Thu", "12:30", "company", "Galvor page — proof, product or launch with the link, 1-2 days after a team member covered it"),
        ("Fri", "09:00", "shrutik", "Shrutik — behind the scenes on a campaign / marketing craft"),
        ("Fri", "12:30", "company", "Galvor page — reshare the week's best personal post with its own line, or a carousel"),
    ],
    "instagram": [
        ("Mon", "19:00", "company", "Carousel — framework / tip"),
        ("Tue", "12:30", "company", "Stories — poll, quiz, behind the scenes"),
        ("Wed", "12:30", "company", "Story — Decoded is out (link in bio)"),
        ("Wed", "19:00", "company", "Reel — ad breakdown or behind the scenes"),
        ("Fri", "13:00", "company", "Carousel — data drop / myth vs fact"),
        ("Thu", "13:00", "company", "Single image — meme, relatable, culture (reel when one is ready)"),
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
