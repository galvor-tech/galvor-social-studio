"""Spend record and daily ceiling for the paid research calls (Hiker, Apify, AI for ideas).

Ported from galvor-cms ledger.py. Every paid call asks `check()` first and calls
`record()` after. Cap comes from settings key `discover_daily_cap_usd` (default $2).
Stored in data/spend.json as {"entries": [{at, day, provider, what, usd}]}.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

from .config import DATA, load_settings

SPEND_FILE = DATA / "spend.json"
DEFAULT_CAP_USD = 2.0
KEEP_DAYS = 400

_lock = threading.RLock()


class OverBudget(Exception):
    pass


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        d = json.loads(SPEND_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("entries"), list):
            return d
    except (OSError, json.JSONDecodeError):
        pass
    return {"entries": []}


def _save(d: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = SPEND_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SPEND_FILE)


def cap() -> float:
    try:
        return float(load_settings().get("discover_daily_cap_usd", DEFAULT_CAP_USD))
    except (TypeError, ValueError):
        return DEFAULT_CAP_USD


def spent_today() -> float:
    with _lock:
        t = today()
        return round(sum(e.get("usd", 0) for e in _load()["entries"]
                         if e.get("day") == t and e.get("cap", True)), 4)


def check(estimate_usd: float, what: str) -> None:
    with _lock:
        used, limit = spent_today(), cap()
        if used + estimate_usd > limit:
            raise OverBudget(f"{what} would take today's research spend past the ${limit:.2f} daily limit "
                             f"(${used:.2f} used). Raise the limit in Settings, or wait until tomorrow.")


def record(provider: str, what: str, usd: float, **extra) -> None:
    """extra: cap=False keeps the entry out of the daily research cap; tokens/model/note are shown on Costs."""
    with _lock:
        d = _load()
        d["entries"].append({"at": datetime.now().isoformat(timespec="seconds"), "day": today(),
                             "provider": provider, "what": what, "usd": round(float(usd), 5), **extra})
        cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        d["entries"] = [e for e in d["entries"] if e.get("day", "") >= cutoff]
        _save(d)


# HikerAPI keyword searches (hashtag top posts, account posts). The username→id lookup is a setup step, not a search.
HIKER_SEARCH_PATHS = ("/v2/hashtag/medias/top", "/g2/user/medias")
DEFAULT_HIKER_SEARCHES = 20
HIKER_USD_PER_REQUEST = 0.001  # same figure as core.discover


def hiker_search_limit() -> int:
    try:
        return max(0, int(load_settings().get("hiker_daily_searches", DEFAULT_HIKER_SEARCHES)))
    except (TypeError, ValueError):
        return DEFAULT_HIKER_SEARCHES


def hiker_searches_today() -> int:
    with _lock:
        t = today()
        return sum(1 for e in _load()["entries"]
                   if e.get("day") == t and e.get("provider") == "hiker" and e.get("what") in HIKER_SEARCH_PATHS)


def reserve_hiker_search(path: str) -> None:
    """Count one Hiker search against today's limit, or raise OverBudget. Check and record happen under one
    lock, so parallel scan workers can't overshoot. Recorded before the request: Hiker bills it either way."""
    with _lock:
        used, limit = hiker_searches_today(), hiker_search_limit()
        if used >= limit:
            raise OverBudget(f"Today's Instagram (Hiker) search limit is used up ({used} of {limit}). "
                             f"Raise it in Settings, or wait until tomorrow.")
        check(HIKER_USD_PER_REQUEST, "An Instagram search")
        record("hiker", path, HIKER_USD_PER_REQUEST)



def summary() -> dict:
    with _lock:
        entries = _load()["entries"]
    t = today()
    by = {}
    for e in entries:
        if e.get("day") != t:
            continue
        row = by.setdefault(e["provider"], {"provider": e["provider"], "usd": 0.0, "calls": 0})
        row["usd"] += e.get("usd", 0)
        row["calls"] += 1
    for r in by.values():
        r["usd"] = round(r["usd"], 4)
    month = sum(e.get("usd", 0) for e in entries if e.get("day", "")[:7] == t[:7])
    return {"today": spent_today(), "cap": cap(), "by_provider": sorted(by.values(), key=lambda r: -r["usd"]),
            "month": round(month, 2), "hiker_searches": hiker_searches_today(),
            "hiker_limit": hiker_search_limit()}


