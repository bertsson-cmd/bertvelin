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

SCHEDULE_FEED = "https://fixturedownload.com/feed/json/fifa-world-cup-2026"


def _fetch_schedule() -> list[dict]:
    """Full official schedule with stadiums, keyless. Source: fixturedownload.com.
    Every match (group + knockout) carries a Location like 'Mexico City Stadium'."""
    data = _http_json(SCHEDULE_FEED)
    return data if isinstance(data, list) else []


def _attach_venues_from_schedule(matches: list[dict]) -> int:
    """Primary venue source. Matches by teams AND kickoff proximity, because
    teams play at different stadiums in different rounds. Returns #resolved."""
    from .teams import team_match, normalize as _norm
    try:
        schedule = _fetch_schedule()
        print(f"[i] Venue layer: schedule feed returned {len(schedule)} fixtures")
    except Exception as e:
        print(f"[!] Venue layer: schedule feed failed ({e})")
        return 0
    if not schedule:
        return 0

    venues = json.load(open(os.path.join(DATA_DIR, "venues.json")))["venues"]

    def find_venue(text: str):
        t = _norm(text)
        return next((v for v in venues if any(_norm(k) in t for k in v["match"])), None)

    def kickoff_ts(m):
        try:
            return datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    def sched_ts(row):
        try:
            return datetime.fromisoformat(
                row.get("DateUtc", "").replace(" ", "T").replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    resolved = 0
    for m in matches:
        if m.get("venue_info"):
            continue
        mts = kickoff_ts(m)
        best = None
        for row in schedule:
            if not (team_match(m["home"], row.get("HomeTeam", "")) and
                    team_match(m["away"], row.get("AwayTeam", ""))):
                continue
            sts = sched_ts(row)
            # same fixture can recur across rounds -> require kickoff within 36h
            if mts is not None and sts is not None and abs(mts - sts) > 36 * 3600:
                continue
            best = row
            break
        if not best:
            print(f"[i] Venue layer: no schedule row for {m['home']} vs {m['away']} "
                  f"(kickoff {m.get('kickoff','?')})")
            continue
        v = find_venue(best.get("Location", ""))
        if v:
            m["venue_info"] = v
            m["venue"] = v["name"]
            resolved += 1
            print(f"[i] Venue matched (schedule): {m['home']} vs {m['away']} -> "
                  f"{v['name']} [feed said {best.get('Location','')!r}]")
            if v["altitude"] >= 1500:
                _note(m, f"Played at altitude ({v['altitude']}m, {v['name']}) — "
                         "favours the acclimatised side, typically the CONCACAF host")
        else:
            print(f"[i] Venue layer: schedule location not recognized: {best.get('Location','')!r} "
                  f"for {m['home']} vs {m['away']} — add it to data/venues.json match keywords")
    return resolved



def attach_venues(matches: list[dict]) -> None:
    """Resolve stadiums. Primary: the keyless fixturedownload schedule feed
    (football-data sends no stadium for World Cup fixtures — its venue field
    is empty and the area fallback is just 'World'). Secondary: football-data,
    kept only in case the feed is down AND they start populating venues."""
    print(f"[i] Venue layer: checking {len(matches)} match(es)")

    if not matches:
        print("[i] Venue layer: no matches loaded, so weather cannot run.")
        return

    resolved = _attach_venues_from_schedule(matches)
    if all(m.get("venue_info") for m in matches):
        print(f"[i] Venue layer: all {resolved} venue(s) resolved from schedule feed.")
        return

    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key:
        print("[i] FOOTBALL_DATA_KEY not set — skipping football-data venue fallback.")
        return

    print("[i] FOOTBALL_DATA_KEY is set — fetching football-data.org fixtures for venue lookup.")

    try:
        today = datetime.now(timezone.utc).date()
        fixtures = _http_json(
            f"https://api.football-data.org/v4/competitions/WC/matches"
            f"?dateFrom={today}&dateTo={today + timedelta(days=2)}",
            headers={"X-Auth-Token": key},
        ).get("matches", [])
        print(f"[i] football-data.org returned {len(fixtures)} fixture(s) for venue lookup.")
    except Exception as e:
        print(f"[!] football-data.org failed ({e}) — skipping venues/weather.")
        return

    venues = json.load(open(os.path.join(DATA_DIR, "venues.json")))["venues"]

    from .teams import normalize as _norm

    def find_venue(venue_text: str) -> dict | None:
        t = _norm(venue_text)            # lowercases, strips accents/punctuation
        return next((v for v in venues if any(_norm(k) in t for k in v["match"])), None)

    from .teams import team_match   # alias-aware: Czechia/Czech Republic, Korea Republic/South Korea

    for m in matches:
        matched_fixture = False
        matched_venue = False

        for f in fixtures:
            ht = f.get("homeTeam", {}).get("name", "")
            at = f.get("awayTeam", {}).get("name", "")
            if team_match(m["home"], ht) and team_match(m["away"], at):
                matched_fixture = True
                venue_text = f.get("venue", "") or f.get("area", {}).get("name", "")
                v = find_venue(venue_text)
                if v:
                    matched_venue = True
                    m["venue_info"] = v
                    m["venue"] = v["name"]
                    print(f"[i] Venue matched: {m['home']} vs {m['away']} -> {v['name']}")
                    if v["altitude"] >= 1500:
                        _note(m, f"Played at altitude ({v['altitude']}m, {v['name']}) — "
                                 "favours the acclimatised side, typically the CONCACAF host")
                else:
                    print(
                        f"[i] Fixture matched but venue was not recognized for "
                        f"{m['home']} vs {m['away']} | football-data venue text: {venue_text!r}"
                    )
                break

        if not matched_fixture:
            fd_names = ", ".join(
                f"{f.get('homeTeam',{}).get('name','?')} v {f.get('awayTeam',{}).get('name','?')}"
                for f in fixtures) or "(none)"
            print(
                f"[i] No football-data fixture match for {m['home']} vs {m['away']} — "
                f"weather skipped. football-data offered: {fd_names}"
            )
        elif not matched_venue:
            print(
                f"[i] No usable venue_info for {m['home']} vs {m['away']} — "
                "weather skipped for this match."
            )


def _initials(s: str) -> str:
    return "".join(w[0] for w in re.findall(r"\w+", s))


# --------------------------------------------------------------- 2. weather

def attach_weather(matches: list[dict]) -> None:
    """Open-Meteo forecast at kickoff + rule-based football reasoning."""
    print(f"[i] Weather layer: checking {len(matches)} match(es)")

    weather_checked = 0
    for m in matches:
        v = m.get("venue_info")
        if not v:
            print(f"[i] Weather skipped: no venue_info for {m['home']} vs {m['away']}")
            continue
        if v["roof"]:
            print(f"[i] Weather neutral: {v['name']} has a roof for {m['home']} vs {m['away']}")
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
        weather_checked += 1
        print(f"[i] Weather loaded: {m['home']} vs {m['away']} at {v['name']}: {summary}")
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

    print(f"[i] Weather layer complete: loaded weather for {weather_checked} match(es).")


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




# -------------------------------------------------------------- 5. form goals

def attach_form_goals(matches: list[dict]) -> None:
    """Average total goals/game from each team's last 10 matches across ALL
    competitions (qualifiers, friendlies, Nations League, WC) — far more stable
    than the 1-2 games available from the WC alone during the group stage.

    Total goals = home + away per match (both teams). One fixture-list call to
    get team IDs, then one /teams/{id}/matches call per team (cached, rate-paced).

    If /teams/{id}/matches is NOT on the free tier, the per-team call returns an
    error which is logged loudly and that team is skipped — the run continues.

    Nudge scale (within the global +/-5pt cap):
      combined avg >= 3.2  -> +2pt over     combined avg <= 1.8  -> +2pt under
      combined avg >= 2.8  -> +1pt over     combined avg <= 2.2  -> +1pt under
      2.2 < avg < 2.8       -> no nudge (too close to the 2.5 line)
    """
    import time

    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key:
        print("[i] Form goals: FOOTBALL_DATA_KEY not set — skipping.")
        return

    from .teams import team_match

    # Step 1: get team IDs from the upcoming WC fixtures (free-tier call)
    try:
        today = datetime.now(timezone.utc).date()
        resp = _http_json(
            f"https://api.football-data.org/v4/competitions/WC/matches"
            f"?dateFrom={today}&dateTo={today + timedelta(days=2)}",
            headers={"X-Auth-Token": key})
        fixtures = resp.get("matches", [])
    except Exception as e:
        print(f"[!] Form goals: fixture fetch failed ({e}) — skipping.")
        return

    team_id_map: dict[str, int] = {}
    for f in fixtures:
        for side in ("homeTeam", "awayTeam"):
            t = f.get(side, {})
            if t.get("id") and t.get("name"):
                team_id_map[t["name"]] = t["id"]
    print(f"[i] Form goals: {len(team_id_map)} team IDs from today's fixtures.")

    def find_id(name: str):
        for tname, tid in team_id_map.items():
            if team_match(name, tname):
                return tid
        return None

    # Step 2: per-team last-10 average (cached). Returns (avg, n_games).
    form_cache: dict[int, tuple] = {}
    endpoint_blocked = {"flag": False}

    def get_form(team_id: int, label: str):
        if team_id in form_cache:
            return form_cache[team_id]
        if endpoint_blocked["flag"]:
            return (None, 0)
        try:
            time.sleep(0.4)   # stay inside the rate limit
            data = _http_json(
                f"https://api.football-data.org/v4/teams/{team_id}/matches"
                f"?status=FINISHED&limit=10",
                headers={"X-Auth-Token": key})
            totals = []
            for rm in data.get("matches", []):
                ft = rm.get("score", {}).get("fullTime", {})
                h, a = ft.get("home"), ft.get("away")
                if h is not None and a is not None:
                    totals.append(int(h) + int(a))
            # keep only the 10 most recent that had scores
            totals = totals[-10:]
            avg = round(sum(totals) / len(totals), 1) if totals else None
            form_cache[team_id] = (avg, len(totals))
            print(f"[i] Form goals: {label} last {len(totals)} games "
                  f"avg {avg if avg is not None else 'n/a'} total goals.")
        except Exception as e:
            msg = str(e)
            # 403/restricted = endpoint not on this plan: stop trying, log once
            if "403" in msg or "forbidden" in msg.lower() or "restricted" in msg.lower():
                endpoint_blocked["flag"] = True
                print(f"[!] Form goals: /teams/{{id}}/matches is NOT available on "
                      f"this football-data plan ({msg}). Goals form disabled for "
                      f"this run. Upgrade tier or rely on WC-only data.")
            else:
                print(f"[!] Form goals: {label} (id {team_id}) fetch failed ({msg})")
            form_cache[team_id] = (None, 0)
        return form_cache[team_id]

    resolved = 0
    for m in matches:
        h_id, a_id = find_id(m["home"]), find_id(m["away"])
        if not h_id or not a_id:
            miss = [t for t, i in ((m["home"], h_id), (m["away"], a_id)) if not i]
            print(f"[i] Form goals: no team ID for {', '.join(miss)} — skipping fixture.")
            continue

        h_avg, h_n = get_form(h_id, m["home"])
        a_avg, a_n = get_form(a_id, m["away"])
        if h_avg is None or a_avg is None:
            print(f"[i] Form goals: insufficient data for {m['home']} or {m['away']} — skip.")
            continue

        combined = round((h_avg + a_avg) / 2, 1)
        _note(m,
              f"Form (last 10): {m['home']} avg {h_avg:.1f} total goals/game "
              f"({h_n}g); {m['away']} avg {a_avg:.1f} ({a_n}g); combined {combined:.1f}")

        if "over_under_2_5" not in m.get("markets", {}):
            continue

        if combined >= 3.2:
            _note(m, f"→ High-scoring form ({combined:.1f} goals/game) — nudge toward over 2.5")
            _nudge(m, "over_under_2_5", "over", 0.02)
        elif combined >= 2.8:
            _note(m, f"→ Above-average form ({combined:.1f} goals/game) — small nudge toward over 2.5")
            _nudge(m, "over_under_2_5", "over", 0.01)
        elif combined <= 1.8:
            _note(m, f"→ Low-scoring form ({combined:.1f} goals/game) — nudge toward under 2.5")
            _nudge(m, "over_under_2_5", "under", 0.02)
        elif combined <= 2.2:
            _note(m, f"→ Below-average form ({combined:.1f} goals/game) — small nudge toward under 2.5")
            _nudge(m, "over_under_2_5", "under", 0.01)
        else:
            _note(m, f"→ Average form ({combined:.1f} goals/game) — no over/under nudge applied")
        resolved += 1

    print(f"[i] Form goals: notes applied to {resolved}/{len(matches)} fixture(s).")


# ------------------------------------------------------------- entry point

def enrich(matches: list[dict]) -> None:
    print(f"[i] Enrichment layer started for {len(matches)} match(es).")
    attach_venues(matches)
    attach_weather(matches)
    attach_movement(matches)
    attach_form_goals(matches)
    attach_ai_news(matches)
    print("[i] Enrichment layer complete.")
