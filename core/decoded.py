"""Decoded by Galvor — the newsletter format, exactly as Issues #3 and #4 were sent.

Writers work in "Decoded markup" (plain text, Markdown-like); render() turns it into the exact email HTML
(inline styles, Georgia, cream #FFFDF8, burgundy #7A1F1F links/bullets, 600px table layout, images embedded).
import_html() does the reverse, so the real issues round-trip (tools/test_decoded.py proves it).

Markup
------
---
issue: 5
title: Decoded #5: Beyond Narratives and Categories            (the H1, exactly as shown)
html_title: Decoded #5: ...                                      (optional <title>; defaults to title)
dek: One-paragraph italic standfirst.
author: Raj Dhakad, Founding AI Engineer, Galvor AI
previous_title: Fake Followers: 0%. Why Your Creator Still Won't Sell
previous_url: https://galvor.ai/newsletters/decode/...
---
## Key takeaways          → the boxed takeaways (use "- " bullets, 3 of them)
## Monday, 9:40 a.m.      → any other "## " is a section heading
Paragraph text with [links](https://...) and **bold**.
> A pull line              → italic 19px line
>> "A quoted line"         → quote block with the burgundy bar (consecutive >> lines = one block)
caption: Source line        → small italic caption (after a figure or quote block)
![Alt text for the chart](fig_01.png)   → full-width figure (file from the post's images/ folder)
### 1 Numbered subhead     → bold subhead with a burgundy number ("### Subhead" without a number = plain)
- **Lead.** bullet text      → burgundy-bullet list
[box] Box title  … [/box]   → black-outlined box (paragraphs, **bold line**, [stat] inside)
[stat] 63 | Before -> 92 | Two months after the changes   → before/after number pair
## Next issue: Title       → double rule + teaser paragraph
## CTA: Box title          → dashed burgundy box; body paragraph(s); "button: Label | https://url"
## Explainer: Heading      → smaller H2 + "**Term.** definition {#anchor}" paragraphs
## How we did this         → small-print method paragraphs
## Sources                 → "- " lines, small print; "Previously in Decoded" is added automatically
[DATA NEEDED: what's missing]  → shows in red in the preview and blocks export until replaced
"""
from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

F = "font-family:Georgia,'Times New Roman',serif;"
LINK = 'style="color:#7A1F1F;text-decoration:underline;"'
TABLE = 'role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"'
P16 = f"margin:0 0 16px 0;{F}font-size:16px;line-height:1.5;color:#222222;"
P13 = f"margin:0 0 6px 0;{F}font-size:13px;line-height:1.5;color:#5E5A52;"
CAP = f"margin:0 0 16px 0;{F}font-size:12px;line-height:1.5;color:#5E5A52;font-style:italic;"
BULLET_TD = f'<td width="18" valign="top" style="width:18px;{F}font-size:16px;line-height:1.5;font-weight:700;color:#7A1F1F;">&#8226;</td>'
BULLET_TXT = f'<td valign="top" style="padding:0 0 8px 0;{F}font-size:16px;line-height:1.5;color:#222222;">'
STRONG = '<strong style="font-weight:700;color:#000000;">'
DOUBLE_RULE_TOP = '<div style="margin:16px 0 26px 0;border-top:3px double #000000;font-size:0;line-height:0;">&nbsp;</div>'
DOUBLE_RULE_END = '<div style="margin:30px 0 0 0;border-top:3px double #000000;font-size:0;line-height:0;">&nbsp;</div>'
BOX_OPEN = f'<table {TABLE} style="border-collapse:collapse;margin:30px 0 0 0;border:1px solid #000000;"><tr><td style="padding:18px 18px 8px 18px;">'
BOX_TITLE = f"margin:0 0 10px 0;{F}font-size:17px;line-height:1.5;color:#000000;font-weight:700;"

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#FFFDF8;color:#222222;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#FFFDF8" style="border-collapse:collapse;background-color:#FFFDF8;font-family:Georgia,'Times New Roman',serif;color:#222222;">
<tr><td align="center" style="padding:20px 8px;">
<table role="presentation" align="center" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#FFFDF8" style="border-collapse:collapse;width:100%;max-width:600px;margin:0 auto;background-color:#FFFDF8;">
<tr><td style="padding:30px 22px 24px 22px;">
"""
TAIL = """</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
SPECIAL = ("key takeaways", "next issue:", "cta:", "explainer:", "how we did this", "sources")


