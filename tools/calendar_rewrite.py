"""Calendar rewrite helper (19 Nov 2026 to 18 Feb 2027). Scripts only: never renders media.

    py -3.15 tools/calendar_rewrite.py prepare          backs up, writes one manifest per group to queue/rewrite/
    py -3.15 tools/calendar_rewrite.py apply <group>    reads queue/rewrite/<group>.out.json, saves the posts, lints
    py -3.15 tools/calendar_rewrite.py status           what has been rewritten so far, and open problems
"""
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.config import DATA, PILLARS  # noqa: E402
from core.lint import lint_post  # noqa: E402
from core.store import all_posts, get_post, save_post  # noqa: E402

START, END = "2026-11-19", "2027-02-18"
Q = ROOT / "queue" / "rewrite"
MARK = "[Calendar rewrite 16 Nov 2026]"
FIELDS = ("title", "hook", "caption", "first_comment", "hashtags", "alt_text", "cta", "script", "poll", "creative",
          "notes", "pillar", "job", "series", "topic_ref")


def group_of(p):
    if p["platform"] == "linkedin":
        return {"sunil": "li_sunil", "raj": "li_raj", "shrutik": "li_shrutik"}.get(p.get("voice"), "li_company")
    f = p.get("format")
    return {"carousel": "ig_carousel", "reel": "ig_reel_story", "story": "ig_reel_story"}.get(f, "ig_image")


def in_scope():
    return sorted((p for p in all_posts() if p["platform"] in ("linkedin", "instagram") and START <= p["date"] <= END
                   and p.get("status") in ("idea", "draft", "designed")), key=lambda p: (p["date"], p["time"]))


def prepare():
    Q.mkdir(parents=True, exist_ok=True)
    backup = ROOT / "logs" / "calendar_backup_2026-11-16.zip"
    if not backup.exists():
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as z:
            for f in (ROOT / "content").rglob("post.json"):
                z.write(f, f.relative_to(ROOT))
        print("backup written:", backup)
    decoded = [{"date": p["date"], "title": p.get("title")} for p in all_posts("newsletter") if START <= p["date"] <= END]
    groups = {}
    for p in in_scope():
        groups.setdefault(group_of(p), []).append({
            "id": p["id"], "date": p["date"], "weekday": date.fromisoformat(p["date"]).strftime("%a"), "time": p["time"],
            "format": p.get("format"), "pillar": p.get("pillar"), "job": p.get("job"), "series": p.get("series"),
            "festival": p.get("festival"), "theme": p.get("theme"), "topic_ref": p.get("topic_ref"),
            "current_title": p.get("title"), "current_hook": p.get("hook"),
            "has_slides": len((p.get("creative") or {}).get("slides") or []),
            "allowed_pillars": PILLARS[p["platform"]]})
    for g, rows in groups.items():
        (Q / f"{g}.manifest.json").write_text(json.dumps({"group": g, "decoded_issues": decoded, "posts": rows},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
        print(g, len(rows))


SPEC_TEXT = (DATA / "CONTENT_SPEC.md").read_text(encoding="utf-8")


def odd_numbers(p):
    """Numbers in the words that are not in the facts bank. Small counts, times and years are ignored."""
    blob = json.dumps([p.get("caption"), p.get("hook"), p.get("script"), (p.get("creative") or {}).get("slides"), p.get("poll")],
                      ensure_ascii=False)
    out = set()
    for m in re.finditer(r"[+\-−]?\$?₹?\d[\d,]*(?:\.\d+)?\s?(?:%|×|x\b|k\b|K\b|lakh|crore|million|billion)?", blob):
        tok = m.group(0).strip()
        core = re.sub(r"[^\d.]", "", tok)
        if not core:
            continue
        try:
            val = float(core.replace(",", ""))
        except ValueError:
            continue
        unit = bool(re.search(r"%|×|x$|k$|K$|lakh|crore|million|billion|\$|₹", tok))
        if not unit and (val <= 60 or 1990 <= val <= 2030):
            continue
        if core in SPEC_TEXT or re.sub(r"[^\d.,]", "", tok).strip(",.") in SPEC_TEXT:
            continue
        out.add(tok)
    return sorted(out)


def apply(group):
    src = Q / f"{group}.out.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    allowed = {r["id"] for r in json.loads((Q / f"{group}.manifest.json").read_text(encoding="utf-8"))["posts"]}
    done, problems = 0, 0
    for new in data["posts"]:
        pid = new.get("id")
        if pid not in allowed:
            print(f"SKIP {pid}: not in this group's manifest")
            problems += 1
            continue
        p = get_post(pid)
        if not p:
            print(f"SKIP {pid}: not found")
            problems += 1
            continue
        for k in FIELDS:
            if k in new:
                p[k] = new[k]
        if p.get("pillar") not in PILLARS[p["platform"]]:
            print(f"FIX  {pid}: pillar '{p.get('pillar')}' is not allowed")
            problems += 1
            continue
        if isinstance(p.get("hashtags"), str):
            p["hashtags"] = p["hashtags"].split()
        p["status"], p["images"] = "draft", []
        p["script_decision"] = {"choice": "pending"}
        notes = re.sub(r"\n?\[16 Nov 2026\] Media deleted;[^\n]*", "", p.get("notes") or "")
        if MARK not in notes:
            notes = (notes.strip() + f"\n{MARK} Script rewritten with the new prompts. No media yet.").strip()
        p["notes"] = notes
        saved = save_post(p, note="Calendar rewrite: new script (16 Nov 2026)")
        issues = [i for i in lint_post(saved) if i["field"] != "images"]
        errs = [i for i in issues if i["severity"] == "error"]
        nums = odd_numbers(saved)
        done += 1
        if errs or nums:
            problems += 1
            print(f"FIX  {pid}")
            for i in errs:
                print(f"       error {i['field']}: {i['message']}")
            if nums:
                print(f"       numbers not in the facts bank: {nums}")
    print(f"{group}: {done} saved, {problems} with problems, {len(allowed) - done} not yet written")


def status():
    by = {}
    for p in in_scope():
        g = by.setdefault(group_of(p), {"total": 0, "done": 0, "errors": 0, "numbers": 0})
        g["total"] += 1
        if MARK in (p.get("notes") or ""):
            g["done"] += 1
            if any(i["severity"] == "error" and i["field"] != "images" for i in lint_post(p)):
                g["errors"] += 1
            if odd_numbers(p):
                g["numbers"] += 1
    for k, v in sorted(by.items()):
        print(k, v)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prepare":
        prepare()
    elif cmd == "apply" and len(sys.argv) > 2:
        apply(sys.argv[2])
    elif cmd == "status":
        status()
    else:
        sys.exit(__doc__)
