"""Renders on-brand creatives (PNG + LinkedIn carousel PDF) from post JSON using headless Chrome/Edge.

Every slide goes through creatives/creative.html, which hard-codes the Galvor logo in the
top-left corner, the violet/gold theme, fonts and footer — so the theme can't drift.
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import CREATIVES, SIZES, STATIC, VOICES, load_settings

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    custom = load_settings().get("chrome_path")
    for c in ([custom] if custom else []) + CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("Chrome or Edge not found. Set its path in Settings → Rendering.")


# ---------------------------------------------------------------- text filters
_HL = re.compile(r"\*(.+?)\*")


def _hl(text) -> Markup:
    """Escape, then turn *words* into gold highlight spans."""
    if text is None:
        return Markup("")
    t = html.escape(str(text))
    t = _HL.sub(r'<span class="hl">\1</span>', t)
    return Markup(t.replace("\n", "<br>"))


def _para(text) -> Markup:
    parts = [p.strip() for p in str(text).split("<br><br>") if p.strip()]
    return Markup("".join(f"<p style='margin-bottom:18px'>{p}</p>" for p in parts))


def _itemhl(item) -> Markup:
    """List items may be 'Title — detail' or {'title','detail'}."""
    if isinstance(item, dict):
        title, detail = item.get("title", ""), item.get("detail", "")
    else:
        s = str(item)
        title, _, detail = s.partition(" — ")
    out = _hl(title)
    if detail:
        out += Markup("<small>") + _hl(detail) + Markup("</small>")
    return out


_env = Environment(loader=FileSystemLoader(str(CREATIVES)), autoescape=select_autoescape(["html"]))
_env.filters["hl"] = _hl
_env.filters["para"] = _para
_env.filters["itemhl"] = _itemhl


def _auto_size(slide: dict, height: int) -> str:
    if slide.get("size"):
        return slide["size"]
    n = len(re.sub(r"[*\n]", "", str(slide.get("headline", ""))))
    layout = slide.get("layout")
    extra = len(slide.get("items") or []) + len(slide.get("options") or []) + len(slide.get("left") or [])
    if layout in ("list", "compare", "poll") or slide.get("body"):
        n += 35 + extra * 12
    tall = height > 1500
    if n <= 28:
        return "xl"
    if n <= 52:
        return "l" if not tall else "xl"
    if n <= 85:
        return "m" if not tall else "l"
    if n <= 130:
        return "s" if not tall else "m"
    return "xs" if not tall else "s"


def slide_html(post: dict, slide: dict, index: int, total: int, size_key: str) -> str:
    width, height = SIZES[size_key]
    voice = VOICES.get(post.get("voice") or "company", VOICES["company"])
    author = None
    if post.get("platform") == "linkedin" and post.get("voice") not in (None, "", "company"):
        author = voice
    series = post.get("series") or ""
    tpl = _env.get_template("creative.html")
    return tpl.render(
        s=slide, index=index, total=total, width=width, height=height,
        size=_auto_size(slide, height), author=author, series=series,
        hashtag=post.get("brand_hashtag") or "#KnowWhyYourAdsWin",
        logo=(STATIC / "brand" / "galvor-mark.png").as_uri(),
        fonts=(STATIC / "fonts").as_uri(), post_id=post.get("id", ""), fmt=post.get("format", ""),
    )


def _screenshot(browser: str, html_path: Path, png_path: Path, width: int, height: int) -> None:
    with tempfile.TemporaryDirectory(prefix="gss-chrome-") as profile:
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--mute-audio",
            f"--user-data-dir={profile}", "--force-device-scale-factor=1",
            f"--window-size={width},{height}", "--virtual-time-budget=4000",
            "--default-background-color=00000000",
            f"--screenshot={png_path.resolve()}", html_path.resolve().as_uri(),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=False)
    if not png_path.exists() or png_path.stat().st_size < 5000:
        raise RuntimeError(f"Render failed for {png_path.name}")


def _verify_png(path: Path, width: int, height: int) -> None:
    from PIL import Image
    with Image.open(path) as im:
        if im.size != (width, height):
            # Chrome sometimes reserves a few px; normalise to the exact target size
            im = im.convert("RGB").crop((0, 0, width, height)) if im.size[0] >= width and im.size[1] >= height \
                else im.convert("RGB").resize((width, height))
            im.save(path, optimize=True)


def render_post(post: dict, folder: Path) -> list[str]:
    """Render all slides of a post into folder/images. Returns relative file names."""
    creative = post.get("creative") or {}
    slides = creative.get("slides") or []
    if not slides:
        return []
    size_key = creative.get("size") or ("story" if post.get("format") in ("reel", "story") else "feed")
    width, height = SIZES[size_key]
    folder = Path(folder).resolve()
    img_dir = folder / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob("*"):
        old.unlink()
    browser = find_browser()
    total = len(slides)
    work = Path(tempfile.mkdtemp(prefix="gss-render-"))
    jobs = []
    for i, slide in enumerate(slides, start=1):
        h = work / f"slide_{i:02d}.html"
        h.write_text(slide_html(post, slide, i, total, size_key), encoding="utf-8")
        jobs.append((h, img_dir / f"slide_{i:02d}.png"))
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda j: _screenshot(browser, j[0], j[1], width, height), jobs))
    for _, png in jobs:
        _verify_png(png, width, height)
    shutil.rmtree(work, ignore_errors=True)

    files = [p.name for _, p in jobs]
    if post.get("platform") == "linkedin" and total > 1:
        from PIL import Image
        imgs = [Image.open(img_dir / f).convert("RGB") for f in files]
        pdf = img_dir / "carousel.pdf"
        imgs[0].save(pdf, save_all=True, append_images=imgs[1:], resolution=150)
        for im in imgs:
            im.close()
        files.append("carousel.pdf")
    return files
