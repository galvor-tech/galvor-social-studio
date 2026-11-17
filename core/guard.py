"""Content warnings learned from 63 sales meetings (ported from galvor-cms guard.py).

They flag; they never block. A person decides. Each flag says why it exists.
check(text) -> [{severity: 'warn', rule, message, why}]
"""
from __future__ import annotations

import re

# From the CMS, as it is there.
CMS_CLIENT_NAMES = [
    "Traya", "Gritzo", "HealthKart", "Bioderma", "NAOS", "MaisonX", "Maison X", "Sharaf", "Esme",
    "TechnoSport", "DaMENSCH", "Amberstone", "Hair Originals", "Clovia", "Biba", "Axis Bank",
]
# From the studio's core/lint.py CLIENTS list (kept in step by hand; lint.py is not imported to stay independent).
STUDIO_CLIENT_NAMES = [
    "XTEND", "C4 Original", "Pure Nutrition", "Physics Wallah", "halo care", "Blue Nectar", "MaisonX",
    "GMR", "AngelOne", "Angel One", "Palladium", "Gritzo", "HealthKart", "Traya", "Fazlani", "Sopariwala",
    "Kreedo", "Carvix", "Glowfolk", "Comet",
]
CLIENT_NAMES = list(dict.fromkeys(CMS_CLIENT_NAMES + STUDIO_CLIENT_NAMES))

RULES = [
    (re.compile(r"\b(won(?!['’]t)|winning|winners?|best[- ]performing|top[- ]performing|worked best)\b", re.I),
     "results-claim",
     "Says an ad won or performed best.",
     "Buyers reject this when the only evidence is how long an ad ran. "
     "Back it with real results data, or say \"ran longest\"."),
    (re.compile(r"\b(" + "|".join(re.escape(n) for n in CLIENT_NAMES) + r")\b", re.I),
     "client-name",
     "Names a client.",
     "Public posts never name a client or its category without written permission."),
    (re.compile(r"\b(guarantee[sd]?|10x|100x)\b", re.I),
     "overclaim",
     "Promises an outcome.",
     "Remove it or back it with a measured result."),
]


def check(text: str) -> list[dict]:
    flags = []
    for rx, rule, msg, why in RULES:
        hits = sorted({m.group(0) for m in rx.finditer(text or "")}, key=str.lower)
        if hits:
            flags.append({"severity": "warn", "rule": rule,
                          "message": f"{msg} ({', '.join(hits)})", "why": why, "words": hits})
    return flags