class DecodedError(Exception):
    pass


# ---------------------------------------------------------------- text helpers
def _ent(s: str) -> str:
    """Non-ASCII → decimal entities, exactly like the sent issues (&#8217; &#183; &#8377; …)."""
    return s.encode("ascii", "xmlcharrefreplace").decode("ascii")


def smart(s: str) -> str:
    """Straight quotes typed by a writer → typographic ones (no-op on text that's already curly)."""
    s = re.sub(r"(?<=\w)'(?=\w)", "’", s)              # don't, Galvor's
    s = re.sub(r"(?<=\w)'(?=[\s.,;:!?)]|$)", "’", s)    # creators'
    s = re.sub(r"'(?=\w)", "‘", s)
    s = re.sub(r'"(?=[\w\[(‘])', "“", s)
    s = s.replace('"', "”")
    return s


def inline(text: str, strong: str = STRONG) -> str:
    """[text](url), **bold**, escaping, entities."""
    out, pos = [], 0
    pat = re.compile(r"\[([^\]]+)\]\(((?:https?://|mailto:|#)[^)\s]+)\)|\*\*(.+?)\*\*|(\[DATA NEEDED[^\]]*\])")
    for m in pat.finditer(text):
        out.append(html.escape(smart(text[pos:m.start()]), quote=False))
        if m.group(1):
            out.append(f'<a href="{html.escape(m.group(2), quote=True)}" {LINK}>{inline(m.group(1), strong)}</a>')
        elif m.group(3):
            out.append(f"{strong}{inline(m.group(3), strong)}</strong>")
        else:
            out.append(f'<span style="background:#FDECEA;color:#B42318;font-weight:700;">{html.escape(m.group(4))}</span>')
        pos = m.end()
    out.append(html.escape(smart(text[pos:]), quote=False))
    return "".join(out)


def _bullets(items: list[str]) -> str:
    rows = "".join(f"<tr>{BULLET_TD}{BULLET_TXT}{inline(t)}</td></tr>" for t in items)
    return f'<table {TABLE} style="border-collapse:collapse;margin:0 0 16px 0;">{rows}</table>'


def _figure(alt: str, src: str, images: Path | None, embed: bool) -> str:
    url = src
    if embed and images is not None and not src.startswith(("http://", "https://", "data:")):
        f = images / src
        if not f.exists():
            raise DecodedError(f"Figure image not found: {src} (put it in the post's images folder)")
        mime = mimetypes.guess_type(f.name)[0] or "image/png"
        url = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    elif not embed and images is not None and not src.startswith(("http", "data:")):
        url = src   # preview resolves relative to /media/<pid>/
    return (f'<table {TABLE} style="border-collapse:collapse;margin:8px 0 10px 0;border-top:1px solid #000000;'
            f'border-bottom:1px solid #000000;"><tr><td style="padding:16px 0 14px 0;"><img src="{url}" width="556" '
            f'alt="{html.escape(alt, quote=True)}" style="display:block;width:100%;max-width:556px;height:auto;border:0;'
            f'outline:none;text-decoration:none;"></td></tr></table><div style="height:10px;font-size:0;line-height:0;">&nbsp;</div>')


def _stat(line: str) -> str:
    m = re.match(r"\[stat\]\s*(.+?)\s*\|\s*(.+?)\s*->\s*(.+?)\s*\|\s*(.+)$", line)
    if not m:
        raise DecodedError(f"Bad [stat] line: {line}")
    a, al, b, bl = m.groups()
    num = f"{F}font-size:40px;line-height:44px;font-weight:700;color:"
    lab = f'<div style="{F}font-size:13px;line-height:18px;color:#6B6960;">'
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 14px 0;">'
            f'<tr><td style="padding:0 14px 0 0;vertical-align:top;"><div style="{num}#8C897F;">{inline(a)}</div>{lab}{inline(al)}</div></td>'
            f'<td style="padding:0 14px 0 0;vertical-align:top;{F}font-size:28px;line-height:44px;color:#7A1F1F;">&#8594;</td>'
            f'<td style="padding:0;vertical-align:top;"><div style="{num}#3F74CF;">{inline(b)}</div>{lab}{inline(bl)}</div></td></tr></table>')


