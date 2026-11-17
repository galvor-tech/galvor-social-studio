"""Writing prompts for scripts and for video generation, plus each person's voice notes.

The three prompts were written on 16 Nov 2026 from five videos Suyash shared (see References → "Five videos on
LinkedIn growth and script writing"). They are defaults: edits made on the Prompts page are saved to
data/prompts.json and used instead. Voice notes and sample posts live in data/voices.json (Voices page).
"""
from __future__ import annotations

import json

from .config import DATA, ROOT, VOICES

PROMPTS_FILE = DATA / "prompts.json"
VOICES_FILE = DATA / "voices.json"
QUEUE = ROOT / "queue" / "media"

DEFAULTS = {
    "linkedin": {
        "label": "LinkedIn post script",
        "used": "Every LinkedIn draft and rewrite written in the Studio.",
        "text": """HOW TO WRITE THIS LINKEDIN POST

Work in this order. Do not skip steps.

1. Pick the one reader. Name the person (for example: a D2C growth lead who approves 30 ads a month) and the one
   thing they will know or do after reading. One post, one argument.

2. Check it is worth saying. List the 3 to 5 points you could make. For each, ask: has this reader already heard
   it ten times? If the points only repeat common advice, stop and return a note in "notes" saying what real
   observation, number or story is missing. A post beats expectations only when it says something the reader
   has not already read.

3. Write the body first, the hook last. Write the story, the numbers and the takeaway. Then read it back, find
   the sharpest line already in it, and move that line to the top. If no line is worth moving, the post is the
   problem, not the hook.

4. The first two lines.
   Line 1: a plain, specific claim or observation, 12 words or fewer. No question, no "Excited to share".
   Line 2: a re-hook that sharpens or complicates line 1, so the reader has to tap "see more".
   Use one of four shapes and say which in "notes":
   - dense: one line packed with a number and a named situation
   - punchy plus context: a short claim, then one line of who or when
   - single-line bomb: one flat statement that most of the industry would dispute
   - stacked: two or three short lines that build to the claim

5. The first 50 words must say what the post is about and who it is for, in the reader's own words. No slow
   set-up, no scene-setting that could open any post.

6. Join a conversation that is already happening when one honestly fits. Options: a move by a known brand, news
   from this week, a person this audience already follows, a belief we hold that the industry disputes, or a
   post format that is spreading right now. Use public facts only. Never state or guess anyone's spend,
   revenue or ROAS.

7. Give the post one job, matching the slot's "job" field:
   Attract = reach new people; Educate = show how we think or work; De-risk = answer a doubt a buyer has;
   Convert = tell a ready reader the next step. Do not mix jobs.

8. Body. Go deep on how, not just what. Prefer "when I", "what we saw", "how we did it" with real detail over
   advice in the abstract. Short paragraphs for a phone screen. Vary sentence length; do not write every
   sentence the same size. Every line should earn the next.

9. Close on a high note: one line that restates the takeaway in fresh words.

10. Call to action. Keep it to one, and tie it to this post's topic: the matching Decoded issue, a checklist, or
    the page that goes deeper. Links go in the first comment. The closing ask is always to follow Galvor,
    never a person.

Do not write: generic leadership or remote-work bait, invented transformations, borrowed stories, "X is dead"
unless we really hold that view, engagement bait ("comment YES"), or lines that only repeat the post back.
Do not ask anyone to like or comment in a group to push reach.""",
    },
    "reel": {
        "label": "Reel and video script",
        "used": "Every reel or video script written in the Studio (Script tab → Write script).",
        "text": """HOW TO WRITE THIS REEL OR VIDEO SCRIPT

The viewer keeps watching only while what they get is better than what they expected. Every choice below serves
that.

Work in this order.

1. Packaging first. Before any script line, fix:
   - the idea in one sentence: the pain this solves for one viewer
   - the on-screen title: the words on the first frame (7 words or fewer)
   - the expectation that title sets. The script must meet it in the first line and then beat it.
   Put these in "setup".

2. Outline before script. List the points. Keep only points that are new to this viewer: a finding of ours, a
   number, an unusual example, or a clearer way to say a known thing. If nothing is new, return no scenes and
   say in "notes" what is missing.

3. The opening (first 3 to 6 seconds), four beats in this order:
   a. Context: say bluntly what this video is about. It must match the on-screen title word for word in meaning.
   b. The common belief: say what most people in this job believe about it.
   c. The turn: say what we found instead. This is the gap that holds attention.
   d. Proof and plan: why we can say this (what we looked at, how many), and what the viewer will get
      ("three checks", "one test").
   In a reel under 30 seconds, a and b can share one line and d can be five words.

4. The body.
   - Order the points: second-best first, best second, then the rest. The viewer should feel the value rising.
   - Give each point three parts: what it is in one plain line; how to do it or an example; why it matters here.
   - Between points, add a re-hook line that makes the next point necessary ("that only works if...").
   - One idea per scene. A scene is 2 to 5 seconds. Each scene needs a voiceover line and an on-screen line of
     6 words or fewer. On-screen text repeats the key words of the voiceover; it never adds a second idea.

5. The ending. One line that sums up what the viewer now knows, said in fresh words, so the last second feels
   like a reward. Then the call to action: follow Galvor (@galvor.ai). For newsletter reels the line is
   "Read the full newsletter on our website, link in bio".

6. If a free resource fits one of the points, mention it inside that point as the answer to the problem, in one
   line. Do not bolt it on as an advert.

Length: reels 20 to 45 seconds, about 2.3 spoken words a second. Write for the ear: short words, no brackets,
numbers said the way a person says them.

In "visual" for each scene, describe what is on screen in plain words (the ad, the chart, the phone, the text
move). Do not write camera jargon. In "notes", list every number used and where it comes from.""",
    },
    "video": {
        "label": "Video generation brief (Claude terminal)",
        "used": "Written into the media queue when you choose a reel script. The terminal reads it and renders the video.",
        "text": """VIDEO GENERATION BRIEF

Make this video from the approved script below. Do not change the words of the script. If a line cannot be
shown well, stop and say so; do not rewrite it.

Build it with the galvor-motion-video skill.

1. First frame. The on-screen title is readable within the first half second and says the same thing as the
   first spoken line. No logo sting, no fade from black, no "hi".

2. Pace. Something on screen changes every 2 to 3 seconds: a new line, a move, a cut or a chart step. At each
   re-hook line in the script, reset the screen (new layout or colour block) so the viewer feels a new part
   begin.

3. One idea per scene. Show the on-screen line from the script, large enough to read on a phone at arm's
   length. Key words land on the spoken word, using the word timings.

4. Numbers. Every number in the voiceover appears on screen as it is spoken, and counts or draws in. Charts
   start from zero and show only what the line says.

5. Rising value. Give the best point (the second in the script) the strongest visual treatment.

6. Images. Make new images for this video's idea. No client names, logos or products. People and settings
   should look international unless the script says otherwise. Any text in the picture is added by the video
   code, not by the image model.

7. Sound. Voice first; music low under it. The chime plays only on the end card.

8. End card. Galvor mark, the closing line from the script, "Follow @galvor.ai". Hold for 2 seconds.

9. Captions on for the whole video. Brand: violet #7A36EB, gold #FFC43D, dark #0A0A14, Plus Jakarta Sans.

10. Output two sizes: 1080x1920 (Reels) and 1080x1350 (LinkedIn). Save both into the post's images folder,
    then log what the render cost:  py -3.15 tools/log_cost.py gemini "video render <post id>" <usd>

Check before handing back: watch the first 3 seconds with the sound off (is it clear what this is about?), then
the whole video with sound on (does any on-screen line lag the voice?).""",
    },
}

