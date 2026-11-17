"""Make a post's video with raea (via the galvor-motion kit's raea_video.py), in the background.

Two modes:
- "motion"  : no filming. The post's script → Gemini TTS voice → Whisper word timings → kinetic type cued on each word.
- "footage" : a filmed take (uploaded). Whisper word timings → Galvor captions lit word by word, logo pill, end card.
Results land in the post's folder as video-reels.mp4 (1080x1920) and/or video-feed.mp4 (1080x1350), H.264 High + AAC,
voice at -14 LUFS, plus words.srt for the platform's own captions.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .store import folder_of, get_post, now_iso, save_post

ROOT = Path("D:/galvor_linkedin/videos/raea")
KIT = Path.home() / ".claude" / "skills" / "galvor-motion-video" / "tools"
PY = Path.home() / ".venvs" / "galvor-motion" / "Scripts" / "python.exe"
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def available() -> tuple[bool, str]:
    if not (KIT / "raea_video.py").exists():
        return False, "The galvor-motion-video kit (raea_video.py) isn't installed."
    if not PY.exists():
        return False, "The Whisper venv (~/.venvs/galvor-motion) is missing."
    if not (Path.home() / ".raea" / "bin" / "raea.exe").exists():
        return False, "raea isn't installed (irm https://raea.io/install.ps1 | iex)."
    return True, ""


def project_dir(p: dict) -> Path:
    return ROOT / (p.get("slug") or p["id"])


def shapes_for(p: dict) -> str:
    return "reels" if p["platform"] == "instagram" else "reels,feed"


def _cue(text: str) -> str:
    toks = re.findall(r"[\w’'%-]+", text)
    return " ".join(toks[:3])


def build_scenes(p: dict) -> tuple[str, dict]:
    """The post's scene table → script.txt + video.json (one scene per row, cued on its first spoken words)."""
    sc = (p.get("script") or {}).get("scenes") or []
    vo, scenes = [], []
    for i, s in enumerate(sc):
        line = (s.get("voiceover") or "").strip()
        if not line:
            continue
        # house rule: the closing ask is "Follow Galvor", never "Follow for…"
        line = re.sub(r"\bfollow for\b", "Follow Galvor for", line, flags=re.I)
        vo.append(line)
        on = (s.get("on_screen") or "").strip()
        last = i == len(sc) - 1
        if last and re.search(r"\bfollow\b", line, re.I):
            scenes.append({"cue": _cue(line), "kind": "end"})
            continue
        m = re.match(r"^([+−-]?\d+)\s?%\s*(.*)$", on.replace("−", "-"))
        if m:
            n = int(m.group(1))
            scenes.append({"cue": _cue(line), "kind": "stat", "stat": n, "suffix": "%", "prefix": "+" if n > 0 else "",
                           "label": m.group(2) or on, "tone": "high" if n > 0 else "low"})
            continue
        text = on or line.split(".")[0]
        words, lines, cur = text.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > 22 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        scenes.append({"cue": _cue(line), "kind": "statement", "lines": lines[:4]})
    if scenes and scenes[-1]["kind"] != "end":
        scenes.append({"cue": scenes[-1]["cue"], "kind": "end"})
    return " ".join(vo), {"title": p.get("title"), "audio": "vo.wav", "captions": True, "scenes": scenes}


def status(pid: str) -> dict:
    with _lock:
        j = dict(_jobs.get(pid) or {})
    if j.get("log_file"):
        try:
            j["log"] = Path(j["log_file"]).read_text(encoding="utf-8", errors="replace").splitlines()[-14:]
        except OSError:
            j["log"] = []
    return j


def start(pid: str, mode: str, footage: Path | None = None, redo_voice: bool = False) -> dict:
    ok, why = available()
    if not ok:
        raise RuntimeError(why)
    p = get_post(pid)
    if not p:
        raise RuntimeError("Post not found")
    with _lock:
        if _jobs.get(pid, {}).get("running"):
            raise RuntimeError("A video for this post is already being made.")
    proj = project_dir(p)
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "out").mkdir(exist_ok=True)
    args = [str(PY), str(KIT / "raea_video.py"), str(proj), "--shapes", shapes_for(p), "--name", "video"]
    if mode == "footage":
        if not footage:
            raise RuntimeError("Upload the filmed take first.")
        for f in ("video.json", "media/vo.wav"):
            (proj / f).unlink(missing_ok=True)
        args += ["--footage", str(footage)]
        (proj / "script.txt").unlink(missing_ok=True)
        text = " ".join((s.get("voiceover") or "") for s in ((p.get("script") or {}).get("scenes") or []))
        if text.strip():
            (proj / "script.txt").write_text(text, encoding="utf-8")   # spelling for the captions; timings come from the take
    else:
        script, video = build_scenes(p)
        if not script:
            raise RuntimeError("The post has no script with voiceover lines.")
        old = (proj / "script.txt").read_text(encoding="utf-8") if (proj / "script.txt").exists() else None
        (proj / "script.txt").write_text(script, encoding="utf-8")
        (proj / "video.json").write_text(json.dumps(video, indent=1, ensure_ascii=False), encoding="utf-8")
        if redo_voice or old != script:            # new words need a new voice
            (proj / "media" / "vo.wav").unlink(missing_ok=True)
            shutil.rmtree(proj / "audio", ignore_errors=True)
        args += ["--tts"]
    log_file = proj / "out" / "job.log"
    job = {"running": True, "mode": mode, "started": now_iso(), "log_file": str(log_file), "project": str(proj)}
    with _lock:
        _jobs[pid] = job

    def work():
        t = time.time()
        with open(log_file, "w", encoding="utf-8") as lf:
            r = subprocess.run(args, stdout=lf, stderr=subprocess.STDOUT, cwd=str(proj))
        res = {"running": False, "ok": r.returncode == 0, "secs": round(time.time() - t)}
        if r.returncode == 0:
            q = get_post(pid)
            dest = folder_of(q) / "images"
            dest.mkdir(parents=True, exist_ok=True)
            files = []
            for shape in shapes_for(q).split(","):
                src = proj / "out" / f"video-{shape}.mp4"
                if src.exists():
                    shutil.copyfile(src, dest / f"video-{shape}.mp4")
                    files.append(f"video-{shape}.mp4")
            if (proj / "words.srt").exists():
                shutil.copyfile(proj / "words.srt", dest / "video-captions.srt")
            report = (proj / "out" / "report.txt").read_text(encoding="utf-8") if (proj / "out" / "report.txt").exists() else ""
            q["video"] = {"files": files, "srt": "video-captions.srt", "mode": mode, "made_at": now_iso(), "report": report,
                          "project": str(proj)}
            save_post(q, note=f"Video made with raea ({mode}): {', '.join(files)}")
            res["files"] = files
        with _lock:
            _jobs[pid] = {**job, **res}
    threading.Thread(target=work, daemon=True, name=f"video-{pid}").start()
    return job
