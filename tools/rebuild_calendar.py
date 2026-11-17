"""Rebuild data/festivals.json as: festivals + AI dates + marketing dates (nothing else).

Source of truth: data/festivals_full_backup.json (the original verified 100-entry list)
plus data/ai_marketing_dates.json (verified AI & marketing industry dates). Re-runnable.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "data" / "festivals_full_backup.json"
EXTRA = ROOT / "data" / "ai_marketing_dates.json"
OUT = ROOT / "data" / "festivals.json"

NATIONAL_FESTIVALS = ("Republic Day", "Independence Day", "Gandhi Jayanti", "New Year's Day")
# D2C marketing moments: sales + gifting occasions brands build creative around
MARKETING_KEEP = ("11.11", "Black Friday", "Small Business Saturday", "Cyber Monday", "End of Reason Sale", "12.12",
                  "Republic Day sales", "Prime Day", "Great Indian Festival", "Valentine's Day", "Mother's Day",
                  "Father's Day", "World Social Media Day", "World Creativity and Innovation Day",
                  "Goafest", "Google Marketing Live", "Cannes Lions", "D2C summits")
AI_KEEP = ("Data Privacy Day", "Nasscom Technology & Leadership Forum", "SaaSBoomi", "India Mobile Congress", "TechSparks")
RENAME = {  # strip unrelated halves of combined entries
    "Black Friday 2027 / Constitution Day": "Black Friday 2027",
    "World Social Media Day / Q1 FY2027-28 end": "World Social Media Day",
}

full = json.loads(FULL.read_text(encoding="utf-8"))
out = []
for f in full:
    f = dict(f)
    f["name"] = RENAME.get(f["name"], f["name"])
    if f["category"] == "festival":
        out.append(f)
    elif f["category"] in ("national", "global_day") and any(f["name"].startswith(n) for n in NATIONAL_FESTIVALS):
        f["category"], f["kind"] = "festival", "national festival"
        out.append(f)
    elif any(k in f["name"] for k in AI_KEEP):
        f["kind"] = "event" if f["category"] == "industry" else "day"
        f["category"] = "ai"
        out.append(f)
    elif any(k in f["name"] for k in MARKETING_KEEP):
        f["kind"] = {"sale": "sale", "industry": "event"}.get(f["category"], "occasion")
        f["category"] = "marketing"
        out.append(f)

if EXTRA.exists():
    seen = {(f["date"], f["name"].lower()) for f in out}
    names = {f["name"].lower().split(" 20")[0] for f in out}
    for e in json.loads(EXTRA.read_text(encoding="utf-8")):
        if e.get("category") not in ("ai", "marketing") or not e.get("date"):
            continue
        base = e["name"].lower().split(" 20")[0]
        rank = {"confirmed": 0, "moon_sighting": 1, "estimate": 2, "tbc": 3}
        dup = next((f for f in out if f["date"][:4] == e["date"][:4] and (
                    f["name"].lower().split(" 20")[0].split(" (")[0] == base.split(" (")[0])), None)
        if dup:
            if rank.get(e.get("confidence"), 3) < rank.get(dup.get("confidence"), 3):
                out.remove(dup)          # newer, better-verified date replaces the older estimate
            else:
                continue
        e.setdefault("kind", "event")
        out.append(e)
        names.add(base)

out.sort(key=lambda f: (f["date"], f["category"], f["name"]))
OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
from collections import Counter
print(len(out), dict(Counter(f["category"] for f in out)))
