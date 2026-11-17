"""Re-slot the plan onto the fixed posting rhythm (agreed 11 Nov 2026).

  python tools/rebuild_plan_2026.py            # dry run: prints the new plan
  python tools/rebuild_plan_2026.py --apply    # moves the posts

Rules
- Window starts tomorrow-ish (START). Posts already published are never touched.
- Festival / date-bound posts keep their date; only their time is standardised.
- Everything else keeps its order and is placed into the next free slot for its voice (LinkedIn) or format (Instagram).
- Nothing is deleted: posts that don't fit before 31 Dec roll into January on the same rhythm.
- Festival posts whose date has already passed are marked skipped; an empty, untitled idea is skipped.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import MONTHLY_THEMES, SLOTS  # noqa: E402
from core.store import all_posts, save_post  # noqa: E402

TODAY = date(2026, 11, 11)
START = TODAY + timedelta(days=1)   # grid starts tomorrow: today's posts stay as they are
HORIZON = date(2027, 5, 31)       # roll-over space; the agreed plan is to 31 Dec 2026
PINNED_TITLES = ("decoded", "year end", "year-end", "monday huddle", "black friday", "cyber monday", "christmas", "new year", "last week of december",
                 "diwali", "republic day", "startup day", "privacy day", "lohri", "sankranti", "pongal")


def pinned(p) -> bool:
    t = (p.get("title") or "").lower()
    return bool(p.get("festival")) or any(k in t for k in PINNED_TITLES) or p.get("format") == "issue"


def is_reshare(p) -> bool:
    return p["platform"] == "linkedin" and "reshare" in (p.get("title") or "").lower()


def slot_kind(p) -> str:
    if p["platform"] == "linkedin":
        return p.get("voice") or "company"
    f = p.get("format")
    return {"carousel": "carousel", "reel": "reel", "story": "story"}.get(f, "image")


def grid(platform: str):
    """Yield (date, time, kind) slots from START to HORIZON for a platform."""
    d = START
    while d <= HORIZON:
        for wd, tm, kind in SLOTS[platform]:
            if d.weekday() == wd:
                yield d, tm, kind
        d += timedelta(days=1)


MAX_EARLIER = 7   # days a post may move earlier than planned (later is fine) — keeps time-bound copy honest


def _ok_earlier(p, d) -> bool:
    return (date.fromisoformat(p["date"]) - d).days <= MAX_EARLIER


def plan():
    moves, skips = [], []
    global open_slots
    open_slots = []
    posts = [p for p in all_posts() if p.get("status") not in ("published", "skipped")]
    for platform in ("linkedin", "instagram"):
        mine = [p for p in posts if p["platform"] == platform and p["date"] >= "2026-11-09"]
        fixed, pool = [], {}
        for p in mine:
            if pinned(p) or p["date"] == TODAY.isoformat():
                if p["date"] < TODAY.isoformat():
                    skips.append((p, "festival date has passed"))
                else:
                    fixed.append(p)
            elif not (p.get("title") or "").strip() or (p.get("title") or "").strip().lower() == "new post":
                skips.append((p, "empty idea"))
            elif is_reshare(p):
                pool.setdefault("reshare", []).append(p)
            else:
                pool.setdefault(slot_kind(p), []).append(p)
        taken = set()
        std = SLOTS["festival_time"][platform]
        for p in fixed:
            d = date.fromisoformat(p["date"])
            # a pinned post on a slot day takes that slot (same kind for IG; company slot for LI)
            for wd, tm, kind in SLOTS[platform]:
                if d.weekday() == wd and (kind == slot_kind(p) or (platform == "linkedin" and kind == "company"
                                                                    and p.get("voice") == "company")):
                    if (d, kind) not in taken:
                        taken.add((d, kind))
                        tm_use = tm
                        break
            else:
                tm_use = SLOTS["story_time"] if p.get("format") == "story" else std
            moves.append((p, d.isoformat(), tm_use))
        reshares = pool.pop("reshare", [])
        fri = [(d, tm) for d, tm, kind in grid(platform) if platform == "linkedin" and kind == "company" and d.weekday() == 4]
        for d, tm, kind in grid(platform):
            if (d, kind) in taken:
                continue
            if platform == "linkedin" and kind == "company" and d.weekday() == 4:
                continue                                  # Fridays are for reshares first (pass 2)
            if not pool.get(kind) or not _ok_earlier(pool[kind][0], d):
                open_slots.append((platform, d.isoformat(), tm, kind))
                continue
            p = pool[kind].pop(0)
            taken.add((d, kind))
            moves.append((p, d.isoformat(), tm))
        # pass 2: each reshare goes to the first free Friday after the post it reshares
        placed = {m[0]["id"]: m[1] for m in moves}
        import difflib
        personal = [m for m in moves if m[0]["platform"] == "linkedin" and m[0].get("voice") != "company"]
        for r in reshares:
            key = re.sub(r"^weekly reshare:\s*", "", (r.get("title") or "").lower())
            best = max(personal, key=lambda m: difflib.SequenceMatcher(None, key, (m[0].get("title") or "").lower()).ratio(), default=None)
            after = date.fromisoformat(best[1]) if best else START
            for d, tm in fri:
                if d > after and (d, "company") not in taken:
                    taken.add((d, "company"))
                    moves.append((r, d.isoformat(), tm))
                    break
        # pass 3: Fridays still free take the next company post
        for d, tm in fri:
            if (d, "company") in taken:
                continue
            if pool.get("company") and _ok_earlier(pool["company"][0], d):
                taken.add((d, "company"))
                moves.append((pool["company"].pop(0), d.isoformat(), tm))
            else:
                open_slots.append((platform, d.isoformat(), tm, "company"))
        for kind, rest in pool.items():
            for p in rest:
                skips.append((p, f"no {kind} slot before {HORIZON}"))
    # newsletter: keep date, standard time
    for p in posts:
        if p["platform"] == "newsletter" and p["date"] >= TODAY.isoformat():
            moves.append((p, p["date"], "08:30"))
    open_slots[:] = [o for o in open_slots if o[1] <= "2026-12-31"]
    return moves, skips


def main(apply: bool):
    moves, skips = plan()
    moves.sort(key=lambda m: (m[1], m[2], m[0]["platform"]))
    changed = 0
    for p, d, tm in moves:
        mark = "" if (p["date"], p.get("time")) == (d, tm) else f"   (was {p['date']} {p.get('time')})"
        if d <= "2026-12-31":
            print(f"{d} {tm}  {p['platform'][:2]}  {p.get('voice','')[:7]:7} {p.get('format','')[:8]:8} {(p.get('title') or '')[:58]}{mark}")
        if apply and mark:
            if p["date"] < TODAY.isoformat():
                p["rescheduled_from"] = p["date"]
            p["date"], p["time"] = d, tm
            p["theme"] = MONTHLY_THEMES.get(d[:7], p.get("theme", ""))
            p.pop("due", None)
            save_post(p, note=f"Re-slotted to the Nov 2026 rhythm ({d} {tm})")
            changed += 1
    print("\nRolled past 31 Dec:", sum(1 for _, d, _ in moves if d > "2026-12-31"))
    for p, why in skips:
        print(f"SKIP {p['date']} {p['platform'][:2]} {(p.get('title') or '')[:50]} — {why}")
        if apply and "slot before" not in why:
            p["status"] = "skipped"
            save_post(p, note=f"Skipped in Nov 2026 re-plan: {why}")
    print("\nOpen slots to 31 Dec (fill with new drafts):")
    opens = sorted(set(open_slots), key=lambda o: (o[1], o[2]))
    for o in opens:
        print("  OPEN", *o)
    if apply:
        import json
        (ROOT / "staging" / "open_slots.json").write_text(json.dumps(opens, indent=1), encoding="utf-8")
        print(f"\nApplied: {changed} moved.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
