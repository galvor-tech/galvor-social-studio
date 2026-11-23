"""Decoded shift asked 23 Nov 2026: #6 goes out Tue 1 Dec, then fortnightly Tuesdays.

  #6 Creative Fatigue        1 Dec    (was Wed 25 Nov)
  #7 The Sale Is Over        15 Dec
  #8 A Year of Ads (2026)    29 Dec
  #9 Test Calendar           12 Jan
  #10 Budget Season          26 Jan
  #11 The Brief Is the Filter 9 Feb
  #12 Linen brand, month one 23 Feb
  #13 Agents, Not Headcount  9 Mar

Also fixes every post that points to an issue by number/date, and moves the Instagram
"Decoded is out" story packs to the new days.   py -3.15 tools/decoded_shift_2026-11-23.py [--apply]
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.store import all_posts, folder_of, save_post   # noqa: E402

TAG = "[Decoded shift 23 Nov 2026] "

ISSUES = [  # (title contains, new number, new date)
    ("Creative Fatigue", 6, "2026-12-01"),
    ("The Sale Is Over", 7, "2026-12-15"),
    ("What a Year of Ads", 8, "2026-12-29"),
    ("Build a Test Calendar", 9, "2027-01-12"),
    ("Budget Season", 10, "2027-01-26"),
    ("The Brief Is the Filter", 11, "2027-02-09"),
    ("Same Budget, $3,800 Moved", 12, "2027-02-23"),
    ("Agents, Not Headcount", 13, "2027-03-09"),
]

# (platform, date, time) -> changes. Text edits are (field, old, new) exact replacements.
EDITS = [
    ("instagram", "2026-11-24", "12:30", dict(text=[
        ("alt_text", "Frame 5 says Decoded #6 on creative fatigue lands tomorrow.", "Frame 5 says Decoded #6 on creative fatigue lands Tuesday 1 Dec."),
        ("cta", "follow @galvor.ai for tomorrow's Decoded #6", "follow @galvor.ai for Decoded #6 on Tuesday 1 Dec"),
        ("creative", "Tomorrow: Decoded #6 on *creative fatigue.*", "Next Tuesday: Decoded #6 on *creative fatigue.*"),
        ("creative", "Decoded #6 lands tomorrow", "Decoded #6 lands Tuesday 1 Dec"),
    ])),
    ("instagram", "2026-11-25", "12:30", dict(move=("2026-12-01", "10:00"))),       # story pack: Decoded #6 is out
    ("linkedin", "2026-11-25", "12:30", dict(text=[
        ("first_comment", "Read Decoded #6 on galvor.ai", "Decoded #6 goes deeper on creative fatigue. Out Tuesday 1 Dec on galvor.ai"),
        ("cta", "first comment points to Decoded #6 (same day, same topic)", "first comment points to Decoded #6 (out 1 Dec, same topic)"),
        ("creative", "Read Decoded #6 on galvor.ai", "Decoded #6 lands 1 Dec on galvor.ai"),
    ])),
    ("linkedin", "2026-11-26", "12:30", dict(text=[
        ("first_comment", "Decoded #7, out next Wednesday,", "Decoded #7, out Tuesday 15 Dec,"),
    ])),
    ("instagram", "2026-11-26", "13:00", dict(text=[("first_comment", "is out on Wedn", "is out on Tue 15 Dec. Wedn")])),
    ("instagram", "2026-11-30", "19:00", dict(text=[("first_comment", "Out Wednesday on galvor.ai.", "Out Tuesday 15 Dec on galvor.ai.")])),
    ("instagram", "2026-12-02", "19:00", dict(text=[("first_comment", "Read Decoded #7 on galvor.ai", "Decoded #7 goes deeper on this. Out Tuesday 15 Dec on galvor.ai")])),
    ("instagram", "2026-12-07", "19:00", dict(text=[("first_comment", "Decoded #8 goes deeper on this. Out Wednesday on galvor.ai.", "We write about this in Decoded, our newsletter. Link in bio.")])),
    ("instagram", "2026-12-18", "13:00", dict(text=[
        ("caption", "read Decoded #9 for what a year of ads taught us. Link in bio.", "look out for Decoded #8 on what a year of ads taught us, out 29 Dec. Link in bio."),
        ("first_comment", "Read Decoded #9 on galvor.ai.", "Decoded #8, what a year of ads taught us, is out 29 Dec on galvor.ai."),
        ("alt_text", "read Decoded #9, follow @galvor.ai.", "Decoded #8 is out 29 Dec, follow @galvor.ai."),
        ("cta", "read Decoded #9 via link in bio", "Decoded #8 out 29 Dec, link in bio"),
        ("creative", "Decoded #9 covers what a year of ads taught us.", "Decoded #8 (29 Dec) covers what a year of ads taught us."),
        ("creative", "Read Decoded #9: link in bio", "Decoded #8 is out 29 Dec"),
    ])),
    ("instagram", "2026-12-25", "13:00", dict(text=[("first_comment", "Decoded #11 goes deeper on this. Out Wednesday on galvor.ai.", "Decoded #9 goes deeper on this. Out Tuesday 12 Jan on galvor.ai.")])),
    ("instagram", "2026-12-28", "19:00", dict(text=[("first_comment", "Read Decoded #9 on galvor.ai.", "Decoded #8 goes deeper on this. Out tomorrow on galvor.ai.")])),
    ("instagram", "2026-12-30", "12:30", dict(move=("2027-01-12", "10:00"), renumber=(11, 9))),   # story pack: test calendar
    ("instagram", "2027-01-06", "12:30", dict(archive=True)),                                     # story pack: Learning Loop (issue archived)
    ("instagram", "2027-01-12", "12:30", dict(move=("2027-01-25", "12:30"), renumber=(13, 10))),  # teaser: budget season lands tomorrow
    ("linkedin", "2026-12-02", "09:00", dict(text=[("first_comment", "Decoded #7 is out tomorrow on galvor.ai:", "Decoded #7 is out on 15 Dec on galvor.ai:")])),
    ("linkedin", "2026-12-09", "09:00", dict(clear_comment=True)),          # pointed to Agents (now 9 Mar)
    ("linkedin", "2026-12-24", "16:00", dict(clear_comment=True)),          # pointed to Agents
    ("linkedin", "2027-01-06", "09:00", dict(clear_comment=True)),          # pointed to Agents
    ("linkedin", "2027-01-20", "09:00", dict(clear_comment=True)),          # pointed to Learning Loop (archived)
    ("linkedin", "2027-02-05", "09:00", dict(renumber=(11, 9))),            # test calendar
    ("linkedin", "2027-02-12", "09:00", dict(renumber=(13, 10))),           # budget season
]


def one(posts, plat, date, time, exclude_series=("Page repost",)):
    hits = [p for p in posts if p["platform"] == plat and p["date"] == date and p["time"] == time
            and p.get("series") not in exclude_series]
    if len(hits) != 1:
        raise SystemExit(f"{plat} {date} {time}: expected 1, got {[h['id'] for h in hits]}")
    return hits[0]


def replace_in(p, field, old, new):
    if field == "creative":
        import json
        s = json.dumps(p["creative"], ensure_ascii=False)
        if old not in s:
            raise SystemExit(f"{p['id']}: '{old}' not in slides")
        p["creative"] = json.loads(s.replace(old, new))
    else:
        if old not in (p.get(field) or ""):
            raise SystemExit(f"{p['id']}: '{old}' not in {field}")
        p[field] = p[field].replace(old, new)


def renum(p, a, b):
    import json
    for k in ("title", "hook", "caption", "first_comment", "cta", "alt_text", "notes"):
        if isinstance(p.get(k), str):
            p[k] = p[k].replace(f"Decoded #{a}", f"Decoded #{b}")
    p["creative"] = json.loads(json.dumps(p["creative"], ensure_ascii=False).replace(f"Decoded #{a}", f"Decoded #{b}"))


def main():
    apply = "--apply" in sys.argv
    posts = all_posts()
    plan = []
    for frag, n, date in ISSUES:
        hits = [p for p in posts if p["platform"] == "newsletter" and frag in p["title"]]
        if len(hits) != 1:
            raise SystemExit(f"issue {frag}: {[h['id'] for h in hits]}")
        p = dict(hits[0]); old = (p["date"], p["title"])
        p["title"] = f"Decoded #{n}: " + p["title"].split(":", 1)[1].strip()
        renum(p, int(old[1].split("#")[1].split(":")[0]), n) if old[1].startswith("Decoded #") else None
        p["title"] = f"Decoded #{n}: " + hits[0]["title"].split(":", 1)[1].strip()
        p["date"], p["time"] = date, "08:30"
        p["notes"] = (p.get("notes") or "") + f"\n{TAG}was {old[0]} as '{old[1][:40]}'; now #{n} on Tue {date}."
        plan.append(("save", hits[0], p))
    for plat, date, time, ch in EDITS:
        p = dict(one(posts, plat, date, time))
        if ch.get("archive"):
            plan.append(("archive", p, None)); continue
        for field, old, new in ch.get("text", []):
            replace_in(p, field, old, new)
        if ch.get("renumber"):
            renum(p, *ch["renumber"])
        if ch.get("clear_comment"):
            p["first_comment"] = ""
            if "Decoded" in (p.get("cta") or ""):
                p["cta"] = "Follow Galvor"
        if ch.get("move"):
            p["date"], p["time"] = ch["move"]
            clash = [q["id"] for q in posts if q["platform"] == plat and q["date"] == p["date"] and q["time"] == p["time"] and q["id"] != p["id"]]
            if clash:
                print("NOTE slot already used:", plat, p["date"], p["time"], clash)
        p["notes"] = (p.get("notes") or "") + f"\n{TAG}links/dates updated for the new Decoded schedule."
        plan.append(("save", posts[[q["id"] for q in posts].index(p["id"])], p))
    for kind, old, new in plan:
        if kind == "archive":
            print("ARCHIVE", old["id"])
        else:
            print("SAVE   ", old["date"], "->", new["date"], new["time"], new["platform"][:2], new["title"][:60])
    if not apply:
        print("dry run"); return
    for kind, old, new in plan:
        if kind == "archive":
            src = folder_of(old); dst = ROOT / "content_archive" / src.relative_to(ROOT / "content")
            dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst))
        else:
            save_post({k: v for k, v in new.items() if k != "_folder"}, note=TAG.strip())
    print("applied")


if __name__ == "__main__":
    main()
