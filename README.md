# Galvor Social Studio

A local content tool for Galvor's LinkedIn, Instagram and the *Decoded* newsletter, styled like the Galvor CRM.
It plans, writes, designs, checks, schedules and (optionally) publishes.

## Merged studio (11 Nov 2026): Social Studio + galvor-cms in one tool
Six screens: **Today · Discover · Ideas · Create · Calendar · Results** (+ Playbook, Settings).
Flow: Discover (daily scan, $2/day cap) → Ideas (numbers only if verbatim in the source) → Write it (AI draft in the next
free slot) → check + approval (editing approved words sends it back) → reminders → post from the phone kit → Results.

- **Posting rhythm (IST, `core/config.py` SLOTS):** LinkedIn Mon 12:30 Shrutik · Tue 09:00 Sunil · Wed 09:00 Raj ·
  Thu 09:00 + Fri 12:30 Galvor page (Fri = weekly reshare). Instagram Mon 19:00 carousel · Tue 12:30 stories ·
  Wed 19:00 reel · Fri 13:00 carousel · Sat 11:00 single. Decoded alternate Tuesdays 08:30. Festivals keep their date.
- **Reminders (`core/reminders.py`):** 30 min before, at the slot, "missed" after 2 h, reply-to-comments 30 min after
  live, 08:30 daily digest, Monday 09:00 weekly digest. In-app always; email/Chat once set up under Settings → Notifications.
  Google Calendar events (one per post to 31 Dec) are the backup that works with the laptop off.
- **Phone kit:** `/kit/<post>?k=<token>` — copy caption, save images, "I posted it". Signed per post; works over the
  tunnel (studio.galvor.ai) without sign-in; everything else stays private.
- **Results (`core/analytics.py`):** Instagram syncs daily via the Graph API once a token is in Settings; LinkedIn
  from the weekly export (drop the .xls on Results). Posts are matched to the plan and marked posted automatically.
- **Re-plan tool:** `python tools/rebuild_plan_2026.py` (dry run) / `--apply`. Tests: `tools/smoke_test.py`,
  `tools/test_reminders.py`, `tools/test_analytics.py`, `tools/test_discover.py`, `tools/test_team.py`.
- Run with Python 3.15 (`py -3.15 app.py`); `start_studio.bat` does this.

## Start it
Double-click **`start_studio.bat`** (or run `python app.py`), then open http://127.0.0.1:5055.
It runs on this laptop only. The scheduler runs while the window is open.

## What's where
| Path | What |
|---|---|
| `content/linkedin/<YYYY-MM>/<date>_<slug>/` | One folder per LinkedIn post: `post.json`, `caption.txt`, `first_comment.txt`, `script.md`, `images/` (PNGs + `carousel.pdf` for document posts) |
| `content/instagram/...` | Same structure for Instagram (`images/` 1080×1350 feed, 1080×1920 stories and reel covers) |
| `content/newsletter/...` | Decoded issues: intro, subject lines, outline, full or skeleton draft, data-needed list |
| `data/festivals.json` | Verified festival and key-dates calendar, Nov 2026 – Dec 2027, with sources and confidence |
| `data/topics.json` | The 150 hooks from the 90-day plan |
| `data/CONTENT_SPEC.md` | Brand guide and rules (also what the AI follows) |
| `data/gaps.json` | Gaps and checklist (what the plan doesn't cover, plus the LinkedIn page fixes) |
| `creatives/creative.html` | The single image template: logo top-left, violet/gold theme, fonts and footer are locked here |
| `.env` | AI keys (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`). Keep it private. |

## Daily flow
1. **Today**: post anything due (copy caption → paste → mark live), fix anything in *Needs attention*.
2. **Approvals**: send drafts for review → approve → schedule. Posts with blocking issues can't be approved.
3. **Calendar**: drag-free planning; click **+** on a day to add a post; festival chips are on every day.
4. **Auto-planner**: fill next week's empty slots from the topic bank (optionally drafted by AI).
5. **Post page**: edit copy, slides, script and poll → **Render images** → preview → the quality check runs live.

## Automation levels
- **On now:** AI drafting and rewriting, auto-planning, image rendering, quality checks, scheduling, and *Post now* reminders.
- **Needs your API access:** auto-publishing (Settings → Publishing). LinkedIn needs Community Management API
  access; Instagram needs a Business account, a Meta app token and a public https URL for images.
  Reels and videos always need a manual upload (the studio gives you the script and cover).

## Tools
- `python tools/import_batch.py <file.json> [--import] [--render]`: validate or import a batch of posts
- `python tools/smoke_test.py`: load every page and fail on any error
- `python tools/seed.py`: rebuild the gaps checklist (keeps statuses)

## Decoded (weekly, Wednesdays 08:30) — added 11 Nov 2026
Create → **Decoded newsletter**: list of issues + AI issue ideas. Each issue opens in the **Decoded editor** (markup left, live
email preview right, checks below). Export gives the exact email HTML of Issues #3–#4 (Issue #4 round-trips byte-for-byte:
`tools/test_decoded.py`). "Draft with AI" writes a full issue in the house format but may only link sources you give it;
unproven numbers come back as [DATA NEEDED] and block export. "Make promo pack" writes the LinkedIn share text, subject lines,
Raj's repost, team comment starters, an Instagram story on the day and a takeaways carousel. Re-plan scripts:
`tools/replan_decoded_weekly.py`, `tools/convert_skeleton_issues.py`.
