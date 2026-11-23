"""Calendar plan 30 Nov 2026 - 26 Feb 2027 (asked for 23 Nov 2026).

Weekly LinkedIn rhythm (IST):
  Mon 09:00 Sunil   "What I heard this week": a real client problem, nobody named
  Tue 08:30 Galvor  Decoded, fortnightly (1 Dec, 15 Dec, 29 Dec, 12 Jan, 26 Jan, 9 Feb, 23 Feb)
  Tue 12:30 Raj     Brand Breakdown carousel: one non-client brand's public Meta ads, weekly
  Wed 09:00 Sunil
  Thu 09:00 Shrutik "New on Instagram this week"
  Thu 16:00 Raj
  Fri 09:00 Sunil
  The Galvor page reposts every personal post with its own line ~4h later (Thu Raj -> Fri 16:00).
Instagram: Thursday 13:00 on @galvor.ai becomes the "New on Instagram" carousel.

Usage:  py -3.15 tools/plan_dec2026.py           # dry run: table + checks
        py -3.15 tools/plan_dec2026.py --apply   # write posts, archive the rest
"""
from __future__ import annotations

import datetime as dt
import gzip
import re
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.lint import lint_post                       # noqa: E402
from core.store import all_posts, blank_post, save_post, folder_of   # noqa: E402

START, END = "2026-11-30", "2027-02-26"
HOLIDAY_FRIDAYS = {"2026-12-25", "2027-01-01"}         # Christmas, New Year: Sunil off, page greeting runs
NOTE = "[Plan 23 Nov 2026] "
CLOSE_ALL = "Follow Galvor"

