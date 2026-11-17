"""Enforce the brand rule: the closing CTA always asks people to follow Galvor, never an individual.

- Rewrites "Follow Raj/Sunil/Shrutik/KC …" and bare "Follow for …" to "Follow Galvor …" (LinkedIn) / "Follow @galvor.ai …" (Instagram)
- Drops "Follow Sunil, Raj and Shrutik"-style actions
- Ensures every closing `cta` slide carries a follow-Galvor action (max 3 actions)
- Fixes first comments that say "Follow along"
Re-renders changed posts. Usage: python tools/fix_follow_cta.py [--dry-run]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.render import render_post            # noqa: E402
from core.store import all_posts, folder_of, save_post  # noqa: E402

PEOPLE = r"(Raj Dhakad|Raj|Sunil Humne|Sunil|Shrutik Rathod|Shrutik|KC)"
PERSON_FOLLOW = re.compile(rf"^Follow {PEOPLE}\b", re.I)
MULTI = re.compile(rf"^Follow {PEOPLE}(,\s*{PEOPLE})*\s+and\s+{PEOPLE}\b", re.I)
BARE = re.compile(r"^Follow (for|along)\b", re.I)
GALVOR = re.compile(r"follow (galvor|@galvor.ai)", re.I)
# series that live on personal profiles: "Follow Galvor for Brief to Live" would mislead → plain "Follow Galvor"
PERSONAL_SERIES = re.compile(r"(?<=Follow Galvor) for (“|\")?(What I Heard in the Room|Brief to Live|the founder view)(”|\")?", re.I)


def brand(post):
    return "Follow @galvor.ai" if post["platform"] == "instagram" else "Follow Galvor"


def fix_text(t, post):
    if MULTI.match(t):
        return None                                   # drop the action entirely
    t2 = PERSON_FOLLOW.sub(brand(post), t)
    t2 = BARE.sub(lambda m: f"{brand(post)} {m.group(1).lower()}" if m.group(1).lower() == "for" else brand(post), t2)
    return t2


def main(dry):
    changed = []
    for p in all_posts():
        slides = (p.get("creative") or {}).get("slides") or []
        before = repr(slides) + repr(p.get("first_comment"))
        for s in slides:
            for k in ("headline", "sub"):
                if isinstance(s.get(k), str) and (PERSON_FOLLOW.match(s[k]) or BARE.match(s[k])):
                    s[k] = fix_text(s[k], p) or s[k]
            if s.get("actions"):
                s["actions"] = [x for x in (fix_text(a, p) for a in s["actions"]) if x]
        if slides and slides[-1].get("layout") == "cta":
            last = slides[-1]
            acts = [PERSONAL_SERIES.sub("", a) for a in (last.get("actions") or [])]
            follow = [a for a in acts if GALVOR.search(a)] or [brand(p)]
            rest = [a for a in acts if not GALVOR.search(a)]
            while len(rest) > 2:                 # keep max 3 actions: drop generic save/share first
                generic = [a for a in rest if re.match(r"^(Save|Share|Send it|Turn on)", a, re.I)]
                rest.remove(generic[-1] if generic else rest[-1])
            last["actions"] = follow[:1] + rest
        fc = p.get("first_comment") or ""
        if re.search(r"\bFollow along\b", fc):
            p["first_comment"] = re.sub(r"\bFollow along\b", "Follow Galvor", fc)
        if repr(slides) + repr(p.get("first_comment")) != before:
            changed.append(p)
            print(f"{p['id'][:58]:58} [{p['status']}] → {[a for a in (slides[-1].get('actions') or [])]}")
    if dry:
        print(f"\n{len(changed)} posts would change (dry run).")
        return
    for p in changed:
        saved = save_post(p, note="CTA rule: closing call-to-action asks people to follow Galvor")
        if saved.get("images"):
            saved["images"] = render_post(saved, folder_of(saved))
            save_post(saved)
    print(f"\n{len(changed)} posts updated and re-rendered.")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
