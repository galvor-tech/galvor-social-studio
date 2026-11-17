"""Re-render every post whose slides contain a given text (e.g. after a handle change).
  python tools/rerender_where.py "@galvor.ai"
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.render import render_post  # noqa: E402
from core.store import all_posts, folder_of, save_post  # noqa: E402

needle = sys.argv[1]
todo = [p for p in all_posts() if needle in json.dumps((p.get("creative") or {}).get("slides") or [], ensure_ascii=False)
        and p.get("images") and p.get("status") not in ("published", "skipped")]
print(len(todo), "to render", flush=True)
for i, p in enumerate(todo, 1):
    try:
        p["images"] = render_post(p, folder_of(p))
        save_post(p)
        print(i, "ok", p["id"], flush=True)
    except Exception as e:
        print(i, "FAILED", p["id"], e, flush=True)