# --------------------------------------------------------------------------- Sunil, Mondays (new)
SUNIL_MON = [
 dict(title="The brand writes the hook. The creator reads it.", pillar="In the Room",
      hook="A Gulf marketer told us how creator videos get made.\nThe brand writes the hook. The creator reads it out.",
      body="""She wasn't complaining. She said that's just how it works now, for her team and for most brands she knows. Creators don't always know what to say about a phone or a blender, so someone on the brand side researches the hook, writes it, sends it over, and the creator performs it.

Fine. But then we're paying creator rates for a voiceover.

And when the scripts come from a template, or a generic AI tool, they all sound the same. Her colleague said it straight: the script doesn't match how the creator talks. Viewers can hear that.

What's worked better for us is a bit boring. Watch 20 of the creator's own videos before writing a word. Write the hook the way they already open their videos. Keep the brand's must-says to one or two lines.

The brand still owns the message. The creator still sounds like themselves.""",
      src="Gulf electronics retailer, calls 5 Aug and 6 Oct 2026 (also said of a Gulf hypermarket chain)",
      page="Sunil on why so many creator videos sound the same, and who's really writing them."),
 dict(title="'Brand fit' is a word agencies hide behind", pillar="In the Room",
      hook="\"Brand fit is a very loose word.\"\nA bank's marketing head told us that. He has a point.",
      body="""His point was simple. Every agency deck says the creators are a great brand fit. Nobody can tell him what that means, and in the end he's the one who decides anyway.

So we've stopped using the word with clients. We ask them to write fit down as things you can check instead.

Do they speak on camera, and in which language?
Is their audience 27 to 45, or mostly college kids?
Have they done a rival brand in the last six months?
Anything in their past that'll come up in the comments?

Written like that, two people can look at the same creator and agree. You can also argue with it, which is kind of the point.

If your brief just says brand fit, the agency fills in the meaning for you. Usually with whoever has the most followers.""",
      src="BFSI marketing head, calls 10 Aug and 12 Oct 2026; a hair-care brand said the same on 4 Jun",
      page="Sunil on what 'brand fit' should actually mean in a creator brief."),
 dict(title="A 250K creator now costs more than a 1M one", pillar="Marketing Money",
      hook="A 250K creator now costs more than a 1M one.\nTwo fashion brands told us this in the same month.",
      body="""One said the same creators had put their rates up by about half in two or three months. The other said smaller creators were quoting more than people with four times the followers.

At first it sounds broken. I don't think it is.

A 1M account often has a huge audience that never buys anything. The 250K creator has people who actually trust them. They know that, so they charge for it.

Rate cards are slowly moving from reach to believability. Brands still negotiating on follower count will keep overpaying for the wrong people, and losing the right ones to someone who pays properly.

Before agreeing a fee I'd look at two things. How their sponsored posts do next to their normal ones. And what the comments say when they recommend something.""",
      src="Menswear D2C (26 Aug) and an ethnic-wear retailer (13 Oct 2026); numbers are the brands' own",
      page="Sunil on why creator rate cards are moving from reach to trust."),
 dict(title="Shortlist 20, sign 10, get 5 videos", pillar="In the Room",
      hook="Shortlist 20 creators. Sign 10. Get 5 videos.\nAnd half of those 5 can't be used.",
      body="""That's not a made-up funnel. A menswear brand walked us through their last few campaigns and it went roughly like that every time.

Some creators went quiet after onboarding. A couple took three or four months to deliver. One launch slipped by a month because briefing ran late.

Everyone measures the top of that funnel. How many creators did we find, how many did we sign. Almost nobody tracks how many usable videos came out the other end, or what each usable one really cost.

Do that maths once and it changes how you shortlist. You stop picking 20 people who look good and start picking 10 who'll deliver what you asked for, on time.

Try it for one campaign. It's a bit painful, but worth it.""",
      src="Menswear D2C, call 26 Aug 2026 (their own numbers)",
      page="Sunil on the number nobody tracks in creator campaigns: usable videos."),
 dict(title="\"We're drowning in numbers. Most of them are rubbish.\"", pillar="Measurement",
      hook="\"Most of our numbers are rubbish.\"\nThat's from a marketing head at a big company. Not me.",
      body="""He said his real job is deleting numbers, not getting more of them. He wants a few that tell him a story and tell him what to do next.

We've heard some version of this from nearly every brand we showed a dashboard to this year. One asked, what do I actually tell my team on Monday? Another wanted the top 10 changes per market and nothing else.

We got this wrong for a while. Our first dashboards had too much in them, because more felt like more value.

Now the first page is a short list of things to change, each with the ad it came from. The charts are still there, just further down, for whoever wants them.

If you're planning 2027 reporting this week, try cutting the weekly report in half. See who notices.""",
      src="BFSI marketing head (10 Aug); nutrition and hair-care brands (Aug-Nov 2026)",
      page="Sunil on cutting reports down to what someone will act on."),
 dict(title="400 leads. Zero bookings.", pillar="In the Room",
      hook="400 leads. Zero bookings.\nAnd the ads weren't the problem.",
      body="""A hospitality brand told us about their last agency. Cheap leads, lots of them, not one booking. Each booking was worth a lot, so this hurt.

When we looked, the ad was fine. Everything after it wasn't.

The button sent people to an Instagram profile. There were no questions to check if someone was actually planning a trip. And replies went out hours later, because the sales team works office hours and leads don't.

So the agency was judged on cost per lead, delivered cheap leads, and technically did its job.

Before you judge an ad, follow one lead the whole way. Click it yourself, fill the form, wait for the reply. Most of the time you'll find the leak in ten minutes.""",
      src="Hospitality brand, call 14 Oct 2026; an edtech launch (11 Sep) had the same break after the form",
      page="Sunil on following one lead all the way through before blaming the ad."),
 dict(title="Your best Tamil ad is invisible", pillar="In the Room",
      hook="Your best Tamil ad is invisible.\nThe national dashboard averaged it away.",
      body="""A hair-care brand said this to us, more or less. Something works really well in Kerala and badly up north, and the overall number calls it average.

They spend a small amount in one southern state. Too small to ever show up in a national report, but a big deal for that market.

Nobody actually thinks India is one market. Yet most creative reporting still rolls everything into one table.

What's helped the brands we work with: review each region on its own. Fewer ads per region, sure, but the patterns you find are real.

And check who writes the regional brief. A lot of Tamil briefs are written in English and the creator translates on the fly. One brand told us that's exactly what they do, because nobody on the team reads Tamil.""",
      src="Hair-care D2C (18 and 27 Aug), kids' nutrition brand (15 Oct 2026)",
      page="Sunil on why regional ads need their own review, not a national average."),
 dict(title="Cheap creators, expensive ads", pillar="Marketing Money",
      hook="Cheap creators plus a big boost budget.\nFor one brand, that ended up costing more.",
      body="""An apparel brand had gone mostly nano and micro. Lower fees, more creators, more money left over for ads behind the posts. Makes sense on paper.

Once real ad money went behind those videos, the bigger creators, 50K and up, came out cheaper per result. What they saved on fees went straight back out as ad spend.

I'm not saying small creators don't work. Some kinds of video did fine at that size, testimonials for one.

But if you're paying Meta to push the video anyway, the creator fee is the small number. What matters is how the video does once you pay for reach.

So add it up properly. Fee plus boost, per result. Not just the fee.""",
      src="Fashion D2C, call 11 Nov 2026 (Galvor analysis of their creator ads)",
      page="Sunil on counting creator fee plus boost, not just the fee."),
 dict(title="\"Influencer marketing is a waste of money\"", pillar="In the Room",
      hook="\"Influencer marketing is a waste of money.\"\nA CMO who's run brands and agencies told us that.",
      body="""He's been through agency after agency. Every one promised reach. A lot of it was fake, or the right people never saw it.

Honestly, I'd say the same if that was my experience.

But what failed for him was the buying, not the channel. Creators picked on follower count, paid for organic reach that never showed up, judged on views.

The brands we see getting it right do it differently. They screen hard first, and most creators don't make it through. They pay for the content, then put ad money behind the videos that work. And they judge it on sales, like any other ad.

Done that way it's just another source of creative. A good one, usually.""",
      src="Fractional CMO/advisor, call 1 Oct 2026",
      page="Sunil takes the 'influencer marketing is a waste' argument seriously."),
 dict(title="\"Help me prove brand ads to my management\"", pillar="Measurement",
      hook="\"Help me prove brand ads to my management.\"\nThat's all a head of digital asked us for.",
      body="""Their company runs two ad teams. One for performance, one for brand. Performance has ROAS and everyone gets it. Brand has a feeling that it's helping.

They can see branded searches go up. People talk about them online. Store traffic moves. But they can't say these five customers came because of that ad, so the brand budget is always the one being questioned.

I don't have a clean answer, and I don't trust anyone who says they do. Attribution is messy and will stay messy.

What I'd do: before the campaign, write down a few things that should move if brand ads work. Branded search, direct traffic, repeat buyers. Check them after. Not perfect, but a lot better than arguing on gut feel.""",
      src="Ethnic-wear retailer's digital head, call 13 Oct 2026",
      page="Sunil on proving brand ads without pretending attribution is solved."),
 dict(title="10 videos a month for Rs 5,000", pillar="AI & the Team",
      hook="A CMO makes 10 videos a month for Rs 5,000.\nMaking content isn't the hard part anymore.",
      body="""He showed us. A promo video that used to take him a full day takes about ten minutes now.

So what's actually scarce? Knowing what to make.

A new brand we spoke to had three ads live and was copying what its competitors ran. Totally understandable. But copy the category's winners long enough and you end up sounding exactly like the category.

When anyone can make a hundred videos, the brands that win know which ten to make. That comes from your own results, not your competitors'.""",
      src="Fractional CMO (1 Oct) and an edtech launch (11 Sep 2026)",
      page="Sunil on what's scarce now that making videos is cheap."),
 dict(title="Most marketing teams are one tired person", pillar="AI & the Team",
      hook="Most brand marketing teams are one tired person.\nMost marketing tools are built for ten.",
      body="""A founder in the UK told us his marketing is the bare minimum. He's on his own, so he uses Claude for most of it. No shame in that.

A footwear brand said it from the other side. You can't expect a senior person to spend eight hours a week reading data.

When we started, we built for a big team with an analyst. Most of the brands we work with don't have one.

So now the first question we ask is: what's the one problem you'd fix this month if you could? We start there, and only there.

If you're that one person, don't try to fix everything at once. Pick one thing.""",
      src="UK food brand founder (21 Oct), footwear D2C (26 Aug 2026)",
      page="Sunil on building for the one-person marketing team."),
 dict(title="Lead count looked fine for eight months", pillar="In the Room",
      hook="Lead count looked fine for eight months.\nLead quality didn't.",
      body="""A founder told us he'd handed his ads to an outside campaign manager. He checked the top number every week. Leads were coming in, so it all seemed fine.

Junk leads were creeping up the whole time. By the time he noticed, the account he'd built over years was a mess.

Nobody lied to him. He was just watching the number that's easiest to show.

If someone else runs your ads, ask them for one number that's hard to make look good. For him it should have been leads that turned into a real conversation.""",
      src="Education brand founder, call 29 Oct 2026",
      page="Sunil on the number to ask for when someone else runs your ads."),
]