# ---------------------------------------------------------------- parse
def parse(markup: str) -> tuple[dict, list[tuple[str, list[str]]]]:
    """→ (front matter, [(heading, lines)]). The first chunk (heading '') is anything before the first ##."""
    text = markup.replace("\r\n", "\n").strip("\n")
    meta = {}
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        text = text[m.end():]
    sections, cur, lines = [], "", []
    for line in text.split("\n"):
        if line.startswith("## "):
            sections.append((cur, lines))
            cur, lines = line[3:].strip(), []
        else:
            lines.append(line)
    sections.append((cur, lines))
    return meta, [s for s in sections if s[0] or any(x.strip() for x in s[1])]


def _paras(lines: list[str]) -> list[str]:
    """Group lines into blocks: blank lines separate paragraphs; special lines stand alone."""
    blocks, buf = [], []

    def flush():
        if buf:
            blocks.append(" ".join(x.strip() for x in buf))
            buf.clear()
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            flush()
            continue
        if re.match(r"^(\s*[-*] |>>? |### |!\[|caption:|button:|\[box\]|\[/box\]|\[stat\])", s.strip()):
            flush()
            blocks.append(s.strip())
        else:
            buf.append(s)
    flush()
    return blocks


def _body(blocks: list[str], images, embed) -> list[str]:
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        if b.startswith(("- ", "* ")):
            items = []
            while i < len(blocks) and blocks[i].startswith(("- ", "* ")):
                items.append(blocks[i][2:].strip())
                i += 1
            out.append(_bullets(items))
            continue
        if b.startswith(">> "):
            qs = []
            while i < len(blocks) and blocks[i].startswith(">> "):
                qs.append(f'<p style="margin:0 0 10px 0;{F}font-size:16px;line-height:1.5;color:#222222;">{inline(blocks[i][3:].strip())}</p>')
                i += 1
            html_q = (f'<table {TABLE} style="border-collapse:collapse;margin:6px 0 10px 0;"><tr><td width="4" bgcolor="#7A1F1F" '
                      f'style="width:4px;background-color:#7A1F1F;"></td><td style="padding:6px 0 4px 16px;">{"".join(qs)}</td></tr></table>')
            if i < len(blocks) and blocks[i].startswith("caption:"):
                html_q += f'<p style="{CAP}">{inline(blocks[i][8:].strip())}</p>'
                i += 1
            out.append(html_q)
            continue
        if b.startswith("> "):
            out.append(f'<p style="margin:4px 0 20px 0;{F}font-size:19px;line-height:1.5;color:#000000;font-style:italic;">{inline(b[2:].strip())}</p>')
        elif b.startswith("### "):
            t = b[4:].strip()
            m = re.match(r"^(\d+)\s+(.+)$", t)
            inner = f'<span style="color:#7A1F1F;">{m.group(1)}</span>&nbsp;&nbsp;{inline(m.group(2))}' if m else inline(t)
            out.append(f'<p style="margin:26px 0 8px 0;{F}font-size:17px;line-height:1.4;font-weight:700;color:#000000;">{inner}</p>')
        elif b.startswith("!["):
            m = re.match(r"!\[(.*)\]\((.+)\)$", b)
            if not m:
                raise DecodedError(f"Bad figure line: {b[:60]}")
            out.append(_figure(m.group(1), m.group(2).strip(), images, embed))
        elif b.startswith("caption:"):
            out.append(f'<p style="{CAP}">{inline(b[8:].strip())}</p>')
        elif b.startswith("[box]"):
            title = b[5:].strip()
            inner, i = [], i + 1
            while i < len(blocks) and not blocks[i].startswith("[/box]"):
                x = blocks[i]
                if x.startswith("[stat]"):
                    inner.append(_stat(x))
                elif re.fullmatch(r"\*\*.+\*\*", x):
                    inner.append(f'<p style="{P16}margin-bottom:6px;font-weight:700;">{inline(x[2:-2])}</p>')
                else:
                    inner.append(f'<p style="{P16}margin-bottom:12px;">{inline(x)}</p>')
                i += 1
            out.append(BOX_OPEN + f'<p style="{BOX_TITLE}">{inline(title)}</p>' + "".join(inner) + "</td></tr></table>")
        elif b.startswith("[stat]"):
            out.append(_stat(b))
        else:
            out.append(f'<p style="{P16}">{inline(b)}</p>')
        i += 1
    return out


