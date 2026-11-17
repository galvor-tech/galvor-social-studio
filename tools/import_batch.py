"""Validate (and optionally import + render) a batch of posts.

Usage:
  python tools/import_batch.py staging/<file>.json            # dry run: schema + lint report only
  python tools/import_batch.py staging/<file>.json --import   # save into content/ folders
  python tools/import_batch.py staging/<file>.json --import --render
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.config import FORMATS, JOBS, PILLARS, VOICES          # noqa: E402
from core.lint import lint_post                                  # noqa: E402
from core.store import blank_post, save_post, folder_of          # noqa: E402

REQUIRED = ["platform", "date", "time", "voice", "pillar", "job", "format", "title", "hook", "caption", "creative"]


def check_schema(p, i):
    errs = []
    for k in REQUIRED:
        if k not in p or p[k] in (None, ""):
            errs.append(f"missing {k}")
    if p.get("platform") not in FORMATS:
        errs.append("bad platform")
    if p.get("job") not in JOBS:
        errs.append(f"bad job {p.get('job')}")
    if p.get("pillar") not in PILLARS.get(p.get("platform"), []):
        errs.append(f"pillar '{p.get('pillar')}' not in PILLARS[{p.get('platform')}]")
    if p.get("voice") not in VOICES:
        errs.append("bad voice")
    if not isinstance(p.get("hashtags", []), list):
        errs.append("hashtags must be a list")
    if not isinstance(p.get("creative"), dict) or not isinstance(p["creative"].get("slides"), list):
        errs.append("creative.slides must be a list")
    return errs


def main():
    path = Path(sys.argv[1])
    do_import = "--import" in sys.argv
    do_render = "--render" in sys.argv
    posts = json.loads(path.read_text(encoding="utf-8"))
    bad = 0
    for i, raw in enumerate(posts):
        p = blank_post(raw.get("platform", "linkedin"), raw.get("date", ""))
        p.update(raw)
        p.setdefault("status", "draft")
        tag = f"[{i}] {p.get('date')} {p.get('platform')} {p.get('voice')} {p.get('format')}: {p.get('title','')[:60]}"
        errs = check_schema(p, i)
        issues = lint_post(p)
        e = [x for x in issues if x["severity"] == "error" and x["field"] != "images"]
        w = [x for x in issues if x["severity"] == "warn" and x["field"] != "images"]
        if errs or e or w:
            print(tag)
            for x in errs:
                print("   SCHEMA:", x)
            for x in e:
                print("   ERROR:", x["field"], "-", x["message"])
            for x in w:
                print("   warn:", x["field"], "-", x["message"])
        if errs or e:
            bad += 1
            continue
        if do_import:
            if p.get("status") in ("idea", None):
                p["status"] = "draft"
            saved = save_post(p)
            if do_render and (p.get("creative") or {}).get("slides"):
                from core.render import render_post
                files = render_post(saved, folder_of(saved))
                saved["images"] = files
                if saved["status"] == "draft":
                    saved["status"] = "designed"
                save_post(saved)
    print(f"\n{len(posts)} posts checked, {bad} with blocking problems.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