# --------------------------------------------------------------------------- Raj, Thursdays (new ones)
RAJ_NEW = {
 "2026-12-03": dict(title="Creator tools say 'verified'. Their users don't believe it.", pillar="Creators & Testing",
      hook="Creator tools say the data is verified.\nThe marketers using them don't believe it.",
      body="""A marketer in the Gulf told us most influencer marketers there use the same creator database. She does too. But the stats keep changing, so after checking the tool she messages the creator to confirm their audience anyway. And after all that, she's still not sure the followers are real.

What I think is going on: most of these tools store a snapshot of each creator and refresh it now and then. An audience can change a lot in six months.

Another brand told us their agency's numbers never matched the live profile. Same reason, older snapshot.

We search live for each brief instead, and read the creator's recent reels and comments. It's slower and costs more per search. But the numbers are from this week.

If your tool can't tell you when its data was last pulled, ask.""",
      src="Gulf electronics retailer (5 Aug 2026); a brand quoted on a US call (18 Aug)",
      page="Raj on why creator databases go stale, and what to ask your tool."),
 "2026-12-10": dict(title="Plan on the sponsored number, not the average", pillar="Creators & Testing",
      hook="Same creator. Same followers.\nTheir sponsored posts get about half the engagement.",
      body="""We see this all the time. One creator we checked for a retail brand did around 7% on normal posts and under 4% on brand deals.

That's normal. People know when it's an ad. A fashion brand put it bluntly: everyone knows the content they're seeing is paid.

The problem is which number goes into the plan. Most plans use the creator's average engagement, and that's mostly their normal posts.

Use their last few sponsored posts as the baseline instead.

It makes the forecast less exciting. It also makes it right.""",
      src="Galvor Scout run shown on a Gulf retailer call (6 Oct 2026); fashion D2C quote (11 Nov)",
      page="Raj on the engagement number that should go into a creator plan."),
 "2026-12-17": dict(title="The creator for your Android launch loves their iPhone", pillar="Creators & Testing",
      hook="You book a creator for an Android launch.\nThey've been praising their iPhone for two years.",
      body="""A retail team asked us this exact question. A phone brand wants three creators. How do you know none of them has spent two years talking up a rival?

Bios won't tell you. Agency lists won't either. You only find out by watching what they've posted.

Same with logos. We once flagged a rival brand's shoes clearly visible in a creator's draft. Nobody on the shoot had noticed.

This is where AI is actually useful. It can watch hundreds of a creator's videos and check what's on screen, what they say and what's in the captions. A person can't do that for 40 creators before a deadline.

Add one line to your next brief: no rival products shown or praised in the last six months. Then actually check it.""",
      src="Gulf electronics retailer, call 6 Oct 2026",
      page="Raj on checking creators for rival brands before you book them."),
 "2027-01-07": dict(title="15 creators, great awareness, 2 sold", pillar="Measurement",
      hook="15 creators. Great awareness.\nTwo of them actually sold anything.",
      body="""A streetwear brand told us this. Lots of views, plenty of clicks, nothing in the cart.

When you go ad by ad, the clicks are often fine. The problem is further down.

For a different brand, one creator's audience was mostly parents of newborns, and the product was for toddlers. Decent click rate, poor sales, high cost. Right creator, wrong audience.

In another case the clicks never turned into page views. That's the landing page or stock, not the video.

"The creator didn't work" is usually three or four different problems. Split it into hook, click, page and buy, and you'll know which one to fix.""",
      src="Streetwear D2C (19 Nov 2026); kids' nutrition analysis (19 Oct and 19 Nov)",
      page="Raj on splitting 'the creator didn't work' into the part that broke."),
 "2027-01-14": dict(title="The bio says fashion. The reels say gym.", pillar="Creators & Testing",
      hook="The bio says fashion.\nThe last 30 reels are gym videos.",
      body="""A brand told us this about creators their agency suggested. Another got a creator recommended for "speaks Bihari" because a database said so. Nobody had watched a single video.

Most creator tools work off metadata. Bio, category tags, follower count, maybe a guessed location. Quick, and often wrong.

The only reliable way is to watch the videos. What do they talk about? Do they speak on camera? In which language? Who's in the comments?

That used to be impossible at scale. Now AI watches around 20 recent videos per creator before anyone sees the shortlist.

It still gets things wrong sometimes. But it's wrong about what they actually post, not about their bio.""",
      src="Streetwear D2C (19 Nov); creator network call (21 Oct 2026)",
      page="Raj on why creator bios are a bad way to pick creators."),
 "2027-01-28": dict(title="Our dashboard told a brand to cut long ads. It was wrong.", pillar="Building Galvor",
      hook="Our dashboard told a brand to cut long ads.\nTheir best ad was 45 seconds of a mum talking.",
      body="""This one's on us.

We'd built a rule from lots of accounts: show the product early, long ads lose people. Usually true.

Then a nutrition brand showed us their top two ads. One was a mum talking for 40-odd seconds. The other was a doctor with a long intro before the product even appears. On cost per new customer, both were winning.

Their buyers are parents, and parents watch for the information. The general rule just didn't fit how they buy.

So we changed two things. We split new customers from retargeting, and we stopped judging ads that hadn't spent enough to judge.

If a tool's advice doesn't match what you know about your buyers, push back. We needed that.""",
      src="Kids' nutrition brand, call 6 Oct 2026",
      page="Raj on a rule our dashboard got wrong, and what we changed."),
 "2027-02-18": dict(title="\"Can't I just build this in Claude?\"", pillar="AI & the Team",
      hook="\"Can't I just build this in Claude?\"\nHonestly? Most of it, yes.",
      body="""We hear this a lot now. One brand had already connected their Meta ads to Claude before we met them. Another wrote a script in ChatGPT that beat ours. It did, we checked.

So I don't think the answer is "no, you can't". A good prompt and an ads connector get you surprisingly far.

What's harder is everything after that. Remembering what your last 2,000 ads taught you. Knowing which ones won because of the offer and which because of the creative. Not uploading company data somewhere you shouldn't.

That's where we spend most of our time.

If you're building it yourself, decide early where the memory lives. That's the bit that breaks first.""",
      src="Six brands raised it Aug-Nov 2026 (fashion, nutrition, apparel, skincare)",
      page="Raj on what you can build yourself with Claude, and the part that's hard."),
}