def render(markup: str, images: Path | None = None, embed: bool = True) -> str:
    meta, sections = parse(markup)
    for k in ("issue", "title", "author"):
        if not meta.get(k):
            raise DecodedError(f"Front matter needs '{k}:'")
    n = meta["issue"]
    prev_n = meta.get("previous_issue") or (str(int(n) - 1) if str(n).isdigit() else "")
    out = []
    out.append(f'<div style="{F}font-size:40px;line-height:44px;font-style:italic;color:#000000;letter-spacing:-1px;text-align:center;">Decoded</div>')
    out.append(f'<div style="{F}font-size:14px;line-height:22px;color:#3A3732;padding-top:4px;text-align:center;">by Galvor AI &#183; Issue #{n}</div>')
    if meta.get("previous_title"):
        out.append(f'<div style="{F}font-size:13px;line-height:20px;color:#5E5A52;padding-top:6px;text-align:center;">Missed Issue #{prev_n}? '
                   f'<a href="{html.escape(meta.get("previous_url", ""), quote=True)}" {LINK}>{inline(meta["previous_title"])}</a></div>')
    out.append(DOUBLE_RULE_TOP)
    out.append(f'<h1 style="margin:0;{F}font-size:26px;line-height:1.2;font-weight:700;letter-spacing:-0.3px;color:#000000;">{inline(meta["title"])}</h1>')
    if meta.get("dek"):
        out.append(f'<p style="margin:14px 0 0 0;{F}font-size:17px;line-height:1.5;color:#3A3732;font-style:italic;">{inline(meta["dek"])}</p>')
    out.append(f'<p style="margin:14px 0 0 0;{F}font-size:14px;line-height:1.5;color:#5E5A52;">By {inline(meta["author"])} &#183; Decoded by Galvor, Issue #{n}</p>')
    tail_sources = []
    for head, lines in sections:
        blocks = _paras(lines)
        low = head.lower()
        if not head:
            out += _body(blocks, images, embed)
        elif low == "key takeaways":
            items = [b[2:].strip() for b in blocks if b.startswith(("- ", "* "))]
            out.append(BOX_OPEN + f'<p style="{BOX_TITLE}">Key takeaways</p>' + _bullets(items) + "</td></tr></table>")
        elif low.startswith("next issue:"):
            out.append(DOUBLE_RULE_END)
            out.append(f'<h2 style="margin:18px 0 14px 0;{F}font-size:20px;line-height:1.3;font-weight:700;color:#000000;">{inline(head)}</h2>')
            for b in blocks:
                out.append(f'<p style="{P16}margin-bottom:24px;">{inline(b)}</p>')
        elif low.startswith("cta:"):
            title = head[4:].strip()
            btn = next((b for b in blocks if b.startswith("button:")), None)
            body = [b for b in blocks if not b.startswith("button:")]
            ps = "".join(f'<p style="margin:0;{F}font-size:16px;line-height:1.5;color:#222222;">{inline(b)}</p>' for b in body)
            bt = ""
            if btn:
                label, _, url = btn[7:].partition("|")
                bt = (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:16px 0 0 0;">'
                      f'<tr><td align="center" bgcolor="#000000" style="background-color:#000000;"><a href="{html.escape(url.strip(), quote=True)}" '
                      f'style="display:inline-block;padding:14px 26px;{F}font-size:16px;line-height:20px;font-weight:700;color:#FFFFFF;'
                      f'text-decoration:none;">{inline(label.strip())}</a></td></tr></table>')
            out.append(f'<table {TABLE} style="border-collapse:collapse;margin:0;border:2px dashed #7A1F1F;"><tr><td style="padding:22px 20px;">'
                       f'<p style="margin:0 0 8px 0;{F}font-size:20px;line-height:1.3;font-weight:700;color:#000000;">{inline(title)}</p>{ps}{bt}</td></tr></table>')
        elif low.startswith("explainer:"):
            out.append(f'<h2 style="margin:30px 0 12px 0;{F}font-size:18px;line-height:1.3;font-weight:700;color:#000000;">{inline(head[10:].strip())}</h2>')
            for b in blocks:
                m = re.search(r"\s*\{#([\w-]+)\}\s*$", b)
                pid = f' id="{m.group(1)}"' if m else ""
                b = b[:m.start()] if m else b
                out.append(f'<p{pid} style="margin:0 0 12px 0;{F}font-size:15px;line-height:1.5;color:#222222;">{inline(b, "<strong>")}</p>')
        elif low == "how we did this":
            out.append(f'<p style="margin:28px 0 8px 0;{F}font-size:13px;line-height:1.5;color:#3A3732;font-weight:700;">How we did this</p>')
            out += [f'<p style="{P13}">{inline(b)}</p>' for b in blocks]
        elif low == "sources":
            out.append(f'<p style="margin:20px 0 8px 0;{F}font-size:13px;line-height:1.5;color:#3A3732;font-weight:700;">Sources</p>')
            tail_sources = [b[2:].strip() if b.startswith(("- ", "* ")) else b for b in blocks]
            out += [f'<p style="{P13}">{inline(b)}</p>' for b in tail_sources if not b.lower().startswith("previously in decoded")]
            if meta.get("previous_title"):
                out.append(f'<p style="{P13}">Previously in Decoded: <a href="{html.escape(meta.get("previous_url", ""), quote=True)}" {LINK}>'
                           f'Issue #{prev_n}, {inline(meta["previous_title"])}</a></p>')
        else:
            out.append(f'<h2 style="margin:30px 0 12px 0;{F}font-size:20px;line-height:1.3;font-weight:700;color:#000000;">{inline(head)}</h2>')
            out += _body(blocks, images, embed)
    title = html.escape(smart(meta.get("html_title") or meta["title"]), quote=False)
    return _ent(HEAD.format(title=title) + "\n".join(out) + "\n" + TAIL)


