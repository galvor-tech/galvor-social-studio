# Calendar rewrite brief (19 Nov 2026 to 18 Feb 2027)

You are rewriting the scripts for one group of posts in Galvor's content calendar. Scripts only: words, slide
text, reel scenes, polls. Do not make, render or request any image or video. Do not start the Studio app.

Galvor (galvor.ai) sells creative marketing intelligence to D2C performance marketing teams, India first, also
US and UK. Readers are founders, CMOs, growth leads and performance marketers.

## Read these first (all inside D:\galvor_linkedin\studio)

1. `data/CONTENT_SPEC.md` — brand guide, rules, the facts bank (section 4), slide layouts (section 6), the post
   schema (section 7). Read all of it.
2. `queue/rewrite/prompts.md` — the LinkedIn post prompt, the reel script prompt, and the four voices. Follow the
   prompt for your format and the voice for your posts.
3. `queue/rewrite/<your group>.manifest.json` — your slots. Each has a date, time, format, pillar, job, series,
   festival, monthly theme and the current title and hook. `decoded_issues` lists the newsletter issue going
   out each Wednesday.
4. `data/topics.json` — the agreed topic bank (ref, voice, pillar, hook). Use it to pick or sharpen topics for
   your voice.
5. `data/competitors_research.json` → `cross_cutting`, and `data/competitor_posts.json` → `insight` — what works
   for competitors. Use as direction only.
6. One or two of the current posts in your group (find the folder under `content/` by date) to see the exact
   JSON shape of a carousel, reel, poll or story. Do not copy their wording.

## What stays fixed for each slot

id, date, time, platform, voice, format, festival. Do not change these. Keep `job` and `pillar` unless the new
topic clearly belongs to another allowed pillar (the manifest lists them).

## What you write for each slot

A new script, start to finish: `title` (internal), `hook`, `caption`, `first_comment`, `hashtags`, `alt_text`,
`cta`, `notes`, plus `creative.slides` for image, carousel and story; `script` for reel and video; `poll` for
poll. Use `null` for script and poll when not needed. For text posts use `"creative": {"size": "feed", "slides": []}`.

Topic: keep the slot's current topic when it is strong, and sharpen it. Replace it when it is generic, repeats
another slot in your group, or reads as a product pitch. No two posts in your group may make the same argument.

## Direction from a skeptical marketing head

- Competitor data from this week: how-to posts someone can copy the same day got by far the most response;
  product and feature posts got almost none. So: teach one usable thing per post. Earn any product mention.
- One post, one argument, one reader. Name the reader in your head before writing.
- The first two lines decide everything. Body first, then lift the sharpest line to the top.
- Vary the shape across your group: how-to, teardown of a public pattern, a belief we hold against the industry,
  a question worth answering, a checklist, a myth and the fact. Do not open three posts in a row the same way.
- Plain words. Short paragraphs. No "Excited to share", no "game-changer", no "unlock", no "delve", no
  "It's not X, it's Y" constructions, no rhetorical triples, no em dashes.
- Indian D2C context is welcome (festive season, Republic Day sales, year-end budgets, new financial year
  planning) when the date fits. Festival slots keep their festival and stay warm and brief.

## Truth rules (these matter most)

- Numbers: only the ones in the facts bank (section 4 of the spec), used exactly as written, with their source
  where the spec requires one. Most posts should use no number at all. Use any single statistic at most twice
  across your whole group.
- Never invent a client, a quote, a conversation, a meeting, a test result or a personal story. The people named
  on these posts are real and will be held to every sentence.
- For Sunil, Raj and Shrutik: write arguments, methods, checklists and observations that follow from Galvor's
  published work, not made-up anecdotes. If a post would be stronger with a real experience, write the post so
  it stands without one, and begin `notes` with `CONFIRM WITH <name>:` followed by what real example they could
  add or must confirm.
- Never state or guess a competitor's or any brand's spend, revenue or ROAS. Do not name competitors.
- No client names or client numbers beyond the anonymised ones in the facts bank.
- Closing ask is always to follow Galvor (LinkedIn) or @galvor.ai (Instagram), never a person. Links go in
  `first_comment`, not the caption. Where a Decoded issue matches the post's topic, point the first comment to
  that issue ("Read Decoded #N on galvor.ai") and nothing else.

## Format notes

- LinkedIn text: 120 to 220 words. Carousel: cover, 4 to 7 value slides, cta slide; caption 60 to 120 words.
  Image: one slide (statement, stat, list or compare) plus a caption of 60 to 140 words. Poll: 2 to 4 options
  and a caption that says why the question matters.
- Instagram captions: 40 to 110 words, first line is the hook. Carousel as above. Image: one slide.
  Story: 3 to 5 slides in `story` size, with one interactive ask (poll or question) described in `notes`.
- Reel and video: follow the reel prompt exactly. 20 to 45 seconds, 5 to 9 scenes, every scene has `time`,
  `visual`, `voiceover`, `on_screen` (6 words or fewer). Put the packaging (idea, on-screen title, expectation)
  in `script.setup`. Also give a cover slide in `creative.slides` (story size).
- Slide text limits are in spec section 6. Stat slides need a `source`. Highlights use balanced *asterisks*.
- `notes`: the hook shape used (LinkedIn), every number used and its source, and anything to confirm.

## How to deliver

Write `queue/rewrite/<your group>.out.json` as UTF-8:

    {"posts": [{"id": "<id from the manifest>", "title": "...", "hook": "...", "caption": "...", ...}, ...]}

Then run, from D:\galvor_linkedin\studio:

    py -3.15 tools/calendar_rewrite.py apply <your group>

It saves each post and prints `FIX` lines for quality errors and for numbers that are not in the facts bank.
Fix every one in your out file and run apply again until it prints 0 with problems and 0 not yet written.
You may write and apply in batches (apply only touches the ids in the file). A post id can change if you rename
nothing: you are not changing slugs, so ids stay the same.

Do not edit any file other than your own out file. Do not touch other groups, the app code, or media.

Final reply: how many posts you wrote, the apply tool's last line, the list of posts carrying a `CONFIRM WITH`
note, any slot whose topic you replaced (old → new), and anything you were unsure about.