# ---------------------------------------------------------------- AI writing spend (Claude / Gemini text calls)
# USD per million tokens. Claude prices are Anthropic's list prices (checked 16 Nov 2026); cache writes bill at
# 1.25x input and cache reads at the listed read price. Gemini text is an estimate: check your Google bill.
AI_PRICES = {
    "claude-opus-5-5":   {"in": 4.0, "out": 20.0, "cache_write": 5.0, "cache_read": 0.20},
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0, "cache_write": 2.5, "cache_read": 0.10},
    "claude-haiku-5-5":  {"in": 0.10, "out": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-fable-5-2":  {"in": 8.0, "out": 40.0, "cache_write": 10.0, "cache_read": 0.20},
}
DEFAULT_AI_MONTHLY_CAP = 30.0


def ai_cost(model: str, inp: int = 0, out: int = 0, cache_write: int = 0, cache_read: int = 0) -> float | None:
    r = AI_PRICES.get(model or "")
    if not r:
        return None
    return (inp * r["in"] + out * r["out"] + cache_write * r["cache_write"] + cache_read * r["cache_read"]) / 1e6


def ai_monthly_cap() -> float:
    try:
        return float(load_settings().get("ai_monthly_cap_usd", DEFAULT_AI_MONTHLY_CAP))
    except (TypeError, ValueError):
        return DEFAULT_AI_MONTHLY_CAP


def ai_spent_month() -> float:
    m = today()[:7]
    with _lock:
        return round(sum(e.get("usd", 0) for e in _load()["entries"]
                         if e.get("day", "")[:7] == m and e.get("kind") == "ai"), 4)


def check_ai() -> None:
    used, limit = ai_spent_month(), ai_monthly_cap()
    if limit > 0 and used >= limit:
        raise OverBudget(f"This month's AI writing limit is used up (${used:.2f} of ${limit:.2f}). "
                         f"Raise it on the Costs page, or write this one in the Claude terminal.")


def entries() -> list[dict]:
    with _lock:
        return list(_load()["entries"])


def report() -> dict:
    """Everything the Costs page shows."""
    es = entries()
    t, m = today(), today()[:7]
    def roll(key, rows):
        out = {}
        for e in rows:
            r = out.setdefault(e.get(key) or "other", {"name": e.get(key) or "other", "usd": 0.0, "calls": 0})
            r["usd"] += e.get("usd", 0); r["calls"] += 1
        for r in out.values():
            r["avg"] = round(r["usd"] / r["calls"], 4) if r["calls"] else 0
            r["usd"] = round(r["usd"], 4)
        return sorted(out.values(), key=lambda r: -r["usd"])
    month = [e for e in es if e.get("day", "")[:7] == m]
    days = {}
    for e in es:
        days[e.get("day", "")] = round(days.get(e.get("day", ""), 0) + e.get("usd", 0), 4)
    months = {}
    for e in es:
        k = e.get("day", "")[:7]
        months[k] = round(months.get(k, 0) + e.get("usd", 0), 4)
    return {"today": round(sum(e.get("usd", 0) for e in es if e.get("day") == t), 4),
            "month": round(sum(e.get("usd", 0) for e in month), 4), "all": round(sum(e.get("usd", 0) for e in es), 4),
            "by_provider": roll("provider", month), "by_action": roll("what", month), "by_action_all": roll("what", es),
            "days": sorted(days.items(), reverse=True)[:31], "months": sorted(months.items(), reverse=True),
            "recent": sorted(es, key=lambda e: e.get("at", ""), reverse=True)[:60],
            "research_cap": cap(), "research_today": spent_today(),
            "ai_cap": ai_monthly_cap(), "ai_month": ai_spent_month(), "count": len(es)}