# ---------------------------------------------------------------- checks
def check(markup: str, images: Path | None = None, facts_text: str = "") -> list[dict]:
    """Format + honesty checks for an issue. severity: error blocks export; warn is advice."""
    from .lint import BANNED, CLIENTS
    out = []

    def add(sev, msg):
        out.append({"severity": sev, "message": msg})
    try:
        meta, sections = parse(markup)
    except Exception as e:
        return [{"severity": "error", "message": f"Can't read the issue: {e}"}]
    for k in ("issue", "title", "dek", "author", "previous_title", "previous_url"):
        if not meta.get(k):
            add("error" if k in ("issue", "title", "author") else "warn", f"Front matter is missing '{k}:'.")
    if meta.get("issue") and not str(meta.get("title", "")).startswith(f"Decoded #{meta['issue']}:"):
        add("warn", f"Title should start “Decoded #{meta.get('issue')}: …” like Issue #4.")
    heads = [h.lower() for h, _ in sections]
    kt = next((ls for h, ls in sections if h.lower() == "key takeaways"), None)
    if kt is None:
        add("error", "Missing “## Key takeaways”.")
    else:
        n = sum(1 for b in _paras(kt) if b.startswith(("- ", "* ")))
        if n != 3:
            add("warn", f"Key takeaways has {n} bullets; Decoded uses 3.")
    if not any(h.startswith("monday") or re.match(r"^\w+day, \d", h) for h in heads):
        add("warn", "No cold-open section (e.g. “## Monday, 9:40 a.m.” with Sam). Every issue opens with one.")
    if "the shift for marketers and leaders" not in heads:
        add("warn", "Missing “## The shift for marketers and leaders” (the five moves).")
    for need, label in (("next issue:", "## Next issue: …"), ("cta:", "## CTA: …"), ("how we did this", "## How we did this"), ("sources", "## Sources")):
        if not any(h.startswith(need) for h in heads):
            add("error", f"Missing “{label}”.")
    cta = next((ls for h, ls in sections if h.lower().startswith("cta:")), None)
    if cta is not None and not any(b.startswith("button:") for b in _paras(cta)):
        add("error", "CTA box needs a “button: Label | https://…” line.")
    if "DATA NEEDED" in markup:
        add("error", f"{markup.count('DATA NEEDED')} [DATA NEEDED] placeholder(s) left — fill them before sending.")
    for m in re.finditer(r"!\[(.*?)\]\((.+?)\)", markup):
        if not m.group(1).strip():
            add("error", f"Figure {m.group(2)} has no alt text (Decoded describes every chart in its alt text).")
        if images is not None and not m.group(2).startswith(("http", "data:")) and not (images / m.group(2)).exists():
            add("error", f"Figure file missing: {m.group(2)} — upload it.")
    body = re.sub(r"^---.*?---", "", markup, flags=re.S)
    low = body.lower()
    for b in BANNED:
        if b in low:
            add("error", f"Banned phrase: “{b}”.")
    for c in CLIENTS:
        if re.search(rf"\b{re.escape(c)}\b", body, re.I):
            add("warn", f"Names “{c}” — needs written client permission.")
    # every number in body copy should carry a link in the same sentence, come from the facts bank, or be Galvor's own data
    unsourced = []
    srcs_start = low.find("## how we did this")
    # numbers already backed elsewhere: chart alt text, captions, the method notes, the facts bank
    backed = " ".join(re.findall(r"!\[(.*?)\]", body)) + " ".join(re.findall(r"caption:(.*)", body)) + \
        (body[srcs_start:] if srcs_start > 0 else "") + " " + facts_text
    section = ""
    for para in re.split(r"\n\s*\n", body[:srcs_start if srcs_start > 0 else None]):
        if para.lstrip().startswith("## "):
            section = para.strip().splitlines()[0].lower()
            para = "\n".join(para.strip().splitlines()[1:])
        if re.match(r"## (monday|tuesday|wednesday|thursday|friday)", section) or "galvor" in section or "next issue" in section:
            continue                      # the cold open is a story; Galvor's own data is explained in the method notes
        if para.lstrip().startswith(("![", "caption:", "button:", "[stat]")):
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para):
            nums = re.findall(r"(?<![\w#])(\d[\d,.]*\s?%|[₹$]\s?\d[\d,.]*\s?(?:crore|lakh|bn|million|k)?|\d{2,}[\d,]*)", sent)
            nums = [x for x in nums if not re.fullmatch(r"20\d\d", x.strip())]
            if nums and "](" not in sent and "galvor" not in sent.lower() and not all(x.strip() in backed for x in nums):
                unsourced.append(nums[0].strip())
    if unsourced:
        add("warn", f"{len(unsourced)} sentence(s) with a number but no source link: {', '.join(unsourced[:6])}{'…' if len(unsourced) > 6 else ''}. "
                    "Link the source, or say it's Galvor's data.")
    words = len(re.findall(r"\w+", re.sub(r"\]\([^)]*\)", "]", body)))
    if words < 1100:
        add("warn", f"{words} words — Issues #3–#4 run about 1,900–2,500.")
    elif words > 3200:
        add("warn", f"{words} words — long for Decoded (Issues #3–#4 run about 1,900–2,500).")
    return out