# --------------------------------------------------------------------------- Shrutik, Thursdays: New on Instagram
IG_FULL = {
 "2026-12-03": dict(title="New on Instagram: reach became views, and creator benchmarks broke",
      hook="Instagram stopped reporting reach the old way.\nYour creator benchmarks quietly broke.",
      body="""A retail client asked me this a few weeks ago. Until this year they judged creators on reach. Now Instagram reports views and viewers, and a creator who used to show 300K reach doesn't show 300K viewers.

So did the creator get worse, or did the ruler change?

Mostly the ruler. Views count every play, viewers are people. Neither one is the old reach number.

What I've started doing with clients:
Reset benchmarks from posts made after the change, not old reports.
Ask creators for viewers, not only views.
Don't put this year's numbers next to last year's in a deck without saying so.

I'm going to post what's new on Instagram every Thursday. Only the stuff that matters if you work with creators.""",
      check="Client observation (Gulf retailer, 6 Oct 2026). Before posting, confirm the views/viewers wording against Instagram's Insights help page.",
      page="Shrutik starts a weekly Instagram update. This week: why reach and views don't compare."),
 "2026-12-10": dict(title="New on Instagram: edit a Story after posting, and a check for stolen reposts",
      hook="You can now edit an Instagram Story after posting.\n15 minutes, and you keep the views.",
      body="""Small one, but useful. Text, music, stickers and drawings can be changed for 15 minutes after a Story goes up, and it keeps its views, likes and replies.

For creator campaigns this matters more than it sounds. A wrong link sticker or a typo in the discount code used to mean deleting and reposting, and losing the views it already had. Now the creator can just fix it.

Second one: Instagram is testing a content protection tool that looks for your original videos reposted without permission. Small group of creators for now.

If a brand reposts creator content without proper rights, that'll get noticed more. Worth checking your creator contracts cover reuse.""",
      check="Story editing: announced by Adam Mosseri, covered by Gizmodo 18 Nov 2026. Content protection: TechCrunch 17 Nov 2026. Re-check both are still live before posting.",
      page="Shrutik on this week's Instagram changes: Story edits and stolen reposts."),
 "2026-12-17": dict(title="New on Instagram: sends beat likes",
      hook="Instagram keeps saying the same thing.\nSends matter more than likes.",
      body="""In a Q&A in October, Mosseri said Instagram mostly looks for Reels and photos you'd send to someone. He's been saying versions of this for a while: watch time, sends and likes, each compared to how many people saw the post.

A fashion client said something that matches. People don't comment much anymore. They save, or they send it to a friend.

So when I look at a creator's past posts now, I check shares and saves before comments.

And in briefs I ask one simple thing: who would send this to whom? If nobody can answer, the video probably won't travel.""",
      check="Mosseri Q&A 23 Oct 2026 is reported by secondary sources; confirm on his Instagram/Threads before posting. Client quote: ethnic-wear retailer, 13 Oct 2026.",
      page="Shrutik on why sends count more than likes on Instagram."),
}
IG_BRIEF = ("Weekly brief (fill on Tuesday of this week): pick the one or two Instagram or Meta changes from the last 7 days "
            "that matter to brands working with creators. Sources: Adam Mosseri's Instagram/Threads, @creators, Meta newsroom, "
            "TechCrunch, Social Media Today. Confirm each change on an official source. Structure: hook (the change, plainly), "
            "what it means for a brand or a creator campaign, one thing to do this week. Use a client question if one fits "
            "(no names). Close: Follow Galvor for what's new on Instagram every Thursday.\n"
            "Ideas already raised by clients to use on slow weeks: Story layouts and fonts; Edits app on desktop and auto audio; "
            "Insights redesign; 'Your Algorithm' feed controls; trial reels for testing hooks; collab ads as the default way to "
            "boost creator posts; Instagram auto-translation vs regional briefs; long-form 'Features' test; originality rules for reposted content.")

