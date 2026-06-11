"""The Odds API source (the-odds-api.com) -- fully automatic odds, no daily typing.

This version:
  - Uses a 07:00 Reykjavik -> 07:00 Reykjavik daily window.
  - Strongly prefers the known FIFA World Cup sport key: soccer_fifa_world_cup.
  - Uses a wider default region set: us,uk,eu,au.
  - Fetches base markets: h2h, totals, spreads.
  - Optionally fetches extra per-event markets with --extra-markets:
      alternate_totals, alternate_spreads, btts, double_chance.
  - Keeps a defensive local time-window filter even though the API request
    already includes commenceTimeFrom/commenceTimeTo.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = "https://api.the-odds-api.com/v4"

# Keep all football total-goals lines from 0.5 through 6.5.
TOTAL_POINTS = {x + 0.5 for x in range(0, 7)}

# These are the cheaper/base markets fetched from the sport odds endpoint.
BASE_MARKETS = "h2h,totals,spreads"

# These are attempted only when --extra-markets is passed.
# They may be unavailable depending on sport, bookmaker, API plan, or event.
EXTRA_EVENT_MARKETS = "alternate_totals,alternate_spreads,btts,double_chance"

# Prefer the known World Cup key before doing fuzzy discovery.
PREFERRED_WORLD_CUP_KEY = "soccer_fifa_world_cup"


def _get(path: str, **params) -> tuple[object, dict]:
    params["apiKey"] = os.environ.get("ODDS_API_KEY", "")
    if not params["apiKey"]:
        raise RuntimeError("Set the ODDS_API_KEY environment variable.")

    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "wc26-analyzer"})

    with urllib.request.urlopen(req, timeout=30) as resp:
        remaining = resp.headers.get("x-requests-remaining", "?")
        return json.loads(resp.read().decode("utf-8")), {"remaining": remaining}


def discover_world_cup_key() -> str:
    """Find the FIFA World Cup sport key, preferring the known official key."""
    sports, _ = _get("/sports", all="true")

    for s in sports:
        if s.get("key") == PREFERRED_WORLD_CUP_KEY:
            return PREFERRED_WORLD_CUP_KEY

    candidates = [
        s for s in sports
        if "world_cup" in s.get("key", "")
        and "soccer" in s.get("key", "")
        and "winner" not in s.get("key", "")
    ]

    if candidates:
        print("[i] World Cup sport-key candidates:")
        for s in candidates:
            print(f"    - {s.get('key')} ({s.get('title', 'untitled')})")
        return candidates[0]["key"]

    raise RuntimeError(
        "No FIFA World Cup sport key found. Inspect /v4/sports and pass "
        "--sport-key manually if The Odds API changed the key."
    )


def _daily_window_7am_reykjavik(now: datetime | None = None) -> tuple[str, str, date]:
    """
    Return the daily betting window:
        07:00 Reykjavik today -> 07:00 Reykjavik tomorrow.

    The window is anchored to the Reykjavik calendar day, not to the exact
    minute the GitHub Action starts.
    """
    tz = ZoneInfo("Atlantic/Reykjavik")
    now_local = (now or datetime.now(tz)).astimezone(tz)

    start_local = datetime.combine(now_local.date(), time(7, 0), tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    def iso_z(dt: datetime) -> str:
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

    return iso_z(start_utc), iso_z(end_utc), start_local.date()


def _in_window(commence_time: str, start_iso: str, end_iso: str) -> bool:
    """Defensive local filter: start_iso <= kickoff < end_iso."""
    def parse_z(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    try:
        kickoff = parse_z(commence_time)
        start = parse_z(start_iso)
        end = parse_z(end_iso)
        return start <= kickoff < end
    except Exception:
        return False


def load_from_api(
    sport_key: str | None = None,
    region: str = "us,uk,eu,au",
    extra_markets: bool = False,
) -> dict:
    """
    Fetch odds from The Odds API and convert them into the analyzer's match format.

    The wider default region set makes demos more resilient than EU-only.
    If you specifically want European books only, call with region="eu".
    """
    key = sport_key or discover_world_cup_key()
    print(f"[i] Using sport key: {key}")
    print(f"[i] Using regions: {region}")

    commence_from, commence_to, window_date = _daily_window_7am_reykjavik()

    events, meta = _get(
        f"/sports/{key}/odds",
        regions=region,
        markets=BASE_MARKETS,
        oddsFormat="decimal",
        commenceTimeFrom=commence_from,
        commenceTimeTo=commence_to,
    )

    print(
        f"[i] Odds API: {len(events)} base events from {commence_from} to {commence_to}, "
        f"~{meta['remaining']} requests remaining this month"
    )

    matches = []
    extra_market_events = 0

    for ev in events:
        if not _in_window(ev.get("commence_time", ""), commence_from, commence_to):
            continue

        if not ev.get("bookmakers"):
            continue

        home, away = ev["home_team"], ev["away_team"]
        match = {
            "id": ev["id"][:8],
            "kickoff": ev.get("commence_time", ""),
            "home": home,
            "away": away,
            "markets": {},
            "adjustments": {"notes": []},
        }

        market_prices = _collect_market_prices(ev.get("bookmakers", []), home, away)

        if extra_markets:
            extra = _load_extra_event_markets(key, ev["id"], region)
            if extra:
                extra_market_events += 1
                _merge_market_prices(
                    market_prices,
                    _collect_market_prices(extra.get("bookmakers", []), home, away),
                )

        for market_name, odds_map in market_prices.items():
            if all(odds_map.values()):
                match["markets"][market_name] = {
                    outcome: _median(prices)
                    for outcome, prices in odds_map.items()
                }

        if match["markets"]:
            matches.append(match)

    print(f"[i] Kept {len(matches)} matches after bookmaker/market filtering")

    if extra_market_events:
        print(f"[i] Loaded additional per-event markets for {extra_market_events} events")

    return {
        "date": window_date.isoformat(),
        "bookmaker": f"market consensus ({region} region, median of books)",
        "matches": matches,
    }


def _load_extra_event_markets(sport_key: str, event_id: str, region: str) -> dict | None:
    """Fetch optional per-event markets. Fail soft if unavailable."""
    try:
        data, _ = _get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            regions=region,
            markets=EXTRA_EVENT_MARKETS,
            oddsFormat="decimal",
        )
        return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as e:
        print(
            f"[i] Extra markets unavailable for event {event_id[:8]} "
            f"({e.code}); continuing with base markets."
        )
        return None
    except Exception as e:
        print(f"[i] Extra markets failed for event {event_id[:8]} ({e}); continuing with base markets.")
        return None


def _collect_market_prices(bookmakers: list[dict], home: str, away: str) -> dict[str, dict[str, list[float]]]:
    """Collect raw bookmaker prices by internal market/outcome key."""
    markets: dict[str, dict[str, list[float]]] = {}

    def ensure(market: str, outcomes: list[str]) -> dict[str, list[float]]:
        return markets.setdefault(market, {outcome: [] for outcome in outcomes})

    for bk in bookmakers:
        for mkt in bk.get("markets", []):
            key = mkt.get("key")
            outcomes = mkt.get("outcomes", [])

            if key in {"h2h", "h2h_3_way"}:
                bucket = ensure("1x2", ["home", "draw", "away"])
                for o in outcomes:
                    slot = _side_or_draw(o.get("name", ""), home, away)
                    if slot in bucket:
                        bucket[slot].append(float(o["price"]))

            elif key in {"totals", "alternate_totals"}:
                for o in outcomes:
                    point = _point(o.get("point"))
                    if point not in TOTAL_POINTS:
                        continue

                    outcome = o.get("name", "").lower()
                    if outcome not in {"over", "under"}:
                        continue

                    market = f"over_under_{_point_key(point)}"
                    ensure(market, ["over", "under"])[outcome].append(float(o["price"]))

            elif key in {"spreads", "alternate_spreads"}:
                for o in outcomes:
                    point = _point(o.get("point"))
                    if point is None or abs(point) % 1 != 0.5:
                        # Whole-number handicaps can push; this analyzer models
                        # two-way win/loss legs only, so keep half-point lines.
                        continue

                    side = _team_side(o.get("name", ""), home, away)
                    if side not in {"home", "away"}:
                        continue

                    # Store each handicap line by the home team's point.
                    # Example: home -1.5 / away +1.5 -> handicap_minus_1_5.
                    home_point = point if side == "home" else -point
                    market = f"handicap_{_signed_point_key(home_point)}"
                    bucket = markets.setdefault(market, {"home": [], "away": []})
                    bucket[side].append(float(o["price"]))

            elif key == "btts":
                bucket = ensure("btts", ["yes", "no"])
                for o in outcomes:
                    outcome = o.get("name", "").strip().lower()
                    if outcome in bucket:
                        bucket[outcome].append(float(o["price"]))

            elif key == "double_chance":
                bucket = ensure("double_chance", ["1x", "x2", "12"])
                for o in outcomes:
                    outcome = _double_chance_outcome(o.get("name", ""), home, away)
                    if outcome in bucket:
                        bucket[outcome].append(float(o["price"]))

    return _complete_handicap_markets(markets)


def _complete_handicap_markets(markets: dict[str, dict[str, list[float]]]) -> dict[str, dict[str, list[float]]]:
    """Keep handicap markets only when each line has both home and away prices."""
    out: dict[str, dict[str, list[float]]] = {}

    for market, odds_map in markets.items():
        if market.startswith("handicap_"):
            if odds_map.get("home") and odds_map.get("away"):
                out[market] = {"home": odds_map["home"], "away": odds_map["away"]}
        else:
            out[market] = odds_map

    return out


def _merge_market_prices(base: dict[str, dict[str, list[float]]], extra: dict[str, dict[str, list[float]]]) -> None:
    for market, outcomes in extra.items():
        target = base.setdefault(market, {})
        for outcome, prices in outcomes.items():
            target.setdefault(outcome, []).extend(prices)


def _team_side(name: str, home: str, away: str) -> str | None:
    name_l = name.strip().lower()
    if name_l == home.strip().lower():
        return "home"
    if name_l == away.strip().lower():
        return "away"
    return None


def _side_or_draw(name: str, home: str, away: str) -> str | None:
    if name.strip().lower() == "draw":
        return "draw"
    return _team_side(name, home, away)


def _double_chance_outcome(name: str, home: str, away: str) -> str | None:
    text = name.strip().lower().replace(" ", "")

    if text in {"1x", "homeordraw"}:
        return "1x"
    if text in {"x2", "draworaway"}:
        return "x2"
    if text in {"12", "homeoraway"}:
        return "12"

    raw = name.strip().lower()
    home_l = home.strip().lower()
    away_l = away.strip().lower()

    has_home = home_l in raw
    has_away = away_l in raw
    has_draw = "draw" in raw

    if has_home and has_draw:
        return "1x"
    if has_away and has_draw:
        return "x2"
    if has_home and has_away:
        return "12"

    return None


def _point(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _point_key(point: float) -> str:
    return f"{point:g}".replace(".", "_")


def _signed_point_key(point: float) -> str:
    prefix = "plus_" if point > 0 else "minus_" if point < 0 else "zero_"
    return prefix + _point_key(abs(point))


def merge_sheet_adjustments(api_data: dict, sheet_data: dict) -> dict:
    """Overlay sheet adjustments/notes onto API odds, matched by team names."""
    by_teams = {
        (m["home"].lower(), m["away"].lower()): m
        for m in api_data["matches"]
    }

    for sm in sheet_data["matches"]:
        match = by_teams.get((sm["home"].lower(), sm["away"].lower()))
        if match and sm.get("adjustments"):
            notes = match["adjustments"].get("notes", []) + sm["adjustments"].get("notes", [])
            match["adjustments"].update(sm["adjustments"])
            match["adjustments"]["notes"] = notes

    return api_data


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
