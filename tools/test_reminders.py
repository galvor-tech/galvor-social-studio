"""Reminder engine: simulate a day's timeline against a temp content folder.
  python tools/test_reminders.py
"""
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import notify, reminders, store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="gss_rem_"))
store.CONTENT = tmp / "content"
reminders.LOGS = tmp / "logs"
reminders.STATE = tmp / "logs" / "reminders.json"
sent = []
notify.send = lambda to, subj, body, path="", ev="", exclude="": sent.append((ev, subj, path)) or len(to)
ok = True


def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)


day = (date.today() + timedelta(days=1)).isoformat()
p = store.save_post(store.blank_post("instagram", day, time="19:00", format="carousel", title="Test carousel",
                                     caption="x", status="approved", voice="company"))
q = store.save_post(store.blank_post("linkedin", day, time="09:00", format="text", title="Sunil test", caption="y",
                                     status="draft", voice="sunil"))
T = datetime.fromisoformat(f"{day}T19:00")
evs = lambda: [e for e, s, _ in sent if "Test carousel" in s]

reminders.tick(T - timedelta(minutes=45));  check(evs() == [], "nothing 45 min before")
reminders.tick(T - timedelta(minutes=29));  check(evs() == ["reminder"], "'coming up' 30 min before")
reminders.tick(T - timedelta(minutes=10));  check(evs() == ["reminder"], "no duplicate 'coming up'")
reminders.tick(T + timedelta(minutes=1));   check(evs() == ["reminder", "due"], "'post now' at the slot")
reminders.tick(T + timedelta(minutes=60));  check(evs() == ["reminder", "due"], "quiet between due and missed")
reminders.tick(T + timedelta(minutes=121)); check(evs() == ["reminder", "due", "missed"], "'missed' after 2 h")
reminders.tick(T + timedelta(minutes=200)); check(evs().count("missed") == 1, "missed only once")
check(any("/kit/" in path and "?k=" in path for e, s, path in sent if "Test carousel" in s), "reminder links to the signed phone kit")
check(any("Sunil test" in s for e, s, _ in sent), "unapproved LinkedIn post is also reminded")

pp = store.get_post(p["id"]); pp.update(status="published", published_at=(T + timedelta(minutes=130)).isoformat()); store.save_post(pp)
reminders.tick(T + timedelta(minutes=150)); check("reply" not in evs(), "no reply nudge before 30 min live")
reminders.tick(T + timedelta(minutes=161)); check(evs().count("reply") == 1, "reply-to-comments nudge 30 min after live")

# digests: once a day
sent.clear()
d0 = datetime.fromisoformat(f"{day}T08:31") + timedelta(days=1)
reminders.tick(d0); reminders.tick(d0 + timedelta(minutes=5))
check([e for e, *_ in sent].count("digest") == 1, "daily digest sent once")

# rescheduling + buffer
nxt = reminders.next_free_slot(store.get_post(q["id"]))
check(nxt and nxt[0] > day and date.fromisoformat(nxt[0]).weekday() == 1 and nxt[1] == "09:00", f"next Sunil slot is a Tuesday 09:00 ({nxt})")
b = reminders.buffer_days()
check(set(b) == {"linkedin", "instagram"} and b["linkedin"]["level"] == "bad", "buffer flags LinkedIn (draft next)")
check(reminders.kit_ok(p["id"], reminders.kit_token(p["id"])) and not reminders.kit_ok(p["id"], "nope"), "kit tokens verify")

shutil.rmtree(tmp, ignore_errors=True)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
