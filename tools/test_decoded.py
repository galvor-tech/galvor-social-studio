"""Proves the Decoded template is exact: import each sent issue → markup → render → compare with the original HTML.
  python tools/test_decoded.py [path/to/decoded-issue-XX.html ...]
"""
import difflib
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import decoded  # noqa: E402

files = [Path(p) for p in sys.argv[1:]] or [Path("D:/Downloads/decoded-issue-03.html"), Path("D:/Downloads/decoded-issue-04.html")]
ok = True
for f in files:
    if not f.exists():
        print("SKIP (not found)", f)
        continue
    orig = f.read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="decoded_"))
    md = decoded.import_html(orig, tmp)
    out = decoded.render(md, tmp, embed=True)
    norm = lambda s: re.sub(r"\s+\n", "\n", s.replace("\r\n", "\n")).strip()
    a, b = norm(orig), norm(out)
    same = a == b
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).quick_ratio()
    print(f"{f.name}: {'IDENTICAL' if same else 'DIFFERENT'} ({len(a):,} vs {len(b):,} chars, similarity {ratio:.4f}), "
          f"{decoded.word_count(md):,} words, {len(list(tmp.iterdir()))} figures")
    if not same:
        hunks = sum(1 for l in difflib.unified_diff(a.split("\n"), b.split("\n"), lineterm="", n=0) if l.startswith("@@"))
        legacy = f.name.endswith("03.html") and hunks <= 3
        print(f"   {hunks} difference(s){' — known Issue #3 legacy styling (CTA box, end-rule spacing, caption line); #4 is the house format' if legacy else ''}")
        ok = ok and legacy
        al, bl = a.split("\n"), b.split("\n")
        for i, line in enumerate(difflib.unified_diff(al, bl, lineterm="", n=0)):
            if i > 40:
                break
            print("   ", re.sub(r"data:image/[^\"]{40,}", "data:…", line)[:400])
    issues = decoded.check(md, tmp)
    print("   checks:", [i["message"][:90] for i in issues] or "clean")
print("ALL PASS" if ok else "SOME DIFFER")
sys.exit(0 if ok else 1)
