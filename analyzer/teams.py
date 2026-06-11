"""Team-name matching across data sources.

The Odds API and football-data.org name the same teams differently
("South Korea" vs "Korea Republic", "USA" vs "United States", "Czechia"
vs "Czech Republic"). Settlement and venue matching both need to bridge
that, so the aliases live in one place.
"""

from __future__ import annotations
import re
import unicodedata

_ALIASES = {
    "korea republic": "south korea", "republic of korea": "south korea",
    "korea rep": "south korea",
    "korea dpr": "north korea", "dpr korea": "north korea",
    "united states": "usa", "united states of america": "usa",
    "czech republic": "czechia",
    "turkiye": "turkey",
    "cote divoire": "ivory coast", "cote d ivoire": "ivory coast",
    "cabo verde": "cape verde",
    "holland": "netherlands",
    "ir iran": "iran", "iran islamic republic": "iran",
    "united arab emirates": "uae",
    "congo dr": "dr congo", "democratic republic of the congo": "dr congo",
    "bosnia herzegovina": "bosnia", "bosnia and herzegovina": "bosnia",
}


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _ALIASES.get(s, s)


def team_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na
