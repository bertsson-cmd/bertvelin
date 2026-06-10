"""
Automatic enrichment — turns raw odds into odds + reasoning, no typing.

Four independent layers; each fails soft (skips with a console note):

1. VENUES   football-data.org (free key) maps each fixture to its stadium.
2. WEATHER  Open-Meteo (free, no key) forecasts conditions at kickoff;
            rule-based notes & small adjustments (heat, wind, rain, altitude).
3. MOVEMENT data/history.json (committed back by the daily Action) tracks
            yesterday's prices; significant moves become notes & nudges.
            Market moves are the single most information-rich free signal —
            they're how team news shows up without reading any news.
4. AI NEWS  optional: with an ANTHROPIC_API_KEY, asks Claude (with web
            search) for injury/team-news per match, returned as structured
            adjustments + readable reasoning.

All adjustments funnel through the same ±5-point cap in odds.build_legs.
"""

from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _http_json(url: str, headers: dict | None = None, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": "wc26-analyzer", **(headers or {})})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _note(match: dict, text: str) -> None:
    match.setdefault("adjustments", {}).setdefault("notes", []).append(text)


def _nudge(match: dict, market: str, outcome: str, delta: float) -> None:
    adj = match.setdefault("adjustments", {}).setdefault(market, {})
    adj[outcome] = adj.get(outcome, 0.0) + delta


# ---------------------------------------------------------------- 1. venues

def attach_venues(matches: list[dict]) -> None:
    """Match fixtures to venues via football-data.org (FOOTBALL_DATA_KEY)."""
    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key:
        print("[i] FOOTBALL_DATA_KEY not set — skipping venue/weather layer.")
        return
    try:
        today = datetime.now(timezone.utc).date()
        fixtures = _http_json(
            f"https://api.football-data.org/v4/competitions/WC/matches"
            f"?dateFrom={today}&dateTo={today + timedelta(days=2)}",
            headers={"X-Auth-Token": key},
        ).get("matches", [])
    except Exception as e:
        print(f"[!] football-data.org failed ({e}) — skipping venues.")
        return

    venues = json.load(open(os.path.join(DATA_DIR, "venues.json")))["venues"]

    def find_venue(venue_text: str) -> dict | None:
        t = (venue_text or "").lower()
        return next((v for v in venues if any(k in t for k in v["match"])), None)

    def team_match(a: str, b: str) -> bool:
        a, b = a.lower(), b.lower()
        return a in b or b in a or _initials(a) == _initials(b)

    for m in matches:
        for f in fixtures:
            ht = f.get("homeTeam", {}).get("name", "")
            at = f.get("awayTeam", {}).get("name", "")
            if team_match(m["home"], ht) and team_match(m["away"], at):
                v = find_venue(f.get("venue", "") or f.get("area", {}).get("name", ""))
                if v:
                    m["venue_info"] = v
                    m["venue"] = v["name"]
                    if v["altitude"] >= 1500:
                        _note(m, f"Played at altitude ({v['altitude']}m, {v['name']}) — "
                                 "favours the acclimatised side, typically the CONCACAF host")
                break


def _initials(s: str) -> str:
    return "".join(w[0] for w in re.findall(r"\w+", s))


# --------------------------------------------------------------- 2. weather

def attach_weather(matches: list[dict]) -> None:
    """Open-Meteo forecast at kickoff + rule-based football reasoning."""
    for m in matches:
        v = m.get("venue_info")
        if not v:
            continue
        if v["roof"]:
            _note(m, f"{v['name']} has a roof — weather neutral")
            continue
        try:
            kickoff = datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))
            day = kickoff.date().isoformat()
            wx = _http_json(
                "https://api.open-meteo.com/v1/forecast?"
                + urllib.parse.urlencode({
                    "latitude": v["lat"], "longitude": v["lon"],
                    "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m",
                    "start_date": day, "end_date": day, "timezone": "UTC",
                }))
            hours = wx["hourly"]["time"]
            idx = min(range(len(hours)),
                      key=lambda i: abs(datetime.fromisoformat(hours[i] + "+00:00") - kickoff))
            temp = wx["hourly"]["temperature_2m"][idx]
            hum = wx["hourly"]["relative_humidity_2m"][idx]
            rain = wx["hourly"]["precipitation_probability"][idx]
            wind = wx["hourly"]["wind_speed_10m"][idx]
        except Exception as e:
            print(f"[!] weather fetch failed for {m['id']} ({e})")
            continue

        summary = f"{temp:.0f}°C, {hum:.0f}% humidity, wind {wind:.0f} km/h, rain {rain:.0f}%"
        _note(m, f"Kickoff forecast at {v['name']}: {summary}")

        if temp >= 30 and hum >= 55:
            _note(m, "→ Severe heat+humidity: tempo drops, more draws/unders historically; "
                     "small nudge toward draw and under 2.5")
            _nudge(m, "1x2", "draw", 0.015)
            _nudge(m, "over_under_2_5", "under", 0.02)
        elif temp >= 32:
            _note(m, "→ Extreme heat: slight nudge toward under 2.5")
            _nudge(m, "over_under_2_5", "under", 0.015)
        if wind >= 35:
            _note(m, "→ Strong wind disrupts crossing/long passing; slight under nudge")
            _nudge(m, "over_under_2_5", "under", 0.015)
        if rain >= 70:
            _note(m, "→ Likely rain: greasy surface, marginally more goal chaos; no adjustment, just awareness")