def word_count(markup: str) -> int:
    body = re.sub(r"^---.*?---", "", markup, flags=re.S)
    return len(re.findall(r"\w+", re.sub(r"\]\([^)]*\)", "]", body)))


# ---------------------------------------------------------------- import (HTML → markup)
def _top_blocks(inner: str) -> list[str]:
    """Split the content cell into top-level elements (tables kept whole)."""
    out, i = [], 0
    while i < len(inner):
        if inner[i] in "\n\r ":
            i += 1
            continue
        m = re.match(r"<(table|div|h1|h2|p)\b", inner[i:])
        if not m:
            j = inner.find("<", i + 1)
            i = j if j > 0 else len(inner)
            continue
        tag = m.group(1)
        if tag == "table":
            depth, j = 0, i
            for t in re.finditer(r"<(/?)table\b", inner[i:]):
                depth += -1 if t.group(1) else 1
                if depth == 0:
                    j = i + t.end()
                    j = inner.find(">", j) + 1
                    break
            # a figure table is followed by its spacer div on the same line
            sp = re.match(r'<div style="height:10px;font-size:0;line-height:0;">&nbsp;</div>', inner[j:])
            if sp:
                j += sp.end()
            out.append(inner[i:j])
            i = j
        else:
            j = inner.find(f"</{tag}>", i) + len(tag) + 3
            out.append(inner[i:j])
            i = j
    return out


