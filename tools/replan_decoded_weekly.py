"""Decoded goes weekly (every Wednesday 08:30 IST, from the Galvor LinkedIn page + email). One-off re-plan, 11 Nov 2026.

  python tools/replan_decoded_weekly.py           # dry run
  python tools/replan_decoded_weekly.py --apply

- Imports the sent issues #3 (4 Nov) and #4 (11 Nov) from D:/Downloads into the studio in Decoded markup.
- Renumbers and redates the planned issues onto Wednesdays; converts their drafts to Decoded markup.
- Adds skeleton issues for the new Wednesdays (#7, #8, #10) — ideas to write, not finished copy.
- Chains every issue: "Missed Issue #N?" + "Next issue:" + "Previously in Decoded".
- Skips the Galvor-page "Decoded promo" posts (the newsletter is itself a Galvor-page post on the same day)
  and moves the Instagram "Decoded is out" stories to the issue's day with the right issue number.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import decoded  # noqa: E402
from core.store import all_posts, blank_post, folder_of, save_post, slugify  # noqa: E402

APPLY = "--apply" in sys.argv
AUTHOR = "Raj Dhakad, Founding AI Engineer, Galvor AI"
BASE = "https://galvor.ai/newsletters/decode/"
CTA = {
    "audit": ("Get a free five-layer audit from Galvor AI",
              "We read every ad in your account for look, speaker, audience, stage and reason, score each layer, and send you the "
              "short list of new ads that would fill the gaps. [Talk to the founders](https://talk.galvor.ai) to book yours.",
              "Get a free audit | https://talk.galvor.ai"),
}

# old issue number in the studio → (new number, Wednesday, exact H1 title, short title for links)
REMAP = {
    4: (5, "2026-11-18", "Decoded #5: Beyond Narratives and Categories: How Galvor Uncovers the Psychology Driving Your Brand",
        "Beyond Narratives and Categories: How Galvor Uncovers the Psychology Driving Your Brand"),
    5: (6, "2026-11-25", "Decoded #6: Creative Fatigue: When to Refresh, When to Cut", "Creative Fatigue: When to Refresh, When to Cut"),
    6: (9, "2026-12-16", "Decoded #9: What a Year of Ads Taught Us: 2026 in Creative", "What a Year of Ads Taught Us: 2026 in Creative"),
    7: (11, "2026-12-30", "Decoded #11: Build a Test Calendar, Not a Content Calendar", "Build a Test Calendar, Not a Content Calendar"),
    8: (12, "2027-01-06", "Decoded #12: The Learning Loop: How to Run a Fortnightly Creative Cycle", "The Learning Loop: How to Run a Fortnightly Creative Cycle"),
    9: (13, "2027-01-13", "Decoded #13: Budget Season: Making the Case for Creative Spend to Finance", "Budget Season: Making the Case for Creative Spend to Finance"),
}
NEW = {   # new Wednesdays → skeleton issues (ideas; the team writes them)
    7: ("2026-12-02", "Decoded #7: The Sale Is Over. What Did Your Ads Learn?", "The Sale Is Over. What Did Your Ads Learn?",
        "Black Friday and Cyber Monday produced the most data your ads will see all year. Most of it will be forgotten by January. "
        "Here is how to turn one sale into a brief for the next one.",
        ["The biggest sale weekend teaches the least, because demand flatters every ad.",
         "Separate what the offer did from what the creative did before you rebrief.",
         "Write down three findings now; by the next sale the numbers will still be there, the reasons won't."],
        ["Monday, 9:40 a.m.", "Why a sale teaches less than it seems", "What Galvor saw in the data", "Offer, creative or demand?",
         "The shift for marketers and leaders"]),
    8: ("2026-12-09", "Decoded #8: Agents, Not Headcount: What an AI Co-worker Should Decide", "Agents, Not Headcount: What an AI Co-worker Should Decide",
        "Marketing teams are asking for more people to move information around. Agents are good at exactly that. Here is where an AI "
        "co-worker helps, where it shouldn't decide, and how Vira shows its thinking.",
        ["Most of a marketing team's week goes into moving information, not deciding.",
         "Let agents prepare the decision; keep the judgement with people who own the result.",
         "An AI co-worker you can't question is a black box with a login."],
        ["Monday, 9:40 a.m.", "Where the week actually goes", "What should never be automated", "How Vira shows its thinking",
         "The shift for marketers and leaders"]),
    10: ("2026-12-23", "Decoded #10: The Year in Ten Lessons", "The Year in Ten Lessons",
         "A short one for the holiday week: the ten ideas from this year of Decoded that held up, in one page you can forward to "
         "the person planning January.",
         ["Ten lessons from this year's issues, one paragraph each.",
          "What we got wrong, and what changed our mind.",
          "One question to ask your ads before the year ends."],
         ["Monday, 9:40 a.m.", "Ten lessons that held up", "What we got wrong", "The shift for marketers and leaders"]),
}


def url_for_title(short: str) -> str:
    return BASE + slugify(short, 90) + "/"


def md_from_draft(draft: str, issue: int, title: str, prev: tuple[str, str], nxt: tuple[str, str], data_needed: list[str]) -> str:
    """Studio draft markdown (old shape) → Decoded markup."""
    lines = draft.replace("\r\n", "\n").split("\n")
    body, dek, started = [], "", False
    for ln in lines:
        s = ln.strip()
        if not started:
            if s.startswith("*") and s.endswith("*") and not s.startswith("**") and len(s) > 40 and not dek:
                dek = s.strip("*").strip()
            if s.lower().startswith(("### key takeaways", "## key takeaways")):
                started = True
                body.append("## Key takeaways")
            continue
        if s == "---":
            continue
        if s.lower().startswith("**next issue"):
            break
        m = re.match(r"^\*\*(\d+)\s+(.+?)\*\*$", s)
        if m:
            body += ["", f"### {m.group(1)} {m.group(2)}"]
            continue
        if re.fullmatch(r"\*[^*].+[^*]\*", s):
            body += ["", f"> {s.strip('*').strip()}"]
            continue
        if s.startswith("### "):
            body += ["", "## " + s[4:]]
            continue
        body.append(ln.rstrip())
    fm = ["---", f"issue: {issue}", f"title: {title}", f"dek: {dek or '[DATA NEEDED: one-paragraph standfirst]'}", f"author: {AUTHOR}",
          f"previous_title: {prev[0]}", f"previous_url: {prev[1]}", "---"]
    tail = ["", f"## Next issue: {nxt[0]}", "", nxt[1] or "[DATA NEEDED: two-line teaser for the next issue]",
            "", f"## CTA: {CTA['audit'][0]}", "", CTA["audit"][1], "", "button: " + CTA["audit"][2],
            "", "## How we did this", "",
            "Galvor’s data: [DATA NEEDED: dataset, date range, number of ads/brands, definitions]",
            "", "## Sources", ""]
    tail += [f"- [DATA NEEDED: source for “{d[:70]}”]" for d in (data_needed or [])[:3]] or ["- [DATA NEEDED: sources]"]
    text = "\n".join(fm + body).rstrip() + "\n" + "\n".join(tail) + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def md_skeleton(issue, title, dek, takeaways, sections, prev, nxt) -> str:
    out = ["---", f"issue: {issue}", f"title: {title}", f"dek: {dek}", f"author: {AUTHOR}",
           f"previous_title: {prev[0]}", f"previous_url: {prev[1]}", "---", "", "## Key takeaways", ""]
    out += [f"- {t}" for t in takeaways]
    for h in sections:
        out += ["", f"## {h}", ""]
        if h.startswith("Monday"):
            out += ["Sam, our growth lead from earlier issues, [DATA NEEDED: the cold-open scene — 3 short paragraphs].", "",
                    "> [DATA NEEDED: one-line italic turn]"]
        elif h.startswith("What Galvor saw"):
            out += ["[DATA NEEDED: what Galvor's data shows — dataset, period, the two or three numbers that matter]", "",
                    "![DATA NEEDED: describe the chart in full sentences — this alt text is what screen readers and Gmail show](fig_01.png)",
                    "caption: Source: Galvor analysis · [DATA NEEDED: period]"]
        elif h.startswith("The shift"):
            out += ["Five moves Galvor recommends, whatever tool you use.", ""]
            out += [f"- **[DATA NEEDED: move {i}].** One or two sentences." for i in range(1, 6)]
        else:
            out += ["[DATA NEEDED: section copy — link every outside number to its source like [this](https://example.com)]"]
    out += ["", f"## Next issue: {nxt[0]}", "", nxt[1] or "[DATA NEEDED: teaser]",
            "", f"## CTA: {CTA['audit'][0]}", "", CTA["audit"][1], "", "button: " + CTA["audit"][2],
            "", "## How we did this", "", "Galvor’s data: [DATA NEEDED: dataset, dates, definitions]",
            "", "## Sources", "", "- [DATA NEEDED: sources, one per line: Publisher (date), [title](url)]"]
    return "\n".join(out) + "\n"


def main():
    posts = all_posts()
    nls = {(p.get("newsletter") or {}).get("issue"): p for p in posts if p["platform"] == "newsletter"}
    # ---------- the chain of titles (issue → (short title, url, date, teaser))
    chain = {3: ("Creative Diversity: Low. Why 30 New Ads Won’t Fix It", BASE + "creative-diversity-low-why-30-new-ads-wont-fix-it/", "2026-11-04", ""),
             4: ("Fake Followers: 0%. Why Your Creator Still Won’t Sell", url_for_title("Fake Followers 0 Why Your Creator Still Wont Sell"), "2026-11-11", "")}
    for old, (new, day, title, short) in REMAP.items():
        chain[new] = (short, url_for_title(short), day, "")
    for n, (day, title, short, dek, *_r) in NEW.items():
        chain[n] = (short, url_for_title(short), day, dek)
    chain[5] = chain[5][:3] + ("Narratives and categories tell you what an ad is about. They don’t tell you why it works. Next time, we "
                               "show how Galvor decodes the buyer psychology behind a brand’s best ads, and builds hooks, scripts and campaigns on it.",)
    for k in sorted(chain):
        print(f"#{k:<3} {chain[k][2]}  {chain[k][0]}")
    if not APPLY:
        print("\n(dry run — add --apply)")
        return

    # ---------- 1. import sent issues #3 and #4
    for n, fn, status in ((3, "D:/Downloads/decoded-issue-03.html", "published"), (4, "D:/Downloads/decoded-issue-04.html", "approved")):
        src = Path(fn)
        if not src.exists():
            print("missing", fn)
            continue
        short, url, day, _ = chain[n]
        p = nls.get(n) if nls.get(n) and nls[n]["date"] == day else None
        p = p or blank_post("newsletter", day, time="08:30", voice="company", pillar="Newsletter", job="Educate", format="issue",
                            series="Decoded", title=f"Decoded #{n}: {short}", hook=short, status=status)
        p = save_post(p)
        md = decoded.import_html(src.read_text(encoding="utf-8"), folder_of(p) / "images")
        meta, _ = decoded.parse(md)
        p["newsletter"] = {"issue": n, "markup": md, "source_file": fn, "url": url,
                           "subject_lines": [short], "preview_text": meta.get("dek", "")[:140]}
        p["caption"] = p.get("caption") or (f"Decoded by Galvor, Issue #{n}: {short}\n\n{meta.get('dek', '')}\n\n"
                                             "Subscribe to get it every Wednesday.")
        p["images"] = sorted(x.name for x in (folder_of(p) / "images").glob("fig_*"))
        p["status"] = status
        if status == "published":
            p["published_url"], p["published_at"] = url, f"{day}T08:30:00"
        p["notes"] = ("Imported from the sent HTML. " + ("Confirm the live URL once it's published on galvor.ai." if n == 4 else ""))
        save_post(p, note=f"Imported Decoded #{n} from {src.name}")
        print("imported", n)

    # ---------- 2. renumber/redate planned issues; convert drafts
    for old, (new, day, title, short) in REMAP.items():
        p = nls.get(old)
        if not p or (p.get("newsletter") or {}).get("markup"):
            continue
        nl = p["newsletter"]
        nxt = chain.get(new + 1, ("", "", "", ""))
        md = md_from_draft(nl.get("draft_markdown") or "", new, title, chain[new - 1][:2], (nxt[0], nxt[3]), nl.get("data_needed"))
        nl.update(issue=new, markup=md, next_issue=nxt[0], url=chain[new][1], previous_studio_issue=old)
        p.update(date=day, time="08:30", title=title, newsletter=nl, status="draft", voice="company")
        p["notes"] = (f"Was planned as #{old} (fortnightly). Now #{new}, Wednesday {day}. Draft converted to Decoded markup — "
                      "edit it in the Decoded editor; every [DATA NEEDED] must be filled before export.\n\n" + (p.get("notes") or ""))
        save_post(p, note=f"Decoded goes weekly: #{old} → #{new} on {day}")
        print(f"renumbered #{old} → #{new} {day}")

    # ---------- 3. skeletons for the new Wednesdays
    for n, (day, title, short, dek, takeaways, sections) in NEW.items():
        if any((q.get("newsletter") or {}).get("issue") == n for q in all_posts("newsletter")):
            continue
        nxt = chain.get(n + 1, ("", "", "", ""))
        p = blank_post("newsletter", day, time="08:30", voice="company", pillar="Newsletter", job="Educate", format="issue",
                       series="Decoded", title=title, hook=short, status="idea",
                       caption=f"Decoded by Galvor, Issue #{n}: {short}\n\n{dek}\n\nSubscribe to get it every Wednesday.")
        p["newsletter"] = {"issue": n, "markup": md_skeleton(n, title, dek, takeaways, sections, chain[n - 1][:2], (nxt[0], nxt[3])),
                           "url": chain[n][1], "next_issue": nxt[0], "subject_lines": [short], "preview_text": dek[:140]}
        p["notes"] = "Skeleton for a new weekly slot. Write it by hand, or use Decoded → Draft with AI, then fill every [DATA NEEDED]."
        save_post(p, note="Created by the weekly Decoded re-plan")
        print("skeleton", n, day)

    # ---------- 4. social posts around the issues
    story_map = {"2026-11-17": ("2026-11-18", {"#4": "#5"}), "2026-12-01": ("2026-11-25", {"#5": "#6"}),
                 "2026-12-29": ("2026-12-30", {"#7": "#11"}), "2027-01-12": ("2027-01-06", {"#8": "#12"}),
                 "2027-01-26": ("2027-01-12", {"#9": "#13"})}
    for p in all_posts():
        t = (p.get("title") or "")
        if p["platform"] == "linkedin" and re.search(r"decoded (issue )?#\d+ promo", t, re.I) and p.get("status") != "published":
            p["status"] = "skipped"
            p["notes"] = "Skipped: Decoded is now posted weekly as a LinkedIn newsletter from the Galvor page on Wednesdays. " + (p.get("notes") or "")
            save_post(p, note="Skipped: replaced by the weekly LinkedIn newsletter post")
            print("skip promo", p["date"], t[:50])
        if p["platform"] == "instagram" and p.get("format") == "story" and "decoded" in t.lower() and p["date"] in story_map:
            day, rep = story_map[p["date"]]
            blob = json.dumps({k: p.get(k) for k in ("title", "hook", "caption", "creative", "alt_text")}, ensure_ascii=False)
            for a, b in rep.items():
                blob = re.sub(re.escape(a) + r"(?!\d)", b, blob).replace(f"Issue {a}", f"Issue {b}")
            p.update(json.loads(blob))
            p["date"], p["time"] = day, "12:30"
            p["images"] = []        # re-render with the new number
            save_post(p, note=f"Moved to the issue day {day} and renumbered ({rep})")
            print("story moved", day, p["title"][:50])


if __name__ == "__main__":
    main()
