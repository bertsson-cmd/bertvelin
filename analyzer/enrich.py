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



# --------------------------------------------------------- 4b. AI intelligence
# Brave Search fetches live news snippets per fixture.
# Groq (Llama 3.3 70B) reads those snippets and produces structured probability
# adjustments. One Brave search + one Groq call per run. No rate-limit drama.

GROQ_INTELLIGENCE_PROMPT = """You are a sharp, conservative football intelligence analyst.
Today is {date}. The World Cup 2026 is in progress.

Today's fixtures with fair market probabilities (bookmaker margin removed):
{fixtures}

Your job: for each fixture, use your knowledge of these teams — squad depth,
injury history, manager rotation patterns, tactical tendencies, motivation
factors, head-to-head patterns — to produce STRUCTURED, CALIBRATED probability
adjustments. Only include a fixture where you have genuine knowledge that
meaningfully shifts the fair probability. Be conservative: the market already
prices most public information. An empty array [] is correct when you have
nothing material to add.

Respond with ONLY a JSON array, no markdown, no preamble:
[
  {{
    "home": "exact home team name from fixtures",
    "away": "exact away team name from fixtures",
    "intelligence": [
      "one concrete readable sentence per finding and its implication"
    ],
    "adjustments": {{
      "1x2": {{"home": 0.0, "draw": 0.0, "away": 0.0}},
      "over_under_2_5": {{"over": 0.0, "under": 0.0}}
    }},
    "confidence": "high | medium | low"
  }}
]

Adjustment rules:
- Absolute probability point changes (0.04 = +4 percentage points)
- Each value within -0.05 to +0.05
- 0.0 unless you have concrete specific knowledge
- Confidence: high = well established fact, medium = strong pattern, low = tendency
- Known injury-prone key player: small downgrade when primary goal threat
- Manager known for rotation: slight downgrade in dead-rubber group games
- Historically low-scoring fixture pattern: nudge toward under
- Must-win vs already qualified: boost must-win team slightly

If tournament performance data is provided, use it to calibrate confidence:
- Actual hit rate well below estimate → market has been efficient, be more conservative
- Specific market types consistently missing → reduce adjustments on those markets
- Strong positive units → model and market reasonably aligned
{tournament_context}"""




