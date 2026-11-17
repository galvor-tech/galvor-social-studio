"""Cloud Run entry point (cms.galvor.ai).

The studio keeps all state as files under data/, content/, content_archive/, queue/, exports/ and logs/.
On Cloud Run those live in a GCS bucket mounted at STATE_DIR; this links each folder there, then starts
the scheduler and waitress on $PORT. Sign-in is handled by IAP in front of the service.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = Path(os.getenv("STATE_DIR", "/state"))

for name in ("data", "content", "content_archive", "queue", "exports", "logs"):
    target = STATE / name
    target.mkdir(parents=True, exist_ok=True)
    link = ROOT / name
    if link.is_symlink() or not link.exists():
        if link.is_symlink():
            link.unlink()
        link.symlink_to(target, target_is_directory=True)

sys.path.insert(0, str(ROOT))
import app as studio  # noqa: E402
from waitress import serve  # noqa: E402

studio.scheduler.start()
serve(studio.app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), threads=8)