VOICE_DEFAULTS = {
    "sunil": {"tone": "Calm, senior, plain. Talks about money, risk and teams the way a founder talks to another founder. "
                      "Tells what he heard in a real room. Few adjectives.",
              "do": "Start from a conversation or decision. One number at most. End on a view, not a tip list.",
              "dont": "No engineering detail, no hype words, no lists of features."},
    "raj": {"tone": "Curious builder. Shows the working: what the ads and numbers said, what broke, what he changed.",
            "do": "Name the test, the sample and the result. Admit what did not work. Use 'I' and 'we built'.",
            "dont": "No sweeping claims from a small sample. No sales language."},
    "shrutik": {"tone": "Practical and warm. Speaks from the day-to-day of briefs, creators, approvals and deadlines.",
                "do": "Tell one real situation from start to finish. Give the step someone can copy tomorrow.",
                "dont": "No client names or numbers. No theory without a story."},
    "company": {"tone": "Clear and factual. The Galvor page shows proof, product and data.",
                "do": "Lead with the finding. Say how we know. Link to the longer piece in the first comment.",
                "dont": "No first-person stories that belong to a person. No slogans in place of facts."},
}


# ---------------------------------------------------------------- prompts
def prompts() -> dict:
    out = {k: dict(v) for k, v in DEFAULTS.items()}
    try:
        saved = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
        for k, t in saved.items():
            if k in out and isinstance(t, str) and t.strip():
                out[k]["text"] = t
                out[k]["edited"] = True
    except (OSError, json.JSONDecodeError):
        pass
    return out


