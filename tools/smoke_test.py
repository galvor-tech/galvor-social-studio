"""Load every page and API read path; fail loudly on any 4xx/5xx or template error."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import app
from core.store import all_posts

c = app.test_client()
posts = all_posts()
urls = ["/", "/overview", "/approvals", "/calendar", "/calendar?m=2026-12&p=instagram", "/calendar?m=2027-01&p=linkedin", "/calendar?m=2026-11&p=newsletter", "/calendar?m=%0D%0A&p=all", "/calendar?m=2026-13&p=x",
        "/content/linkedin", "/content/instagram", "/content/newsletter", "/content/linkedin?status=designed&month=2026-11",
        "/new", "/new?platform=instagram&date=2026-11-20&festival=Test", "/planner", "/planner?start=2027-02-01&weeks=2",
        "/topics", "/festivals", "/festivals?cat=sale", "/strategy", "/brand", "/gaps", "/analytics", "/settings", "/discover", "/discover?all=1&sort=recent", "/ideas", "/ideas?status=used",
        "/results", "/results?days=90&p=linkedin", "/results?days=28&p=instagram", "/decoded",
        "/search?q=fatigue",
        "/scripts", "/scripts?days=all&voice=raj", "/competitors", "/references", "/costs", "/voices", "/prompts"]
urls += [f"/post/{p['id']}" for p in posts]
bad = 0
for u in urls:
    r = c.get(u, follow_redirects=True)
    if r.status_code != 200:
        bad += 1
        print("FAIL", r.status_code, u, r.data[:300])
for p in posts[:5]:
    for img in [i for i in p.get("images", []) if i.endswith(".png")][:1]:
        r = c.get(f"/media/{p['id']}/{img}")
        if r.status_code != 200:
            bad += 1; print("FAIL media", p["id"])
# phone kit: signed link works from another device; unsigned does not; the rest of the studio stays private
from core.reminders import kit_path
remote = {"REMOTE_ADDR": "192.168.1.50"}
for p in [q for q in posts if q["platform"] != "newsletter"][:8]:
    r = c.get(kit_path(p), environ_base=remote)
    if r.status_code != 200:
        bad += 1; print("FAIL kit", r.status_code, p["id"], r.data[:200])
    r = c.get(f"/kit/{p['id']}", environ_base=remote)
    if r.status_code != 403:
        bad += 1; print("FAIL kit without token should be 403", r.status_code)
for u in ("/", "/results", "/settings"):
    r = c.get(u, environ_base=remote)
    if r.status_code != 403:
        bad += 1; print("FAIL remote access to", u, "should be 403, got", r.status_code)
# every form on the calendar must submit a real month (regression: the platform buttons once sent a blank month)
import re as _re
for _mo in ("2026-11", "2026-12"):
    _html = c.get(f"/calendar?m={_mo}").data.decode()
    for _v in _re.findall(r'name="m" value="([^"]*)"', _html):
        if _v != _mo:
            bad += 1; print("FAIL calendar form month", repr(_v))
print(f"{len(urls)} pages checked, {bad} failures")
sys.exit(1 if bad else 0)