# --------------------------------------------------------------------------- Raj, Tuesdays: Brand Breakdown (none are Galvor clients or CRM accounts)
BRANDS = [
 ("2026-12-01", "Mamaearth", "beauty and personal care, India"),
 ("2026-12-08", "boAt", "audio and wearables, India (gifting season)"),
 ("2026-12-15", "Mokobara", "luggage, India (holiday travel)"),
 ("2026-12-22", "Snitch", "menswear, India (party season)"),
 ("2026-12-29", "Minimalist", "skincare, India"),
 ("2027-01-05", "Gymshark", "fitness apparel, UK/global (New Year resolutions)"),
 ("2027-01-12", "Huel", "nutrition, UK/US"),
 ("2027-01-19", "Wakefit", "sleep and home, India"),
 ("2027-01-26", "The Whole Truth", "food, India"),
 ("2027-02-02", "Namshi", "fashion e-commerce, Gulf"),
 ("2027-02-09", "SUGAR Cosmetics", "beauty, India (Valentine's)"),
 ("2027-02-16", "Bombay Shaving Company", "grooming, India"),
 ("2027-02-23", "Glossier", "beauty, US"),
]
BB_SLIDES = [
 ("cover", "{brand} is running [N] Meta ads. We read every one."),
 ("stat", "Who posts them: brand page vs creator partnership ads"),
 ("list", "How alike they are: captions reused, top openers, CTA mix, language mix"),
 ("stat", "What's lasting: ads live 30+ days (a likely winner, not proof)"),
 ("list", "What they get right"),
 ("list", "What we'd question"),
 ("list", "Three hooks and how long each has run"),
 ("statement", "The takeaway for a brand your size"),
 ("text", "How we did this: public Meta Ad Library, [date range]. No spend or ROAS data; run time is a proxy."),
 ("cta", "Follow Galvor for a new brand every Tuesday"),
]
BB_NOTE = ("Brand Breakdown #{n}. Data: pull {brand}'s live ads (India unless noted) from the public Meta Ad Library the Friday before "
           "(Apify ads-library actor via the terminal, about $1-3 a pull), have AI read every ad, then fill each slide with real counts. "
           "Never use a number that isn't from the pull. Say plainly what public data can't show (spend, ROAS, dark ads; long-running "
           "isn't the same as winning, clients raised this). Market: {market}. Format follows the reference post the user shared "
           "(account split, sameness, what's lasting, what they get right, what to question, hooks with run times, takeaway, caveats), "
           "as a carousel. Caption: 2-line hook with the most surprising count, 3-4 short lines, link-free, Follow Galvor.")

