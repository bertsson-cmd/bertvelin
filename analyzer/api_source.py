"""
The Odds API source (the-odds-api.com) -- fully automatic odds, no daily typing.

Setup (once):
  1. Get a free API key at https://the-odds-api.com (free tier ~500 requests/mo;
     one request per day uses ~30 of them, so it comfortably covers the tournament).
  2. Locally:  export ODDS_API_KEY=yourkey
     GitHub:   repo Settings -> Secrets -> Actions -> new secret ODDS_API_KEY
  3. Run:      python3 main.py --api

What you get vs. the Google Sheet route:
  + zero daily effort; the site updates itself with current market odds
  - consensus EU bookmaker prices, not necessarily Epicbet's exact ones
    (usually within a few percent -- check the real price before placing)
  - no analyst adjustments/notes, unless you ALSO keep the sheet: run with
    both --api and --sheet and your sheet's adjustment/note columns are
    merged onto the API odds by team names.
"""

from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from datetime import date

BASE = "https://api.the-odds-api.com/v4"


def _get(path: str, **params) -> tuple[object, dict]:
    params["apiKey"] = os.environ.get("ODDS_API_KEY", "")
    if not params["apiKey"]:
        raise RuntimeError("Set the ODDS_API_KEY environment variable (see module docstring).")
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "wc26-analyzer"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        remaining = resp.headers.get("x-requests-remaining", "?")
        return json.loads(resp.read().decode("utf-8")), {"remaining": remaining}


def discover_world_cup_key() -> str:
    """Find the FIFA World Cup sport key instead of hardcoding it."""
    sports, _ = _get("/sports", all="true")
    for s in sports:
        if "world_cup" in s.get("key", "") and "soccer" in s.get("key", "") \
                and "winner" not in s.get("key", ""):
            return s["key"]
    raise RuntimeError(
        "No FIFA World Cup sport key found. Inspect the /v4/sports response "
        "and set it manually via the --sport-key flag."
    )


def load_from_api(sport_key: str | None = None, region: str = "eu") -> dict:
    key = sport_key or discover_world_cup_key()
    events, meta = _get(f"/sports/{key}/odds", regions=region,
                        markets="h2h,totals", oddsFormat="decimal")
    print(f"[i] Odds API: {len(events)} events, ~{meta['remaining']} requests remaining this month")

    matches = []
    for ev in events:
        if not ev.get("bookmakers"):
            continue
        home, away = ev["home_team"], ev["away_team"]
        m = {
            "id": ev["id"][:8],
            "kickoff": ev.get("commence_time", ""),
            "home": home, "away": away,
            "markets": {}, "adjustments": {"notes": []},
        }
        # Median across bookmakers = a robust consensus price.
        h2h: dict[str, list[float]] = {"home": [], "draw": [], "away": []}
        totals: dict[str, list[float]] = {"over": [], "under": []}
        for bk in ev["bookmakers"]:
            for mkt in bk.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        slot = "home" if o["name"] == home else "away" if o["name"] == away else "draw"
                        h2h[slot].append(o["price"])
                elif mkt["key"] == "totals":
                    for o in mkt["outcomes"]:
                        if o.get("point") == 2.5:
                            totals[o["name"].lower()].append(o["price"])
        if all(h2h.values()):
            m["markets"]["1x2"] = {k: _median(v) for k, v in h2h.items()}
        if all(totals.values()):
            m["markets"]["over_under_2_5"] = {k: _median(v) for k, v in totals.items()}
        if m["markets"]:
            matches.append(m)

    return {"date": date.today().isoformat(),
            "bookmaker": f"market consensus ({region} region, median of books)",
            "matches": matches}


def merge_sheet_adjustments(api_data: dict, sheet_data: dict) -> dict:
    """Overlay your sheet's adjustments/notes onto API odds, matched by team names."""
    by_teams = {(m["home"].lower(), m["away"].lower()): m for m in api_data["matches"]}
    for sm in sheet_data["matches"]:
        m = by_teams.get((sm["home"].lower(), sm["away"].lower()))
        if m and sm.get("adjustments"):
            notes = m["adjustments"].get("notes", []) + sm["adjustments"].get("notes", [])
            m["adjustments"].update(sm["adjustments"])
            m["adjustments"]["notes"] = notes
    return api_data


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
