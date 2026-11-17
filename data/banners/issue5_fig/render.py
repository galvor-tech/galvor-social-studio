"""Render HTML files to PNG with headless Chrome; --crop trims trailing white rows.
usage: python render.py WIDTH HEIGHT [--crop] file1.html file2.html ..."""
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageChops

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
w, h = sys.argv[1], sys.argv[2]
crop = "--crop" in sys.argv
for f in [a for a in sys.argv[3:] if a != "--crop"]:
    src = Path(f).resolve()
    out = src.with_suffix(".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=4000",
                    f"--window-size={w},{h}", f"--screenshot={out}", src.as_uri()],
                   capture_output=True, timeout=90)
    im = Image.open(out).convert("RGB")
    if crop:
        bg = Image.new("RGB", im.size, (255, 255, 255))
        box = ImageChops.difference(im, bg).getbbox()
        if box:
            im = im.crop((0, 0, im.width, box[3]))
            im.save(out)
    print(out.name, im.size)
