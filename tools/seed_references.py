"""One-off: save the references read in the Claude terminal on 16 Nov 2026, with their deep dives.
Safe to run again: items whose link or title is already saved are skipped.

    py -3.15 tools/seed_references.py [folder holding the video transcripts as <video id>.txt]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import refs  # noqa: E402

T = Path(sys.argv[1]) if len(sys.argv) > 1 else None
DAY = "2026-11-16"


def transcript(vid: str) -> str:
    f = T / f"{vid}.txt" if T else None
    return f.read_text(encoding="utf-8") if f and f.exists() else ""


ITEMS = [
    dict(vid="7I50PECz7SU", url="https://youtu.be/7I50PECz7SU", kind="video",
         title="Kallaway: How To Write A Killer Script That Keeps Viewers Hooked (YouTube, Feb 2025, 20 min)",
         note="Basis for the reel script prompt",
         s=dict(
             says="A YouTube creator (Kallaway, who says he has passed a billion views) lays out the five-step order he writes every script in: packaging, outline, intro, body, outro. His one principle is that people keep watching while what they get is better than what they expected, and every step is built to open that gap. It is the most useful of the five videos because it gives a repeatable order of work, not tips.",
             points=[
                 "Fix the idea, the title and a rough thumbnail before writing; the first lines must confirm what the title promised and then go one better.",
                 "Write a bullet outline before the script and check each point is new to the viewer. If the points only repeat common advice, do not make the video.",
                 "The opening has four beats: say what the video is about, state the common belief, give your different take, then give proof and a plan.",
                 "Put the second-best point first and the best point second, so the viewer feels the value rising and stays for the third.",
                 "Explain each point in three parts: what it is, how to do it with an example, and why it matters to the whole.",
                 "Add a short re-hook between points ('that only works if you also...') because attention fades unless it is renewed.",
                 "End on a high note that sums up what the viewer learned; that is where likes, shares and re-watches come from.",
                 "Mention a free resource inside the point it solves, in one line, so it does not feel like an advert.",
             ],
             use=[
                 "Reel scripts (Instagram Wednesday reel, LinkedIn video): the Studio's reel prompt now follows this order and refuses to write scenes when nothing in the outline is new.",
                 "Decoded newsletter reels: the 'common belief, then what we found' opening fits Galvor's findings directly.",
                 "Video generation: the first frame must confirm the title, and the screen resets at each re-hook. Both are in the video brief.",
                 "Raj's Ad of the Week: open on what most teams believe about the ad, then what the data showed.",
             ],
             changes=[
                 "Review the existing reel scripts in Scripts against the four-beat opening before choosing them.",
                 "Reorder points in any script that puts its best point last.",
                 "Add the outline check to script review: name the one thing in this script the viewer has not heard before.",
             ],
             caution=[
                 "Written for long YouTube videos; a 30-second reel has room for one or two points, so the opening beats must be compressed.",
                 "The 'second-best first' rule and the music-album comparison are his own observation, not tested evidence.",
                 "He promotes his own script tool and email course inside the video.",
             ])),
    dict(vid="_ZFncQNrOhw", url="https://youtu.be/_ZFncQNrOhw", kind="video",
         title="Diandra Escobar: How to Grow Your LinkedIn So Fast in 2026 (YouTube, Jul 2026, 20 min)",
         note="Basis for the LinkedIn post prompt",
         s=dict(
             says="A LinkedIn agency founder walks through the path a future client takes: first sees you in a comment, clicks your profile, later meets your post in the feed, reads for a few weeks, then sends a message. Her argument is that expertise and attention are separate things, and experts have to earn attention by joining conversations that are already happening. It is the most practical of the three LinkedIn videos for a small team with real expertise and little reach.",
             points=[
                 "New accounts are first noticed in other people's comment sections: list 20 to 30 creators whose audience is your buyer and spend 30 minutes a day leaving comments that add an example, a respectful disagreement or a short story.",
                 "The profile is the landing page: headline says the problem you solve and for whom; the About section runs problem, solution, proof, next step; Featured links to something you own.",
                 "She reports one consultant changed only his headline and About section and saw reach up 226% and engagement up 327% (one case, her own telling).",
                 "She says LinkedIn's feed now reads what a post is about and ranks by percentile, which favours smaller accounts, and that roughly the first 50 words decide whether a post is considered at all.",
                 "Five ways to join a live conversation: a known brand's move, this week's news, a person your audience follows, a belief you hold against the industry, a post format that is spreading.",
                 "Write the whole post first, then lift its sharpest line to the top as the hook. If no line is worth lifting, rewrite the post.",
                 "Her content mix: 40% growth, 30% authority, 20% conversion, 10% personal, with one point of view running through all of it.",
                 "Reply to an inbound message the same day; reach out to people who keep commenting, since that continues a conversation instead of starting a cold one.",
             ],
             use=[
                 "LinkedIn post prompt: body first, hook last; the first 50 words name the topic and the reader; one job per post. All in the Studio's prompt now.",
                 "Comment habit for Sunil, Raj and Shrutik: a shared list of 20 to 30 D2C and performance-marketing voices, 15 minutes a day. This is individual commenting, not a pod.",
                 "Profile check for all three before the calendar starts: headline, About, Featured pointing to Decoded.",
                 "Joining live conversations suits Raj (a brand's public ad library) and Sunil (industry news), within our rule on never stating a competitor's spend or ROAS.",
             ],
             changes=[
                 "Rewrite the three headlines and About sections to say the problem and the buyer in plain words.",
                 "Point each Featured section at the Decoded subscribe page.",
                 "Build the 20 to 30 name comment list and add it to the Playbook.",
                 "Keep Galvor's own mix (Attract 35, Educate 35, De-risk 20, Convert 10); it is close to hers and already agreed.",
             ],
             caution=[
                 "The claims about how LinkedIn's feed works (percentiles, 50 words, favouring small accounts) are her reading of LinkedIn's statements. Not checked against LinkedIn's own posts; treat as good practice, not fact.",
                 "All the result numbers are her agency's clients, told by her.",
                 "Hot takes and 'X is dead' formats can cost credibility with senior buyers if we do not hold the view.",
                 "The video sells her course, community and agency.",
             ])),
    dict(vid="kXvswxdr_BM", url="https://youtu.be/kXvswxdr_BM", kind="video",
         title="Diandra Escobar: The Best LinkedIn Lead Generation Strategy in 2026 (YouTube, Oct 2026, 16 min)",
         note="Lead magnets and the owned list",
         s=dict(
             says="The same agency founder argues that followers are rented and an email list is owned, so every strong post should offer something specific a reader can take in exchange for an email address. She covers what makes these giveaways fail, four formats that work, a follow-up question to send three days later, and a ladder of offers from free to expensive.",
             points=[
                 "She says her list grew to 6,000 readers in four months after she replaced 'follow for more' with a specific giveaway under each post.",
                 "Four reasons giveaways fail: too broad, not connected to the post, too slow to build, and no email capture or follow-up.",
                 "The rule: solve one specific problem for one specific person in one sitting, and ask whether someone would pay $20 for it.",
                 "Formats that work: a small tool, a 10-minute recorded walk-through, tested prompts people can copy, a five-day email course.",
                 "Do the deep thinking once a week in a long piece, then package that same thinking as posts and one giveaway.",
                 "Three days after someone downloads, ask one question: did you try it or is it sitting in your downloads?",
                 "Build steps between free and expensive so each step earns the next; never sell the big offer directly from a post.",
             ],
             use=[
                 "Decoded is already Galvor's owned list. Every LinkedIn post's first comment should point to the one Decoded issue that matches it, not to the newsletter in general.",
                 "A small giveaway per Decoded issue: for Issue #5, a one-page 'four things to read in your comments' checklist.",
                 "The weekly long piece is Decoded; the week's posts and reel should be cut from it. The Studio's repurpose buttons already do this.",
                 "The three-day follow-up question suits Shrutik's voice for pilots and demo requests.",
             ],
             changes=[
                 "Change first-comment links from the home page to the matching Decoded issue.",
                 "Make one checklist or template per Decoded issue and test whether subscribe rate rises.",
                 "Write down Galvor's ladder: post, Decoded, a free read of your public ads, pilot.",
             ],
             caution=[
                 "Her numbers are her own and unaudited.",
                 "A third of the video promotes her own product for hosting giveaways.",
                 "Asking for a phone number or too many fields would put off senior marketing buyers; keep it to an email.",
             ])),
    dict(vid="0H4uouOn7lI", url="https://youtu.be/0H4uouOn7lI", kind="video",
         title="Matt Gray: How to beat the new LinkedIn algorithm in 16 minutes (YouTube, Dec 2025, 17 min)",
         note="Profile, image-led posts, calls to action",
         s=dict(
             says="A creator with a large LinkedIn following describes three parts of his approach: a profile that converts visitors, a system for getting early engagement, and a content system. Most of it is general, but three ideas are useful: own one word in the reader's mind, treat a dense image as the post's thumbnail, and tie each call to action to the post's topic.",
             points=[
                 "Pick the one word you want to own and put it in the profile's one-line description (his is 'systems').",
                 "A dense, hand-drawn image that sums up the post acts as its thumbnail; he credits one such image with a post that reached 24 million views (his figure).",
                 "Four post types he relies on: behind the scenes, value-packed images, how-I-do-it detail, and personal stories.",
                 "The first three lines decide everything: raise curiosity, name who it is for, promise something specific.",
                 "The call to action should offer something tightly linked to the post's subject.",
                 "Review the top 10% of your posts every 30 days and do more of what they share.",
                 "He arranges for 25 to 30 people to engage with each post in its first 45 minutes.",
             ],
             use=[
                 "Galvor's word to own: 'why' (why your ads win) or 'creative memory'. Put it in all three profiles and the page description.",
                 "One-page summary images for Raj's teardowns and Decoded findings, made only after the script is chosen.",
                 "The monthly top-10% review belongs in Results: it already has the data once LinkedIn exports are imported.",
             ],
             changes=[
                 "Agree the one word and add it to each headline.",
                 "Add a monthly reminder: review the top 10% of posts and write down what they share.",
                 "For the first image-led post, test a hand-drawn one-pager against a clean branded one.",
             ],
             caution=[
                 "Arranging 25 to 30 people to engage in the first 45 minutes is an engagement pod. It breaks our rule and the plan's rule; do not copy it. The team's own honest comments in the first hour are fine.",
                 "The video is from December 2025 and the least current of the five.",
                 "Follower and view counts are his own; much of the video sells his paid programme.",
                 "His audience is founders in general, not senior marketing buyers.",
             ])),
    dict(vid="ibfdqyz4KhQ", url="https://youtu.be/ibfdqyz4KhQ", kind="video",
         title="Lara Acosta: Watch Me Use AI to Create 30 Days of Viral LinkedIn Posts (YouTube, Aug 2025, 11 min)",
         note="How to brief an AI writer",
         s=dict(
             says="A LinkedIn creator shows her prompts for getting 30 days of posts from an AI model: give it real context about the person, ask for content pillars, generate hooks from examples of hooks that worked, then full posts from example posts you like. The useful part is the method of feeding the writer real examples; the 'viral' part should be left alone.",
             points=[
                 "Give the model the person's real profile text and recent posts before asking for anything.",
                 "Base content on three things: what you can teach, what you can sell, and the stories that connect them.",
                 "Split posts by audience: broad to gain followers, narrower to build trust, specialist to bring in buyers.",
                 "Her hook format: a bold first line of eight words or fewer, then a second line that re-hooks.",
                 "Give the model posts you personally stopped to read; the output takes on that taste.",
                 "For reach she adds general topics (transformations, remote work, leadership, 'six ways to').",
             ],
             use=[
                 "Voices page: saving 10 to 15 real posts per person is this method. The writer now receives them on every draft.",
                 "The two-line hook is in the LinkedIn prompt, loosened to 12 words so it does not read as a formula.",
                 "Broad, narrower, specialist maps onto Attract, Educate and De-risk or Convert.",
             ],
             changes=[
                 "Collect the real posts for Sunil, Raj and Shrutik and paste them into Voices.",
                 "Keep a short file of hooks from our own best posts and feed those back in, not other creators' hooks.",
             ],
             caution=[
                 "Generic 'viral' topics would bring the wrong audience for Galvor and are excluded from the prompt.",
                 "A hard limit of eight words a sentence makes copy sound machine-written; we do not use it.",
                 "Her example invents a personal transformation for someone else. We never do that.",
                 "From August 2025; she sells a writing course.",
             ])),
    dict(url="", kind="image", title="OtterlyAI study: which LinkedIn content gets cited in AI answers (image shared via KC, AI_citation.jpeg)",
         note="AI citation test",
         text="Image summary (read in the Claude terminal): a post by Klaus-M. Schremser of OtterlyAI reporting a 30-day test of 240 pieces of LinkedIn content. Of 107 AI citations, 2 went to regular LinkedIn posts and 105 to LinkedIn articles (Pulse). Articles from personal profiles were cited 2.9 times as often as company-page articles. Microsoft Copilot and Perplexity made up 99.1% of the citations.",
         s=dict(
             says="A post from the founder of OtterlyAI, a tool that tracks AI citations, reporting a 30-day test of 240 pieces of LinkedIn content. Almost all the citations AI assistants gave went to LinkedIn articles, not ordinary posts, and articles from a person's profile were cited far more than articles from a company page.",
             points=[
                 "240 pieces of content were tracked for 30 days.",
                 "Of 107 AI citations, 105 went to LinkedIn articles and 2 to regular posts.",
                 "Articles from personal profiles were cited 2.9 times as often as company-page articles.",
                 "Copilot and Perplexity accounted for 99.1% of the citations.",
             ],
             use=[
                 "Decoded: republish each issue as a LinkedIn article from Raj's own profile a few days after the page sends it, and see whether AI assistants start citing it.",
                 "Results: note by hand when Perplexity or Copilot cites Galvor for 'creative intelligence for D2C' questions.",
             ],
             changes=[
                 "Run this as a four-issue test starting with Decoded #5 from Raj's profile.",
                 "Ask five buyer-style questions in Perplexity and Copilot once a month and log who gets cited.",
             ],
             caution=[
                 "One vendor's test of its own category, 30 days, small numbers. A signal to test, not a rule.",
                 "ChatGPT and Google's AI answers barely appear in the result, so it says little about them.",
                 "Publishing the same text in two places needs the article to link back to the original issue.",
             ])),
    dict(url="https://www.linkedin.com/posts/borja-obeso_bye-bye-manual-link-building-claude-with-share-7527002048467222529-cMRH/", kind="link",
         title="Borja Obeso: a Claude skill for link building (LinkedIn post)", note="Link building ideas",
         text="Summary of the post as read in the Claude terminal: Borja Obeso describes a Claude skill that automates link building in four ways: outreach to 'best tools' list articles asking to be added, replying to journalist requests, backlink exchanges, and directory listings.",
         s=dict(
             says="A LinkedIn post describing an AI skill that does link building for a software company in four ways: asking authors of 'best tools' lists to include you, answering journalists' requests for sources, swapping links with other sites, and submitting to directories.",
             points=[
                 "Outreach to list articles ('best creative analytics tools') to be added.",
                 "Answering journalist requests for expert comment.",
                 "Backlink exchanges with other sites.",
                 "Directory listings.",
             ],
             use=[
                 "List articles matter for Galvor: the competitor research found vendor-written 'best tools' pages own the search results for creative analytics. Being named in the independent ones is worth the outreach.",
                 "Directories: G2, Product Hunt, Capterra and AI tool directories, done once.",
                 "Journalist requests suit Sunil's voice on D2C marketing spend.",
             ],
             changes=[
                 "List the 15 independent 'best creative analytics or ad intelligence tools' articles and ask to be included, with one finding from Decoded as the reason.",
                 "Submit Galvor to the main directories with real product screenshots.",
             ],
             caution=[
                 "Skip backlink exchanges: swapped links are against search engines' guidelines unless marked as sponsored.",
                 "Mass automated outreach reads as spam; keep it to a short, hand-checked list.",
                 "Only the visible part of the post could be read without sign-in. Paste the full text for a fuller read.",
             ])),
    dict(url="https://www.linkedin.com/posts/tim-scheuer-91b005237_sequoia-the-next-1t-idea-is-the-ai-native-share-7526667172006313984-Gu1l/", kind="link",
         title="Tim Scheuer: the six layers of an AI-native firm (LinkedIn post)", note="Second brain idea",
         text="Summary of the post as read in the Claude terminal: Tim Scheuer, citing Sequoia's view that the next large opportunity is the AI-native firm, lays out six layers such a firm runs on AI: acquisition, nurture, convert, onboard, fulfil, and a 'second brain' that stores what the firm learns.",
         s=dict(
             says="A LinkedIn post that builds on a Sequoia argument about AI-native companies and names six layers such a company runs with AI: getting attention, nurturing, converting, onboarding, delivering the work, and a shared memory of what the company has learned.",
             points=[
                 "Six layers: acquisition, nurture, convert, onboard, fulfil, second brain.",
                 "The 'second brain' is one place that stores what the firm learns so each piece of work starts from it.",
             ],
             use=[
                 "The Studio's References, Competitors and Voices pages are this shared memory for marketing: what KC shares, what rivals do and how each person writes all feed the next draft.",
                 "It echoes Galvor's own line, 'every ad should make the next one better', which Sunil can use as a point of view post.",
             ],
             changes=[
                 "Add an objections list to the Playbook: every doubt a buyer raises, with the post or Decoded issue that answers it.",
                 "Keep a 'first heard of Galvor via' note on each demo request.",
             ],
             caution=[
                 "A framework post with no evidence behind it.",
                 "Mass automated outbound, which posts like this often lead to, does not fit a senior-buyer audience.",
                 "Only the visible part of the post could be read without sign-in.",
             ])),
]

have = {(r.get("url") or r["title"]) for r in refs.all_refs()}
for it in ITEMS:
    key = it["url"] or it["title"]
    if key in have:
        print("skip", it["title"][:50])
        continue
    text = transcript(it["vid"]) if it.get("vid") else it.get("text", "")
    r = refs.add(url=it["url"], text=text or "(no text saved)", title=it["title"], shared_by="KC / Suyash", day=DAY, note=it["note"])
    refs.save_summary(r["id"], it["s"], by="Claude terminal")
    print("saved", r["folder"], len(text))