def attach_ai_intelligence(matches: list[dict],
                           scoreboard: dict | None = None) -> None:
    """Groq-only intelligence layer (Llama 3.3 70B, free tier, no card required).

    Analyses fixtures from training knowledge — squad depth, manager rotation
    patterns, injury history, tactical tendencies, motivation factors.
    Receives tournament scoreboard so Groq can self-calibrate based on what
    markets have actually been right/wrong about during this tournament.
    One call per day. 14,400 req/day free limit on console.groq.com.
    Falls soft on any error — math picks still run if this layer fails.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        print("[i] AI intelligence: GROQ_API_KEY not set — skipping.")
        return

    from .teams import team_match

    # ---- Build fixture summaries with fair probs ----
    fixture_lines = []
    for m in matches:
        h2h = m.get("markets", {}).get("1x2", {})
        ou  = m.get("markets", {}).get("over_under_2_5", {})
        if not h2h:
            continue
        total_inv = sum(1 / v for v in h2h.values() if v)
        def fp(o): return round((1 / o) / total_inv, 3) if o else 0
        line = (f"- {m['home']} vs {m['away']}"
                f" | home {fp(h2h.get('home',0)):.0%}"
                f" draw {fp(h2h.get('draw',0)):.0%}"
                f" away {fp(h2h.get('away',0)):.0%}")
        if ou:
            ou_inv = sum(1 / v for v in ou.values() if v)
            def fpo(o): return round((1 / o) / ou_inv, 3) if o else 0
            line += (f" | over {fpo(ou.get('over',0)):.0%}"
                     f" under {fpo(ou.get('under',0)):.0%}")
        fixture_lines.append(line)

    if not fixture_lines:
        return

    print(f"[i] AI intelligence: analysing {len(fixture_lines)} fixture(s) with Groq...")

    tournament_context = ""
    if scoreboard and scoreboard.get("n", 0) > 0:
        n   = scoreboard["n"]
        actual   = scoreboard.get("actual_rate", 0)
        estimated = scoreboard.get("est_rate", 0)
        units     = scoreboard.get("units", 0)
        history   = scoreboard.get("history", [])
        market_stats: dict[str, dict] = {}
        for rec in history:
            for leg in rec.get("legs", []):
                mkt = leg.get("market", "")
                fam = ("result"  if ("1x2" in mkt or "double_chance" in mkt or "handicap" in mkt)
                       else "totals" if "over_under" in mkt
                       else "btts"   if "btts" in mkt
                       else "other")
                ms = market_stats.setdefault(fam, {"n": 0, "wins": 0})
                ms["n"] += 1
                if leg.get("won"):
                    ms["wins"] += 1
        mkt_lines = [
            f"  {fam}: {ms['wins']}/{ms['n']} legs won ({ms['wins']/ms['n']:.0%})"
            for fam, ms in market_stats.items() if ms["n"] > 0]
        gap = actual - estimated
        calibration = ("market more accurate than estimated — be conservative"
                       if gap < -0.05 else
                       "model estimates tracking well" if abs(gap) <= 0.05 else
                       "model slightly overestimating — consider smaller nudges")
        tournament_context = (
            f"\n\nTOURNAMENT PERFORMANCE ({n} slips settled):"
            f"\n  {scoreboard.get('wins',0)}/{n} slips won "
            f"({actual:.0%} actual vs {estimated:.0%} estimated)"
            f"\n  Units: {units:+.2f} | {calibration}"
            + (f"\n  By market:\n" + "\n".join(mkt_lines) if mkt_lines else ""))
        print(f"[i] AI intelligence: tournament context included ({n} settled slips)")

    prompt = GROQ_INTELLIGENCE_PROMPT.format(
        date=datetime.now(timezone.utc).date(),
        fixtures="\n".join(fixture_lines),
        tournament_context=tournament_context)

    try:
        resp = _http_json(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}",
                     "Content-Type": "application/json"},
            payload={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2000,
            })
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not text.strip():
            print("[i] AI intelligence: empty Groq response — skipping.")
            return
        clean = re.sub(r"```json|```", "", text).strip()
        if not clean or clean in ("[]", "[ ]"):
            print("[i] AI intelligence: no material news found today.")
            return
        items = json.loads(clean)
        if not isinstance(items, list):
            print("[!] AI intelligence: unexpected response format — skipping.")
            return
    except json.JSONDecodeError as e:
        print(f"[!] AI intelligence: JSON parse failed ({e}) — skipping.")
        return
    except Exception as e:
        print(f"[!] AI intelligence: Groq call failed ({e}) — skipping.")
        return

    # ---- Step 4: apply adjustments ----
    applied = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        matched = next((m for m in matches
                        if team_match(item.get("home", ""), m["home"])
                        and team_match(item.get("away", ""), m["away"])), None)
        if not matched:
            print(f"[i] AI intelligence: fixture not matched — "
                  f"{item.get('home')} vs {item.get('away')}")
            continue

        confidence = item.get("confidence", "medium").lower()
        cap = {"high": 0.05, "medium": 0.03, "low": 0.015}.get(confidence, 0.03)

        for line in item.get("intelligence", []):
            conf_tag = f" [{confidence}]" if confidence != "medium" else ""
            _note(matched, f"AI\U0001f916{conf_tag}: {line}")

        adj_applied = []
        for market, outcomes in item.get("adjustments", {}).items():
            for outcome, delta in (outcomes or {}).items():
                if delta and abs(float(delta)) >= 0.005:
                    d = max(-cap, min(cap, float(delta)))
                    _nudge(matched, market, outcome, d)
                    adj_applied.append(f"{market}/{outcome}: {d:+.3f}")

        if adj_applied:
            print(f"[i] AI intelligence: {matched['home']} vs {matched['away']} "
                  f"({confidence}) — {', '.join(adj_applied)}")
            applied += 1
        else:
            print(f"[i] AI intelligence: {matched['home']} vs {matched['away']} "
                  f"— news found, no adjustment warranted.")

    print(f"[i] AI intelligence: adjustments applied to {applied}/{len(matches)} fixture(s).")



# -------------------------------------------------------------- 5. form goals

def attach_form_goals(matches: list[dict]) -> None:
    """Average total goals/game from each team's World Cup matches so far.

    IMPORTANT — free-tier reality: football-data's TIER_ONE plan does NOT
    include national-team match history (the /teams/{id}/matches endpoint
    returns count:0 for international sides). The only goals data available
    on the free tier is the WC competition feed itself. So this layer builds
    form from finished WC 2026 matches via /competitions/WC/matches, which
    the free tier covers (same source settlement uses).

    Consequence: no data on matchday 1 (no WC games played yet), 1 game of
    data on matchday 2, 2 by the end of groups, 3+ in the knockouts. Each
    note states how many games it is based on so you can weight it. To get
    pre-tournament form (qualifiers/friendlies) you would need a paid
    football-data tier or a different data source.

    Total goals = home + away per match. Nudge scale (within the ±5pt cap):
      combined avg >= 3.2  -> +2pt over     combined avg <= 1.8  -> +2pt under
      combined avg >= 2.8  -> +1pt over     combined avg <= 2.2  -> +1pt under
      2.2 < avg < 2.8       -> no nudge
    """
    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key:
        print("[i] Form goals: FOOTBALL_DATA_KEY not set — skipping.")
        return

    from .teams import team_match

    try:
        wc = _http_json(
            "https://api.football-data.org/v4/competitions/WC/matches?status=FINISHED",
            headers={"X-Auth-Token": key})
        finished = wc.get("matches", [])
        print(f"[i] Form goals: {len(finished)} finished WC matches available "
              f"(free-tier WC feed).")
    except Exception as e:
        print(f"[!] Form goals: WC feed fetch failed ({e}) — skipping.")
        return

    if not finished:
        print("[i] Form goals: no finished WC matches yet — goals form will "
              "appear once teams have played (matchday 2 onward).")
        return

    # team_id -> list of total goals; plus id -> name for matching
    goals: dict[int, list[int]] = {}
    names: dict[int, str] = {}
    for fm in finished:
        ft = fm.get("score", {}).get("fullTime", {})
        h, a = ft.get("home"), ft.get("away")
        if h is None or a is None:
            continue
        tot = int(h) + int(a)
        for side in ("homeTeam", "awayTeam"):
            t = fm.get(side, {})
            if t.get("id"):
                goals.setdefault(t["id"], []).append(tot)
                names[t["id"]] = t.get("name", str(t["id"]))

    def team_goals(name: str):
        for tid, tname in names.items():
            if team_match(name, tname):
                return goals.get(tid, [])
        return []

    resolved = 0
    for m in matches:
        hg = team_goals(m["home"])
        ag = team_goals(m["away"])
        if not hg or not ag:
            miss = [t for t, g in ((m["home"], hg), (m["away"], ag)) if not g]
            print(f"[i] Form goals: no WC games yet for {', '.join(miss)} — skip fixture.")
            continue

        h_avg = round(sum(hg) / len(hg), 1)
        a_avg = round(sum(ag) / len(ag), 1)
        combined = round((h_avg + a_avg) / 2, 1)
        print(f"[i] Form goals: {m['home']} {h_avg} ({len(hg)}g), "
              f"{m['away']} {a_avg} ({len(ag)}g), combined {combined}")

        _note(m,
              f"WC form: {m['home']} avg {h_avg:.1f} total goals/game "
              f"({len(hg)}g); {m['away']} avg {a_avg:.1f} ({len(ag)}g); "
              f"combined {combined:.1f}")

        if "over_under_2_5" not in m.get("markets", {}):
            continue

        if combined >= 3.2:
            _note(m, f"→ High-scoring WC form ({combined:.1f}/game) — nudge toward over 2.5")
            _nudge(m, "over_under_2_5", "over", 0.02)
        elif combined >= 2.8:
            _note(m, f"→ Above-average WC form ({combined:.1f}/game) — small nudge toward over 2.5")
            _nudge(m, "over_under_2_5", "over", 0.01)
        elif combined <= 1.8:
            _note(m, f"→ Low-scoring WC form ({combined:.1f}/game) — nudge toward under 2.5")
            _nudge(m, "over_under_2_5", "under", 0.02)
        elif combined <= 2.2:
            _note(m, f"→ Below-average WC form ({combined:.1f}/game) — small nudge toward under 2.5")
            _nudge(m, "over_under_2_5", "under", 0.01)
        else:
            _note(m, f"→ Average WC form ({combined:.1f}/game) — no over/under nudge")
        resolved += 1

    print(f"[i] Form goals: notes applied to {resolved}/{len(matches)} fixture(s).")


# ------------------------------------------------------------- entry point

def enrich(matches: list[dict], scoreboard: dict | None = None) -> None:
    print(f"[i] Enrichment layer started for {len(matches)} match(es).")
    attach_venues(matches)
    attach_weather(matches)
    attach_movement(matches)
    attach_form_goals(matches)
    attach_ai_intelligence(matches, scoreboard=scoreboard)
    print("[i] Enrichment layer complete.")