# -------------------------------------------------------------- 3. movement

HISTORY_PATH = os.path.join(DATA_DIR, "history.json")


def attach_movement(matches: list[dict]) -> None:
    """Compare today's 1x2 prices with the last run; note & nudge big moves."""
    try:
        history = json.load(open(HISTORY_PATH))
    except Exception:
        history = {}

    for m in matches:
        key = f"{m['home']} v {m['away']}"
        prev = history.get(key, {}).get("1x2")
        cur = m.get("markets", {}).get("1x2")
        if prev and cur:
            for outcome in ("home", "draw", "away"):
                if outcome in prev and outcome in cur:
                    dp = 1 / cur[outcome] - 1 / prev[outcome]  # implied prob change
                    if dp >= 0.03:
                        side = {"home": m["home"], "away": m["away"], "draw": "the draw"}[outcome]
                        _note(m, f"Market moved toward {side} since last run "
                                 f"({prev[outcome]:.2f} → {cur[outcome]:.2f}). Sharp moves "
                                 "usually mean team news; following the move, small nudge.")
                        _nudge(m, "1x2", outcome, min(dp / 2, 0.02))
        if cur:
            history[key] = {"1x2": cur, "date": datetime.now(timezone.utc).isoformat()}

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=1)


# ---------------------------------------------------------- 4. AI news desk

AI_PROMPT = """You are a cautious football analyst. Today is {date}.
For each fixture below, use web search to check the latest team news: confirmed
injuries, suspensions, likely heavy rotation, manager quotes, anything from the
last 72 hours that materially affects the result probability.

Fixtures:
{fixtures}

Respond with ONLY a JSON array, no markdown fences, no preamble. One object per
fixture that has noteworthy news (omit fixtures with nothing notable):
[{{"home": "...", "away": "...",
   "reasoning": ["one short readable bullet per finding, with what it implies"],
   "adjustments": {{"1x2": {{"home": 0.0, "draw": 0.0, "away": 0.0}}}}}}]

Adjustment rules: absolute probability points, conservative, each within
-0.03..0.03, and 0 unless the news is concrete (named player, confirmed status).
Markets already price public news quickly, so most days most values are 0."""


def attach_ai_news(matches: list[dict], model: str = "claude-sonnet-4-6") -> None:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("[i] ANTHROPIC_API_KEY not set — skipping AI news layer.")
        return
    fixtures = "\n".join(f"- {m['home']} vs {m['away']} ({m.get('kickoff','')})" for m in matches)
    try:
        resp = _http_json(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            payload={
                "model": model, "max_tokens": 3000,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
                "messages": [{"role": "user", "content": AI_PROMPT.format(
                    date=datetime.now(timezone.utc).date(), fixtures=fixtures)}],
            })
        text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
        items = json.loads(re.sub(r"```json|```", "", text).strip())
    except Exception as e:
        print(f"[!] AI news layer failed ({e}) — continuing without it.")
        return

    for item in items:
        for m in matches:
            if item.get("home", "").lower() in m["home"].lower() and \
               item.get("away", "").lower() in m["away"].lower():
                for line in item.get("reasoning", []):
                    _note(m, f"News desk: {line}")
                for market, omap in item.get("adjustments", {}).items():
                    for outcome, delta in omap.items():
                        d = max(-0.03, min(0.03, float(delta)))
                        if d:
                            _nudge(m, market, outcome, d)


# ------------------------------------------------------------- entry point

def enrich(matches: list[dict]) -> None:
    attach_venues(matches)
    attach_weather(matches)
    attach_movement(matches)
    attach_ai_news(matches)
