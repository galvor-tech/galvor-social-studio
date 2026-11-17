"""Render every slide's HTML in headless Chrome and report any text overflow / collisions.

Usage: python tools/qa_overflow.py [platform]
"""
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.config import SIZES                     # noqa: E402
from core.render import find_browser, slide_html  # noqa: E402
from core.store import all_posts                  # noqa: E402


def check(job):
    browser, html_path, w, h = job
    with tempfile.TemporaryDirectory(prefix="gss-qa-") as prof:
        out = subprocess.run([browser, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-first-run",
                              f"--window-size={w},{h}", "--force-device-scale-factor=1", "--virtual-time-budget=4000",
                              "--dump-dom", html_path.resolve().as_uri()], capture_output=True, text=True,
                             encoding="utf-8", errors="ignore", timeout=90).stdout
    m = re.search(r'data-qa="([^"]*)"', out)
    return m.group(1) if m else "no-result"


def main():
    plat = sys.argv[1] if len(sys.argv) > 1 else None
    browser = find_browser()
    work = Path(tempfile.mkdtemp(prefix="gss-qa-html-"))
    jobs, meta = [], []
    for p in all_posts(plat):
        cr = p.get("creative") or {}
        slides = cr.get("slides") or []
        size = cr.get("size") or ("story" if p.get("format") in ("reel", "story") else "feed")
        w, h = SIZES[size]
        for i, s in enumerate(slides, 1):
            f = work / f"{len(jobs):04d}.html"
            f.write_text(slide_html(p, s, i, len(slides), size), encoding="utf-8")
            jobs.append((browser, f, w, h))
            meta.append((p["id"], i, s.get("layout")))
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(check, jobs))
    bad = [(m, r) for m, r in zip(meta, res) if r != "ok"]
    for (pid, i, lay), r in bad:
        print(f"{pid} slide {i} [{lay}]: {r}")
    print(f"\n{len(jobs)} slides checked, {len(bad)} with layout problems.")


if __name__ == "__main__":
    main()