# --------------------------------------------------------------------------- re-slotted drafts (by current id prefix -> new date)
SUNIL_KEEP = [  # Wed/Fri 09:00, in order
 ("li-2026-12-01-", "2026-12-02", "Sunil's ten-question memory test for anyone with a year of ad data."),
 ("li-2026-12-03-", "2026-12-04", "Sunil on what changed when the weekly report stopped eating Monday."),
 ("li-2026-12-08-", "2026-12-09", "Sunil's two-column test before hiring for a marketing role."),
 ("li-2026-12-10-", "2026-12-11", "Sunil wants to know who makes the call to cut an ad on your team. Vote on his post."),
 ("li-2026-12-15-", "2026-12-16", "Sunil on pilots that have no business question behind them."),
 ("li-2026-12-17-", "2026-12-18", "Sunil on why 'we already have an agency' is where the conversation starts."),
 ("li-2026-12-22-", "2026-12-23", "Sunil on why Galvor never touches a client's media budget."),
 ("li-2026-12-31-", "2026-12-30", "Sunil's year-end note: the habit he's keeping into 2027."),
 ("li-2026-12-29-", "2027-01-06", "Sunil on the marketing calls he'd never hand to AI."),
 ("li-2027-01-05-", "2027-01-08", "Sunil's five checks before AI content goes live at scale."),
 ("li-2027-01-14-", "2027-01-13", "Sunil's Lohri and Sankranti note on leaky funnels."),
 ("li-2027-01-07-", "2027-01-15", "Sunil on why a CAC problem is often a creative problem."),
 ("li-2027-01-12-", "2027-01-20", "Sunil on the CMO of 2028."),
 ("li-2027-01-19-", "2027-01-22", "Sunil on AI-generated vs AI-informed creative."),
 ("li-2027-01-21-", "2027-01-27", "The three numbers Sunil would keep on a founder's dashboard."),
 ("li-2027-01-26-", "2027-01-29", "Five questions Sunil says to ask any AI marketing vendor. Us included."),
 ("li-2027-01-28-", "2027-02-03", "Sunil on where Galvor still falls short with clients, and what we're changing."),
 ("li-2027-02-02-", "2027-02-05", "Sunil on AI making average marketing look busy."),
 ("li-2027-02-04-", "2027-02-10", "Sunil on paying twice for the same creative mistake."),
 ("li-2027-02-09-", "2027-02-12", "Sunil's one-page learning note before next year's budget."),
 ("li-2027-02-11-", "2027-02-17", "If a pilot could fix one thing, what would you pick? Sunil's poll."),
 ("li-2027-02-16-", "2027-02-19", "Sunil on who trains human judgement when AI does the junior work."),
 ("li-2027-02-18-", "2027-02-24", "Sunil on brand guidelines as a PDF vs Brand Memory as a system."),
 ("li-2027-02-25-", "2027-02-26", "Sunil on why 'we need more creators' is rarely the real problem."),
]
RAJ_KEEP = [  # Thu 16:00
 ("li-2026-12-23-", "2026-12-24", "Raj's three questions before you trust an AI agent with a decision."),
 ("li-2027-01-06-", "2026-12-31", "Raj on agents that claim to 'learn from their mistakes'."),
 ("li-2026-12-09-", "2027-01-21", "Raj on ranking ads by orders that stayed, not orders placed."),
 ("li-2027-02-17-", "2027-02-04", "Raj on what a long-running ad does and doesn't prove."),
 ("li-2026-12-16-", "2027-02-11", "Raj's four-call test for every chart in a weekly review."),
 ("li-2027-03-03-", "2027-02-25", "Raj on why three winners isn't a pattern."),
]
DECODED = [  # (current id prefix, new date, new number)
 ("nl-2026-12-02-", "2026-12-01", 7),
 ("nl-2026-12-16-", "2026-12-15", 8),
 ("nl-2026-12-30-", "2026-12-29", 9),
 ("nl-2027-01-13-", "2027-01-12", 10),
 ("nl-2027-02-17-", "2027-01-26", 11),
 ("nl-2027-02-10-", "2027-02-09", 12),
 ("nl-2026-12-09-", "2027-02-23", 13),
]
FESTIVAL_KEEP = ["li-2026-12-25-", "li-2027-01-01-"]   # Christmas, New Year (page, 12:30)


# --------------------------------------------------------------------------- helpers
def days():
    d = dt.date.fromisoformat(START)
    while d.isoformat() <= END:
        yield d
        d += dt.timedelta(days=1)


CLOSES = ["Follow Galvor for more from the rooms we sit in.", "Follow Galvor if this is the stuff you deal with too.",
          "Follow Galvor, we share what we learn from these calls.", "Follow Galvor for more of this.",
          "Follow Galvor for the next one."]
_ci = [0]


def caption(hook, body):
    _ci[0] += 1
    return f"{hook}\n\n{body.strip()}\n\n{CLOSES[_ci[0] % len(CLOSES)]}"


def repost(orig, line, date, time):
    who = {"sunil": "Sunil", "raj": "Raj", "shrutik": "Shrutik"}[orig["voice"]]
    return blank_post("linkedin", date, time=time, voice="company", pillar=orig.get("pillar") or "In the Room",
                      job="Attract", format="text", series="Page repost", status="draft",
                      title=f"Page repost: {orig['title'][:80]}", hook=line, caption=line,
                      notes=NOTE + f"Repost {who}'s post '{orig['title']}' ({orig['date']} {orig['time']}) from the Galvor page "
                                   "with this line, once the first hour of comments on the original is done. "
                                   "No link, no hashtags.",
                      repost_of={"voice": orig["voice"], "date": orig["date"], "time": orig["time"], "title": orig["title"]})


