"""This week (24-27 Nov) and next (30 Nov-4 Dec), asked 23 Nov 2026.

- 24 Nov: LinkedIn has only Raj's post (the look-alike post moves here from Thu 26 Nov).
- 25 Nov: LinkedIn has only Sunil's post (his 24 Nov poll moves here). Raj's 25 Nov carousel moves to Thu 26 16:00.
- 26-27 Nov: as per the calendar.
- LinkedIn: more carousel / image / video, fewer text-only posts (scripts and slide text only, no media made).
- Instagram: reels Mon / Wed / Fri 19:00, an image or carousel Tue / Thu 13:00. Stories stay as extras.
- The calendar is built only to Fri 4 Dec. Later LinkedIn and Instagram posts go to content_archive
  (Decoded issues stay, they have their own fortnightly schedule). Next weeks are planned with "Plan for next week".

py -3.15 tools/week_2026-11-24.py [--apply]
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.lint import lint_post                      # noqa: E402
from core.store import all_posts, folder_of, save_post   # noqa: E402

TAG = "[Week plan 23 Nov 2026] "
LAST_DAY = "2026-12-04"


def pick(posts, plat, date, time=None, voice=None, fmt=None):
    hits = [p for p in posts if p["platform"] == plat and p["date"] == date and (time is None or p["time"] == time)
            and (voice is None or p.get("voice") == voice) and (fmt is None or p.get("format") == fmt)
            and p.get("series") != "Page repost"]
    if len(hits) != 1:
        raise SystemExit(f"{plat} {date} {time} {voice} {fmt}: {[h['id'] for h in hits]}")
    return dict(hits[0])


def reel(duration, setup, scenes, cover, sub=""):
    return ({"duration": duration, "setup": setup,
             "scenes": [{"time": t, "visual": v, "voiceover": vo, "on_screen": os_} for t, v, vo, os_ in scenes]},
            {"size": "story", "slides": [{"layout": "cover", "headline": cover, "sub": sub},
                                         {"layout": "cta", "headline": "Follow *@galvor.ai*", "sub": "New reels every Mon, Wed and Fri.",
                                          "actions": ["Follow @galvor.ai"]}]})


def main():
    apply = "--apply" in sys.argv
    posts = all_posts()
    saves, archive = [], []

    # ------------------------------------------------------------------ LinkedIn, this week
    raj = pick(posts, "linkedin", "2026-11-26", "16:00", "raj")
    raj.update(date="2026-11-24", time="12:30", format="carousel", alt_text=(
        "Six slides. 1: Six look-alikes in three days, 48% less spend each. 2: 36% less first-month spend for new ads "
        "that looked like running ads, held in 4 of 5 months. 3: 48% less each when six or more look-alikes went live "
        "within three days. 4: near-copies split one budget, our guess. 5: the 20-minute thumbnail test. 6: Follow Galvor."))
    raj["creative"] = {"size": "feed", "slides": [
        {"layout": "cover", "kicker": "Sale-week launches", "headline": "Six look-alikes in three days. *48% less* spend each.",
         "sub": "What we saw in new video ads, May to Sep 2026."},
        {"layout": "stat", "kicker": "Finding 1", "stat": "36%", "headline": "less first-month spend for new ads that *looked like* ones already running",
         "sub": "Held in 4 of the 5 months.", "source": "Source: Galvor analysis · new video ads launched May–Sep 2026"},
        {"layout": "stat", "kicker": "Finding 2", "stat": "48%", "headline": "less each when *six or more* look-alikes went live within three days",
         "source": "Source: Galvor analysis · new video ads launched May–Sep 2026"},
        {"layout": "text", "kicker": "My best guess", "headline": "Near-copies *split one budget*",
         "body": "Meta seems to treat them as roughly one ad.\n\nWe measured the result, not the reason. You still pay to make all six."},
        {"layout": "list", "kicker": "Before Friday", "headline": "The *thumbnail test*, about 20 minutes", "items": [
            "Lay every planned ad out as thumbnails", "Group the ones a stranger would call the same ad",
            "Keep the best from each group, hold the rest", "Put the saved time into one ad that looks different"]},
        {"layout": "cta", "headline": "Fewer near-copies. *More real tests.*", "sub": "Full method in Decoded #3 on galvor.ai.",
         "actions": ["Follow Galvor", "Read Decoded #3"]}]}
    raj["notes"] += "\n" + TAG + "Moved to Tue 24 Nov (Raj is the only LinkedIn post that day) and made a carousel. Caption unchanged."
    saves.append(raj)

    poll = pick(posts, "linkedin", "2026-11-24", "09:00", "sunil")
    poll["date"] = "2026-11-25"
    poll["notes"] = (poll.get("notes") or "") + "\n" + TAG + "Moved from Tue 24 to Wed 25 Nov (Sunil is the only LinkedIn post that day)."
    saves.append(poll)

    tired = pick(posts, "linkedin", "2026-11-25", "12:30", "raj")
    tired.update(date="2026-11-26", time="16:00")
    tired["notes"] = (tired.get("notes") or "") + "\n" + TAG + "Moved from Wed 25 to Thu 26 Nov 16:00 so 24 and 25 Nov have one LinkedIn post each."
    saves.append(tired)

    archive.append(pick(posts, "linkedin", "2026-11-24", "12:30", "company"))     # Guru Nanak greeting: 24 Nov is Raj only

    bf = pick(posts, "linkedin", "2026-11-26", "09:00", "sunil")
    bf.update(format="image", alt_text="Quote card: Dashboards describe yesterday. Monday needs a decision. One question for Monday's agenda.")
    bf["creative"] = {"size": "feed", "slides": [
        {"layout": "statement", "kicker": "Black Friday eve", "headline": "Dashboards describe yesterday. *Monday needs a decision.*",
         "sub": "One question for Monday's agenda: what did this weekend teach us that we'll use in the next brief?"}]}
    bf["notes"] = (bf.get("notes") or "") + "\n" + TAG + "Text post made an image post (one quote card). Caption unchanged."
    saves.append(bf)

    sh = pick(posts, "linkedin", "2026-11-27", "09:00", "shrutik")
    sh.update(format="video")
    sh["script"] = {"duration": "45s", "setup": "Shrutik to camera at a desk, phone in hand with a WhatsApp chat open. One take, light cuts. A short on-screen line for each step.",
                    "scenes": [{"time": t, "visual": v, "voiceover": vo, "on_screen": o} for t, v, vo, o in [
        ("0–4s", "Shrutik to camera, holding the phone up.", "It's Black Friday, and a brand just changed the offer on a video we've already shot.", "The offer changed after the shoot"),
        ("4–9s", "Puts the phone down.", "I don't send the creator a one-line WhatsApp anymore. I treat it like a new brief.", "Treat it as a new brief"),
        ("9–16s", "Typing one line in a notes app.", "First I write what changed in one line, and get the brand to reply: yes, that's it.", "1. One line. Brand says yes."),
        ("16–24s", "Close-up of a list: supers, captions, voiceover, end card, thumbnail.", "Then I list everything it touches. Supers, captions, voiceover, end card, thumbnail.", "2. List every asset it touches"),
        ("24–31s", "Two columns on paper: edit / reshoot.", "Two piles. What the edit can fix, and what needs the creator again.", "3. Edit fix or reshoot?"),
        ("31–39s", "Back to camera.", "New due date before I ask for the change. And I ask who approves it, because that's exactly when a new reviewer shows up.", "4. New date  5. Who approves?"),
        ("39–45s", "Shrutik to camera.", "It takes an hour. It saves the round where the old offer sneaks back into the final cut.", "Follow Galvor"),
    ]]}
    sh["notes"] = (sh.get("notes") or "") + "\n" + TAG + "Text post made a talking-head video (script only, nothing filmed). Caption unchanged."
    saves.append(sh)

    # ------------------------------------------------------------------ LinkedIn, next week
    s30 = pick(posts, "linkedin", "2026-11-30", "09:00", "sunil")
    s30.update(format="video")
    s30["script"] = {"duration": "55s", "setup": "Sunil to camera, seated, plain background. One take with two or three cuts. Short on-screen lines.",
                     "scenes": [{"time": t, "visual": v, "voiceover": vo, "on_screen": o} for t, v, vo, o in [
        ("0–5s", "Sunil to camera.", "A marketer in the Gulf told us how creator videos really get made there.", "Who writes the creator's hook?"),
        ("5–11s", "Same, slight push in.", "The brand writes the first three seconds. The creator reads them out.", "The brand writes it. The creator reads it."),
        ("11–19s", "Sunil to camera.", "She wasn't complaining. Creators don't always know what to say about a phone or a blender, so the brand team writes the hook.", ""),
        ("19–25s", "Cut, closer.", "Fine. But then we're paying creator rates for a voiceover.", "Creator rates. Voiceover work."),
        ("25–34s", "Sunil to camera.", "And when the scripts come from a template or a generic AI tool, they all sound the same. Viewers can hear that.", "Template scripts all sound the same"),
        ("34–47s", "Sunil to camera.", "What works better is a bit boring. Watch 20 of the creator's own videos first. Write the hook the way they already open. Keep the must-says to one or two lines.", "Watch 20 of their videos first"),
        ("47–55s", "Sunil to camera.", "The brand still owns the message. The creator still sounds like themselves.", "Follow Galvor"),
    ]]}
    s30["notes"] += "\n" + TAG + "Made a talking-head video (script only). Caption unchanged."
    saves.append(s30)

    sh3 = pick(posts, "linkedin", "2026-12-03", "09:00", "shrutik")
    sh3.update(format="carousel", alt_text="Four slides: reach became views; before vs now; what I do with clients now; Follow Galvor for New on Instagram every Thursday.")
    slides_ig = [
        {"layout": "cover", "kicker": "New on Instagram", "headline": "Reach became *views*. Your creator benchmarks broke.",
         "sub": "What changed, and what I do with clients now."},
        {"layout": "compare", "kicker": "Same creator", "headline": "Same creator, *different ruler*", "left_title": "Before",
         "left": ["Judged on reach", "One number per post"], "right_title": "Now",
         "right": ["Views and viewers", "Views count every play, viewers are people"]},
        {"layout": "list", "kicker": "What I do now", "headline": "Three changes I've made", "items": [
            "Reset benchmarks from posts after the change", "Ask creators for viewers, not only views",
            "Say so when comparing with last year"]},
    ]
    sh3["creative"] = {"size": "feed", "slides": slides_ig + [
        {"layout": "cta", "headline": "New on Instagram, *every Thursday*", "sub": "Only what matters if you work with creators.", "actions": ["Follow Galvor"]}]}
    sh3["notes"] += "\n" + TAG + "Made a carousel. Caption unchanged."
    saves.append(sh3)

    r3 = pick(posts, "linkedin", "2026-12-03", "16:00", "raj")
    r3.update(format="image", alt_text="Quote card: Ask your creator tool when its data was last pulled.")
    r3["creative"] = {"size": "feed", "slides": [
        {"layout": "statement", "kicker": "Creator data", "headline": "Ask your creator tool *when its data was last pulled.*",
         "sub": "Most store a snapshot. An audience can change a lot in six months."}]}
    r3["notes"] += "\n" + TAG + "Made an image post (one card). Caption unchanged."
    saves.append(r3)

    # ------------------------------------------------------------------ Instagram: reels Mon/Wed/Fri 19:00, image/carousel Tue/Thu 13:00
    gn = pick(posts, "instagram", "2026-11-24", "11:00", "company", "image")
    gn["time"] = "13:00"; gn["notes"] = (gn.get("notes") or "") + "\n" + TAG + "Tuesday image post at 13:00."
    saves.append(gn)

    c27 = pick(posts, "instagram", "2026-11-27", "13:00", "company", "carousel")
    c27["script"], c27["creative"] = reel("28s", "Phone screen recording of an ad about to be published, then quick text cards for each check. Fast cuts.", [
        ("0–3s", "Finger hovering over Publish on a sale ad.", "Before your Black Friday ad goes live, seven checks.", "7 checks before you publish"),
        ("3–9s", "Ad frame with the offer, muted icon, end date.", "Is the offer in the first frame? Does it read with the sound off? Is the end date on screen and in the caption?", "Offer first. Sound off. End date."),
        ("9–15s", "Ad next to its landing page, same price circled.", "Does the page show the same price? Is the product in the ad actually in stock?", "Same price. In stock."),
        ("15–22s", "A grid of ads, one highlighted as different. A note: 'we expect…'", "Does each ad have one clear difference from the rest? And did you write down what you expect before launch?", "One difference. One prediction."),
        ("22–28s", "All seven checks on one card.", "Two minutes per ad. Save this for every sale.", "Save this. Follow @galvor.ai"),
    ], "*7 checks* before your sale ads go live", "Two minutes per ad.")
    c27.update(format="reel", time="19:00", alt_text="Reel: seven checks before Black Friday ads go live.")
    c27["notes"] = (c27.get("notes") or "") + "\n" + TAG + "Friday is a reel day: carousel turned into a 28s reel script (same seven checks). Caption unchanged."
    saves.append(c27)

    c30 = pick(posts, "instagram", "2026-11-30", "19:00", "company", "carousel")
    c30["script"], c30["creative"] = reel("33s", "Talking head or voiceover over a leaderboard of sale ads being sorted into three piles.", [
        ("0–4s", "A sale leaderboard, all ads green.", "The sale flatters every ad. Before you copy this weekend's winners, sort them.", "Sale winners can lie"),
        ("4–10s", "A big '-40%' sticker covers an average-looking ad.", "With a big discount on screen, even weak ads sell. Brief January off that list and you might be copying the discount.", "You might be copying the discount"),
        ("10–18s", "Ads slide into three piles.", "Three piles. Won before and during the sale. Won only during it. Lost even with the discount.", "3 piles"),
        ("18–26s", "Each pile gets a label.", "The first pile is your creative. The second is your offer. The third tells you what to leave out.", "Creative. Offer. Leave out."),
        ("26–33s", "The three labels on one card.", "Do it this week, while you still remember the details.", "Save this. Follow @galvor.ai"),
    ], "The sale flatters every ad. *Sort them.*", "Three piles, this week.")
    c30.update(format="reel", alt_text="Reel: sort sale ads into three piles before briefing January.")
    c30["notes"] = (c30.get("notes") or "") + "\n" + TAG + "Monday is a reel day: carousel turned into a 33s reel script. Caption unchanged."
    saves.append(c30)

    mh = pick(posts, "instagram", "2026-12-01", "12:30", "company", "image")
    mh["time"] = "13:00"; mh["notes"] = (mh.get("notes") or "") + "\n" + TAG + "Tuesday image post at 13:00."
    saves.append(mh)

    ig3 = pick(posts, "instagram", "2026-12-03", "13:00", "company", "carousel")
    ig3.update(status="draft", title="New on Instagram: reach became views",
               hook="Reach became views. Your creator benchmarks broke.",
               caption=("Instagram stopped reporting reach the old way, and a lot of creator benchmarks broke quietly.\n\n"
                        "A creator who used to show 300K reach doesn't show 300K viewers now. Views count every play, viewers are people. Neither is the old reach number.\n\n"
                        "So reset your benchmarks from posts made after the change, ask creators for viewers, and say so when you compare with last year.\n\n"
                        "Save this for your next creator report.\n\nFollow @galvor.ai for what's new on Instagram every Thursday."),
               alt_text="Four slides: reach became views; before vs now; three changes; follow @galvor.ai.")
    ig3["creative"] = {"size": "feed", "slides": slides_ig + [
        {"layout": "cta", "headline": "New on Instagram, *every Thursday*", "sub": "Save this for your next creator report.", "actions": ["Follow @galvor.ai"]}]}
    ig3["notes"] += "\n" + TAG + "Written from Shrutik's LinkedIn post the same morning. Confirm the views/viewers wording against Instagram's Insights help page."
    saves.append(ig3)

    c4 = pick(posts, "instagram", "2026-12-04", "13:00", "company", "carousel")
    c4["script"], c4["creative"] = reel("35s", "Voiceover over a simple card being filled in, one line per decision.", [
        ("0–4s", "A blank 'pre-launch card'.", "The best time to decide when to cut an ad is before it goes live.", "Decide before launch"),
        ("4–10s", "Two people pointing at the same chart, disagreeing.", "After launch, everyone reads the numbers their own way and the review turns into a debate.", "Or the review becomes a debate"),
        ("10–18s", "Card lines fill in.", "So agree five things first. What it's testing. What it's compared with.", "1. Testing what  2. Against what"),
        ("18–25s", "Next lines fill in.", "The one number that judges it. How long before anyone judges.", "3. Judged on  4. Judged after"),
        ("25–31s", "Last line fills in.", "And what happens if it wins, or loses.", "5. Then what"),
        ("31–35s", "The filled card.", "Rules first. Results second.", "Follow @galvor.ai"),
    ], "*5 decisions* before a campaign goes live", "Made after launch, they turn into arguments.")
    c4.update(format="reel", time="19:00", alt_text="Reel: five decisions to agree before a campaign goes live.")
    c4["notes"] = (c4.get("notes") or "") + "\n" + TAG + "Friday is a reel day: carousel turned into a 35s reel script. Caption unchanged."
    saves.append(c4)

    # ------------------------------------------------------------------ archive everything after 4 Dec (not Decoded)
    for p in posts:
        if p["date"] > LAST_DAY and p["platform"] in ("linkedin", "instagram"):
            archive.append(p)

    # ------------------------------------------------------------------ checks
    bad = 0
    for p in saves:
        for i in lint_post(p):
            if i["severity"] == "error" and i["field"] != "images":
                print("LINT", p["date"], p["platform"], p["title"][:40], i["message"]); bad += 1
    week = {}
    for p in [q for q in posts if q["id"] not in {s["id"] for s in saves} | {a["id"] for a in archive}] + saves:
        if "2026-11-24" <= p["date"] <= LAST_DAY:
            week.setdefault(p["date"], []).append(p)
    for d in sorted(week):
        for p in sorted(week[d], key=lambda q: (q["platform"], q["time"])):
            print(d, p["time"], p["platform"][:2], (p.get("voice") or "")[:7].ljust(7), p["format"].ljust(8), p["title"][:55])
    print(f"\nsave {len(saves)}  archive {len(archive)}  problems {bad}")
    if not apply:
        print("dry run"); return
    if bad:
        raise SystemExit("fix problems first")
    for p in archive:
        src = folder_of(p); dst = ROOT / "content_archive" / src.relative_to(ROOT / "content")
        if dst.exists():
            dst = dst.with_name(dst.name + "_wk2026-11-23")
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst))
    for p in saves:
        save_post({k: v for k, v in p.items() if k != "_folder"}, note=TAG.strip())
    print("applied")


if __name__ == "__main__":
    main()