def _md(fragment: str) -> str:
    """Inline HTML → markup text."""
    s = re.sub(r'<a href="([^"]*)"[^>]*>(.*?)</a>', lambda m: f"[{_md(m.group(2))}]({html.unescape(m.group(1))})", fragment, flags=re.S)
    s = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\xa0", " ").strip()


def import_html(src: str, images_dir: Path | None = None) -> str:
    """Convert a sent Decoded HTML file into markup (+ write its embedded images as fig_NN files)."""
    t = re.search(r"<title>(.*?)</title>", src, re.S)
    start = src.find('<tr><td style="padding:30px 22px 24px 22px;">')
    end = src.rfind("</td></tr>\n</table>\n</td></tr>")
    if start < 0 or end < 0:
        raise DecodedError("This doesn't look like a Decoded issue (layout table not found).")
    blocks = _top_blocks(src[start + len('<tr><td style="padding:30px 22px 24px 22px;">'):end])
    meta, lines, fig = {}, [], 0
    mode = None
    for b in blocks:
        txt = _md(b)
        if b.startswith("<div") and "font-size:40px" in b:
            continue
        if b.startswith("<div") and "Issue #" in b and "font-size:14px" in b:
            meta["issue"] = re.search(r"Issue #(\d+)", txt).group(1)
            continue
        if b.startswith("<div") and "Missed Issue" in b:
            a = re.search(r'<a href="([^"]*)"[^>]*>(.*?)</a>', b, re.S)
            meta["previous_url"], meta["previous_title"] = html.unescape(a.group(1)), _md(a.group(2))
            continue
        if b.startswith("<div") and "border-top:3px double" in b:
            continue
        if b.startswith("<h1"):
            meta["title"] = txt
            continue
        if b.startswith("<p") and "font-size:17px" in b and "font-style:italic" in b and "dek" not in meta:
            meta["dek"] = txt
            continue
        if b.startswith("<p") and txt.startswith("By ") and "Decoded by Galvor" in txt:
            meta["author"] = re.sub(r"\s*·\s*Decoded by Galvor, Issue #\d+$", "", txt[3:])
            continue
        if b.startswith("<h2"):
            if "font-size:18px" in b:
                lines += ["", f"## Explainer: {txt}"]
            else:
                lines += ["", f"## {txt}"]
            mode = "next" if txt.lower().startswith("next issue:") else None
            continue
        if b.startswith("<table") and "Key takeaways" in b[:900]:
            lines += ["", "## Key takeaways"]
            lines += [f"- {_md(x)}" for x in re.findall(r'<td valign="top" style="padding:0 0 8px 0;[^"]*">(.*?)</td>', b, re.S)]
            continue
        if b.startswith("<table") and "dashed #7A1F1F" in b:
            title = _md(re.search(r"<p[^>]*font-size:20px[^>]*>(.*?)</p>|<p[^>]*font-size:19px[^>]*>(.*?)</p>", b, re.S).group(0))
            lines += ["", f"## CTA: {title}"]
            for p in re.findall(r'<p style="margin:0;[^"]*">(.*?)</p>', b, re.S):
                lines += ["", _md(p)]
            bt = re.search(r'<a href="([^"]*)" style="display:inline-block[^>]*>(.*?)</a>', b, re.S)
            if bt:
                lines += ["", f"button: {_md(bt.group(2))} | {html.unescape(bt.group(1))}"]
            mode = None
            continue
        if b.startswith("<table") and "<img" in b:
            fig += 1
            im = re.search(r'<img src="([^"]*)"[^>]*alt="([^"]*)"', b, re.S)
            name = im.group(1)
            dm = re.match(r"data:image/(\w+);base64,(.*)", name, re.S)
            if dm:
                ext = {"jpeg": "jpg"}.get(dm.group(1), dm.group(1))
                name = f"fig_{fig:02d}.{ext}"
                if images_dir is not None:
                    images_dir.mkdir(parents=True, exist_ok=True)
                    (images_dir / name).write_bytes(base64.b64decode(dm.group(2)))
            lines += ["", f"![{html.unescape(im.group(2))}]({name})"]
            continue
        if b.startswith("<table") and "width:4px;background-color:#7A1F1F" in b:
            lines.append("")
            lines += [f">> {_md(p)}" for p in re.findall(r"<p[^>]*>(.*?)</p>", b, re.S)]
            continue
        if b.startswith("<table") and "border:1px solid #000000" in b:
            title = _md(re.search(r"<p[^>]*>(.*?)</p>", b, re.S).group(1))
            lines += ["", f"[box] {title}"]
            rest = b[b.find("</p>") + 4:]
            for el in re.finditer(r'<p style="([^"]*)">(.*?)</p>|(<table role="presentation" cellpadding="0".*?</table>)', rest, re.S):
                if el.group(3):
                    nums = re.findall(r"font-size:40px[^>]*>(.*?)</div><div[^>]*>(.*?)</div>", el.group(3), re.S)
                    lines += ["", f"[stat] {_md(nums[0][0])} | {_md(nums[0][1])} -> {_md(nums[1][0])} | {_md(nums[1][1])}"]
                elif "font-weight:700" in el.group(1):
                    lines += ["", f"**{_md(el.group(2))}**"]
                else:
                    lines += ["", _md(el.group(2))]
            lines += ["", "[/box]"]
            continue
        if b.startswith("<table") and "&#8226;" in b:
            lines.append("")
            lines += [f"- {_md(x)}" for x in re.findall(r'<td valign="top" style="padding:0 0 8px 0;[^"]*">(.*?)</td>', b, re.S)]
            continue
        if b.startswith("<p"):
            st = re.match(r'<p(?: id="([\w-]+)")? style="([^"]*)"', b)
            pid, style = st.group(1), st.group(2)
            inner = re.search(r"<p[^>]*>(.*)</p>", b, re.S).group(1)
            if "font-size:19px" in style and "italic" in style:
                lines += ["", f"> {txt}"]
            elif "font-size:17px" in style and "margin:26px" in style:
                m = re.match(r'<span style="color:#7A1F1F;">(\d+)</span>&nbsp;&nbsp;(.*)', inner, re.S)
                lines += ["", f"### {m.group(1)} {_md(m.group(2))}" if m else f"### {txt}"]
            elif "font-size:12px" in style:
                lines.append(f"caption: {txt}")
            elif "font-size:15px" in style:
                lines += ["", txt + (f" {{#{pid}}}" if pid else "")]
            elif "font-size:13px" in style and "font-weight:700" in style:
                lines += ["", f"## {txt}"]
            elif "font-size:13px" in style:
                if txt.startswith("Previously in Decoded:"):
                    continue
                prev = next((l for l in reversed(lines) if l.startswith("## ")), "")
                lines += [("- " if prev == "## Sources" else "") + txt] if prev == "## Sources" else ["", txt]
            else:
                lines += ["", txt]
            continue
    fm = ["---", f"issue: {meta.get('issue', '')}", f"title: {meta.get('title', '')}"]
    if t and html.unescape(t.group(1)).strip() != meta.get("title"):
        fm.append(f"html_title: {html.unescape(t.group(1)).strip()}")
    fm += [f"dek: {meta.get('dek', '')}", f"author: {meta.get('author', '')}",
           f"previous_title: {meta.get('previous_title', '')}", f"previous_url: {meta.get('previous_url', '')}", "---"]
    body = "\n".join(lines).strip("\n")
    body = re.sub(r"\n{3,}", "\n\n", body)
    return "\n".join(fm) + "\n" + body + "\n"


def outline(markup: str) -> list[str]:
    _, sections = parse(markup)
    return [h for h, _ in sections if h]