def main():
    apply = "--apply" in sys.argv
    posts = all_posts()
    in_range = [p for p in posts if START <= p["date"] and p["platform"] in ("linkedin", "newsletter")]
    ig_thu_images = [p for p in posts if p["platform"] == "instagram" and START <= p["date"] <= END
                     and dt.date.fromisoformat(p["date"]).weekday() == 3 and p.get("format") == "image"]
    keep_ids, new_posts, moves = set(), [], []          # moves: (post, changes)

    def find(prefix, plat, voice=None):
        hits = [p for p in in_range if p["id"].startswith(prefix) and p["platform"] == plat
                and (voice is None or p.get("voice") == voice)]
        if len(hits) != 1:
            raise SystemExit(f"expected 1 post for {prefix}, found {[h['id'] for h in hits]}")
        return hits[0]

    personal = []   # (post dict after change, page line)
    for prefix, date, line in SUNIL_KEEP:
        p = find(prefix, "linkedin", "sunil")
        moves.append((p, dict(date=date, time="09:00"))); keep_ids.add(p["id"])
        personal.append(({**p, "date": date, "time": "09:00"}, line))
    for prefix, date, line in RAJ_KEEP:
        p = find(prefix, "linkedin", "raj")
        moves.append((p, dict(date=date, time="16:00"))); keep_ids.add(p["id"])
        personal.append(({**p, "date": date, "time": "16:00"}, line))
    for prefix, date, n in DECODED:
        p = find(prefix, "newsletter")
        title = p["title"].split(":", 1)[1].strip() if ":" in p["title"] else p["title"]
        moves.append((p, dict(date=date, time="08:30", title=f"Decoded #{n}: {title}"))); keep_ids.add(p["id"])
    for prefix in FESTIVAL_KEEP:
        p = find(prefix, "linkedin", "company"); moves.append((p, dict(time="12:30"))); keep_ids.add(p["id"])

    # new: Sunil Mondays
    mondays = [d.isoformat() for d in days() if d.weekday() == 0]
    assert len(mondays) == len(SUNIL_MON) == 13
    for d, s in zip(mondays, SUNIL_MON):
        p = blank_post("linkedin", d, time="09:00", voice="sunil", pillar=s["pillar"], job="Attract", format="text",
                       series="What I heard this week", status="draft", title=s["title"], hook=s["hook"],
                       caption=caption(s["hook"], s["body"]), hashtags=["#MarketingLeadership", "#CreatorMarketing", "#D2C"],
                       notes=NOTE + f"Source (internal, never name in the post): {s['src']}. Quotes are close paraphrases from "
                                    "the meeting transcript; check the wording reads natural before approving.")
        new_posts.append(p); personal.append((p, s["page"]))
    # new: Raj Thursdays
    for d, s in RAJ_NEW.items():
        p = blank_post("linkedin", d, time="16:00", voice="raj", pillar=s["pillar"], job="Educate", format="text",
                       series="", status="draft", title=s["title"], hook=s["hook"], caption=caption(s["hook"], s["body"]),
                       hashtags=["#CreatorMarketing", "#MarketingAnalytics", "#AIinMarketing"],
                       notes=NOTE + f"Source (internal, never name in the post): {s['src']}.")
        new_posts.append(p); personal.append((p, s["page"]))
    # new: Raj Tuesdays, Brand Breakdown
    for n, (d, brand, market) in enumerate(BRANDS, 1):
        hook = f"{brand} is running [N] Meta ads right now.\nWe read every one. [most surprising count]."
        p = blank_post("linkedin", d, time="12:30", voice="raj", pillar="Public Data", job="Educate", format="carousel",
                       series="Brand Breakdown", status="idea", title=f"Brand Breakdown #{n}: {brand} on Meta",
                       hook=hook, caption=hook + "\n\n[3-4 short lines from the pull. No link.]\n\nFollow Galvor for a new brand every Tuesday.",
                       hashtags=["#D2C", "#CreativeStrategy", "#MetaAds"],
                       creative={"size": "portrait", "slides": []},
                       notes=NOTE + BB_NOTE.format(n=n, brand=brand, market=market) + "\nSlide outline (build after the pull):\n"
                             + "\n".join(f"{i}. [{l}] {h.format(brand=brand)}" for i, (l, h) in enumerate(BB_SLIDES, 1)))
        new_posts.append(p); personal.append((p, f"Raj took apart {brand}'s Meta ads this week. Worth a scroll."))
    # new: Shrutik Thursdays, New on Instagram (+ IG mirror)
    thursdays = [d.isoformat() for d in days() if d.weekday() == 3]
    assert len(thursdays) == 13
    for i, d in enumerate(thursdays, 1):
        s = IG_FULL.get(d)
        if s:
            p = blank_post("linkedin", d, time="09:00", voice="shrutik", pillar="Creators & Testing", job="Educate",
                           format="text", series="New on Instagram", status="draft", title=s["title"], hook=s["hook"],
                           caption=f"{s['hook']}\n\n{s['body'].strip()}\n\nFollow Galvor for what's new on Instagram every Thursday.",
                           hashtags=["#Instagram", "#CreatorMarketing", "#SocialMedia"],
                           notes=NOTE + "Fact check before approving: " + s["check"])
            line = s["page"]
        else:
            hk = "New on Instagram this week: [the change, plainly].\n[What it means for a creator campaign]."
            p = blank_post("linkedin", d, time="09:00", voice="shrutik", pillar="Creators & Testing", job="Educate",
                           format="text", series="New on Instagram", status="idea", title=f"New on Instagram, week {i}",
                           hook=hk, caption=hk + "\n\n[Body written on the Tuesday of this week]\n\nFollow Galvor for what's new on Instagram every Thursday.",
                           hashtags=["#Instagram", "#CreatorMarketing", "#SocialMedia"], notes=NOTE + IG_BRIEF)
            line = "Shrutik's weekly round-up of what changed on Instagram."
        new_posts.append(p); personal.append((p, line))
        ig = blank_post("instagram", d, time="13:00", voice="company", pillar="Quick Tip", job="Educate", format="carousel",
                        series="New on Instagram", status="idea", title=f"New on Instagram, week {i} (@galvor.ai)",
                        hook="New on Instagram this week", caption="New on Instagram this week: [change]. What it means for you: [one line]. Save this for later.\n\nFollow @galvor.ai for what's new every Thursday.",
                        hashtags=["#instagramupdates", "#instagramtips", "#creators"],
                        creative={"size": "portrait", "slides": [{"layout": "cover", "headline": "New on Instagram this week"},
                                                                {"layout": "text", "headline": "What changed"},
                                                                {"layout": "text", "headline": "What it means for brands and creators"},
                                                                {"layout": "cta", "headline": "Follow @galvor.ai for the weekly update"}]},
                        notes=NOTE + "Instagram mirror of Shrutik's LinkedIn post the same morning. Same facts, shorter, "
                                     "made for saves and sends. Script first, media only after the script is chosen.")
        new_posts.append(ig)

    # page reposts
    for p, line in personal:
        d = dt.date.fromisoformat(p["date"])
        if p["voice"] == "raj" and d.weekday() == 3:
            rd, rt = (d + dt.timedelta(days=1)).isoformat(), "16:00"
        else:
            rd = p["date"]
            rt = {"09:00": "13:00", "12:30": "16:30", "16:00": "20:00"}[p["time"]]
        new_posts.append(repost(p, line, rd, rt))

    archive = [p for p in in_range if p["id"] not in keep_ids] + ig_thu_images

    # ---------------------------------------------------------------- checks
    crm = ROOT.parent / "client-hub" / "data" / "crm"
    names = []
    for f in sorted(crm.glob("*/data.json.gz"))[-1:]:
        names = [a["name"] for a in json.load(gzip.open(f))["accounts"]]
    names += ["Sharaf", "Gritzo", "Insiya", "Kavita", "Ashish", "Nikita", "Modash", "CreatorIQ", "Samsung", "Crocs"]
    extra_ok = {"Google", "Palladium"}
    bad = 0
    final = [({**p, **ch}) for p, ch in moves] + new_posts
    for p in new_posts:
        text = " ".join([p.get("title", ""), p.get("hook", ""), p.get("caption", "")]).lower()
        for n in names:
            if n in extra_ok or len(n) < 4:
                continue
            if re.search(r"\b" + re.escape(n.lower()) + r"\b", text):
                print("CLIENT/NAME IN COPY:", p["date"], p["title"], "->", n); bad += 1
        for issue in lint_post(p):
            if issue["severity"] == "error" and issue["field"] != "images" and p["status"] != "idea":
                print("LINT ERROR:", p["date"], p["voice"], p["title"][:50], "->", issue["message"]); bad += 1
        if p["platform"] == "linkedin" and p["status"] == "draft" and p["voice"] != "company":
            for ln in p["hook"].split("\n")[:2]:
                if len(ln) > 60:
                    print("HOOK LINE >60:", p["date"], p["voice"], repr(ln));
            if "—" in p["caption"]:
                print("EM DASH:", p["date"], p["title"])
    # spacing: same handle twice a day / two handles within 3h
    slots = {}
    for p in final:
        if p["platform"] == "linkedin" or p["platform"] == "newsletter":
            slots.setdefault(p["date"], []).append((p["time"], p["voice"], p["title"][:40]))
    for d in sorted(slots):
        if not (START <= d <= END):
            continue
        row = sorted(slots[d])
        per = {}
        for t, v, _ in row:
            per[v] = per.get(v, 0) + 1
        dup = {v: n for v, n in per.items() if n > 1 and v != "company"}
        if dup:
            print("SAME HANDLE TWICE:", d, dup)
    # weekly counts
    print("\nWEEK        sunil raj shrutik page(own+reposts) decoded")
    for mon in mondays:
        wk = [p for p in final if mon <= p["date"] < (dt.date.fromisoformat(mon) + dt.timedelta(days=7)).isoformat()]
        c = lambda v, plat="linkedin": sum(1 for p in wk if p["platform"] == plat and p["voice"] == v)
        print(mon, f"{c('sunil'):5} {c('raj'):3} {c('shrutik'):7} {c('company'):17} {c('company', 'newsletter'):7}")
    print(f"\nnew posts: {len(new_posts)}  moved: {len(moves)}  to archive: {len(archive)}  problems: {bad}")
    if not apply:
        print("\nDry run. Add --apply to write.")
        for d in [x for x in sorted(slots) if "2026-11-30" <= x <= "2026-12-04"]:
            for t, v, ti in sorted(slots[d]):
                print(" ", d, t, v.ljust(8), ti)
        return
    if bad:
        raise SystemExit("Fix the problems above first.")
    # ---------------------------------------------------------------- write
    arch_root = ROOT / "content_archive"
    for p in archive:
        src = folder_of(p)
        dst = arch_root / src.relative_to(ROOT / "content")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst = dst.with_name(dst.name + "_plan2026-11-23")
        shutil.move(str(src), str(dst))
        print("archived", p["id"])
    for p, ch in moves:
        q = {**p, **ch}
        q["notes"] = (q.get("notes") or "") + f"\n{NOTE}Moved from {p['date']} {p['time']} to {q['date']} {q['time']}."
        save_post(q, note=f"{NOTE}re-slotted to {q['date']} {q['time']}")
    for p in new_posts:
        save_post(p, note=f"{NOTE}created")
    print("done")


if __name__ == "__main__":
    main()