def prompt(key: str) -> str:
    return prompts()[key]["text"]


def save_prompts(data: dict) -> None:
    keep = {k: v.strip() for k, v in data.items() if k in DEFAULTS and v.strip() and v.strip() != DEFAULTS[k]["text"].strip()}
    PROMPTS_FILE.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- voices
def voices() -> dict:
    try:
        saved = json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    out = {}
    for k, v in VOICES.items():
        d = {**VOICE_DEFAULTS.get(k, {}), **(saved.get(k) or {})}
        d.setdefault("samples", [])
        out[k] = {**v, **d, "key": k}
    return out


def save_voice(key: str, data: dict) -> None:
    if key not in VOICES:
        return
    try:
        saved = json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    cur = saved.get(key) or {}
    for f in ("tone", "do", "dont"):
        if f in data:
            cur[f] = (data[f] or "").strip()
    if "samples" in data:
        cur["samples"] = [s.strip() for s in data["samples"] if s and s.strip()][:15]
    saved[key] = cur
    VOICES_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")


def voice_block(key: str) -> str:
    """What the writer is told about the person whose name goes on the post."""
    v = voices().get(key or "company") or voices()["company"]
    lines = [f"VOICE: {v['name']} ({v['role']}). Lens: {v['lens']}",
             f"Tone: {v.get('tone', '')}", f"Do: {v.get('do', '')}", f"Do not: {v.get('dont', '')}"]
    samples = v.get("samples") or []
    if samples:
        lines.append("Posts this person really wrote. Match the rhythm, word choice and length. Do not reuse their content:")
        for s in samples[:4]:
            lines.append("---\n" + s[:1800])
        lines.append("---")
    else:
        lines.append("(No real posts from this person are saved yet, so keep the voice plain and do not imitate a style.)")
    return "\n".join(lines)


# ---------------------------------------------------------------- script decision → media queue
def media_brief(p: dict) -> str:
    """The file the Claude terminal reads to make media for a post whose script has been chosen."""
    is_video = p.get("format") in ("reel", "video")
    head = [f"# Media brief: {p.get('title') or p.get('hook')}", "",
            f"- Post id: {p.get('id')}", f"- Platform: {p.get('platform')}  ·  Format: {p.get('format')}",
            f"- Goes out: {p.get('date')} {p.get('time')} IST  ·  Voice: {p.get('voice')}",
            f"- Script chosen by: {(p.get('script_decision') or {}).get('by', '')} on {(p.get('script_decision') or {}).get('at', '')[:10]}",
            f"- Save media into: {p.get('_folder', '')}\\images", ""]
    if is_video:
        sc = p.get("script") or {}
        body = [prompt("video"), "", "## Approved script", "", f"Duration: {sc.get('duration', '')}", f"Setup: {sc.get('setup', '')}", ""]
        for i, s in enumerate(sc.get("scenes") or [], 1):
            body += [f"### Scene {i} ({s.get('time', '')})", f"- Voiceover: {s.get('voiceover', '')}",
                     f"- On screen: {s.get('on_screen', '')}", f"- Visual: {s.get('visual', '')}", ""]
        body += [f"Music: {sc.get('music', '')}", f"Notes: {sc.get('notes', '')}", "", "## Caption (for reference)", "", p.get("caption") or ""]
    else:
        slides = (p.get("creative") or {}).get("slides") or []
        body = ["## What to make", "",
                "Make the images for this post from the approved words below. Do not change the words.",
                "Follow the creatives workflow: 5 distinct concepts and a contact sheet for a single image; for a "
                "carousel, one cover in 5 concepts, then the inner slides in the chosen style. New imagery made for "
                "this idea. Text is laid out in HTML, not by the image model. Sizes: 1080x1350.", "",
                "## Approved words", "", f"Hook: {p.get('hook', '')}", "", "Caption:", p.get("caption") or "", ""]
        for i, sl in enumerate(slides, 1):
            body.append(f"Slide {i}: " + json.dumps({k: v for k, v in sl.items() if k not in ("bg", "image")}, ensure_ascii=False))
    return "\n".join(head + body) + "\n"


def queue_media(p: dict) -> str:
    QUEUE.mkdir(parents=True, exist_ok=True)
    f = QUEUE / f"{p.get('date')}_{p.get('id')}.md"
    f.write_text(media_brief(p), encoding="utf-8")
    return str(f)


def unqueue_media(p: dict) -> None:
    f = QUEUE / f"{p.get('date')}_{p.get('id')}.md"
    if f.exists():
        f.unlink()


def queued() -> list[dict]:
    if not QUEUE.exists():
        return []
    return [{"file": f.name, "path": str(f)} for f in sorted(QUEUE.glob("*.md"))]
