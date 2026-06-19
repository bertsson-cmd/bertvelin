"""
Results tracking — the honesty ledger.

Each morning the run does two things here:
  1. SETTLE yesterday's (and any older pending) slips against final scores
     from football-data.org, grading every leg.
  2. RECORD today's slips so tomorrow's run can settle them.

The scoreboard that comes out of this is the only feature that can tell you
whether Bertpicker earns its keep: actual hit rate vs. the estimates, and
units up or down at flat 1-unit stakes. Expect the units line to drift
negative over a full tournament — that's the margin doing what margins do —
and treat any sustained gap between actual and estimated hit rates as the
model being wrong, not the world.

Settlement rules:
  - All markets settle on 90 minutes + stoppage (regular time), like the
    bookmaker markets they mirror. For knockout games that go to extra
    time, football-data's regularTime score is used; if it's missing, the
    slip stays pending rather than being graded on the wrong number.
  - A slip wins only if every leg wins. Stake 1 unit per slip:
    profit = combined_odds - 1 on a win, -1 on a loss.

Storage (committed back to the repo by the daily Action):
  data/picks.json    {date: {"A": slip, "B": slip, "C": slip}}
  data/results.json  {"settled": {date: [graded slip records]}}

Fails soft without FOOTBALL_DATA_KEY: picks are still recorded, settlement
just waits until the key exists.
"""

from __future__ import annotations
import json
import os
import re
import urllib.request
from datetime import date as date_cls, datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PICKS_PATH = os.path.join(DATA_DIR, "picks.json")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


# ------------------------------------------------------------ record picks

def gemini_already_ran(day: str) -> bool:
    """True if Gemini intelligence already ran today (checked before calling it)."""
    return bool(_load(PICKS_PATH, {}).get(day, {}).get("_gemini_ran"))


def record_gemini_ran(day: str) -> None:
    """Mark that Gemini has run for today so re-runs skip it."""
    picks = _load(PICKS_PATH, {})
    picks.setdefault(day, {})["_gemini_ran"] = True
    _save(PICKS_PATH, picks)


def record_picks(day: str, slips: dict) -> None:
    """slips: {"A": Parlay|None, "B": ..., "C": ...}. Re-running a day
    overwrites that day's picks (manual workflow re-runs are fine)."""
    picks = _load(PICKS_PATH, {})
    entry = {}
    for name, p in slips.items():
        if p is None:
            continue
        entry[name] = {
            "combined_odds": round(p.combined_odds, 4),
            "est_probability": round(p.est_probability, 4),
            "legs": [{
                "match_id": l.match_id, "label": l.label,
                "home": _home_from(l), "away": _away_from(l),
                "market": l.market, "outcome": l.outcome, "odds": l.odds,
                "est": round(l.adj_prob, 4),
            } for l in p.legs],
        }
    picks[day] = entry
    _save(PICKS_PATH, picks)


def _home_from(leg) -> str:
    return getattr(leg, "home", "") or leg.match_id


def _away_from(leg) -> str:
    return getattr(leg, "away", "") or ""


# ------------------------------------------------------- slip locking

def load_locked_slips(day: str, todays_legs: list) -> dict | None:
    """If picks were already recorded for `day`, rebuild those exact slips.

    Why: the picker is otherwise stateless — a midday manual re-run would
    re-rank with drifted prices and could swap the slips someone already
    placed. Locked slips keep the morning's LEGS; only the displayed odds
    refresh (matched against today's feed by teams+market+outcome). The
    ledger keeps the 07:00 odds — those are the prices the slips were
    published at, so settlement stays honest.

    Returns {"A": Parlay|None, "B": ..., "C": ...} or None if nothing
    recorded yet (e.g. the 07:00 run failed before recording — then a
    re-run picks fresh, which is exactly right).
    """
    entry = _load(PICKS_PATH, {}).get(day)
    if not entry:
        return None
    from .parlay import Parlay      # local import: no circular dependency
    from .odds import Leg
    from .teams import team_match

    def fresh_leg(st: dict):
        for l in todays_legs:
            if (l.market == st["market"] and l.outcome == st["outcome"]
                    and team_match(l.home, st.get("home", ""))
                    and team_match(l.away, st.get("away", ""))):
                return l
        return None

    out = {}
    for name in ("A", "B", "C", "D"):
        s = entry.get(name)
        if not s:
            out[name] = None
            continue
        legs = []
        for st in s["legs"]:
            l = fresh_leg(st)
            if l is None:           # match gone from feed: keep morning's numbers
                l = Leg(match_id=st.get("match_id", "?"), label=st["label"],
                        market=st["market"], outcome=st["outcome"], odds=st["odds"],
                        fair_prob=st.get("est", 0.5), adj_prob=st.get("est", 0.5),
                        home=st.get("home", ""), away=st.get("away", ""))
            legs.append(l)
        out[name] = Parlay(legs)
    return out


# -------------------------------------------------------------- settlement

def settle_pending(today: str) -> dict:
    """Grade every pick from days before `today` that isn't settled yet.
    Returns the scoreboard summary (see summarize())."""
    picks = _load(PICKS_PATH, {})
    results = _load(RESULTS_PATH, {"settled": {}})
    pending = sorted(d for d in picks
                     if d < today and d not in results["settled"] and picks[d])

    if pending:
        key = os.environ.get("FOOTBALL_DATA_KEY", "")
        if not key:
            print("[i] Results: FOOTBALL_DATA_KEY not set — "
                  f"{len(pending)} day(s) of picks stay pending.")
        else:
            scores = _fetch_scores(pending, key)
            for day in pending:
                graded = _grade_day(picks[day], scores)
                if graded is not None:
                    results["settled"][day] = graded
                    for rec in graded:
                        mark = "WON" if rec["won"] else "lost"
                        print(f"[i] Settled {day} slip {rec['slip']}: {mark} "
                              f"({rec['profit']:+.2f}u)")
                else:
                    print(f"[i] {day}: results not final yet — stays pending.")
            _save(RESULTS_PATH, results)

    return summarize(results, picks, today)


def _fetch_scores(days: list[str], key: str) -> list[dict]:
    """Finished matches covering the pending dates (plus one day of slack
    for late-UTC kickoffs)."""
    lo = min(days)
    hi = (date_cls.fromisoformat(max(days)) + timedelta(days=2)).isoformat()
    url = (f"https://api.football-data.org/v4/competitions/WC/matches"
           f"?dateFrom={lo}&dateTo={hi}")
    req = urllib.request.Request(url, headers={"X-Auth-Token": key,
                                               "User-Agent": "wc26-analyzer"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8")).get("matches", [])
    except Exception as e:
        print(f"[!] Results: score fetch failed ({e}) — picks stay pending.")
        return []


def _regular_time_score(fd_match: dict) -> tuple[int, int] | None:
    """90-minute score, or None if unavailable/unfinished."""
    if fd_match.get("status") != "FINISHED":
        return None
    score = fd_match.get("score", {})
    if score.get("duration", "REGULAR") != "REGULAR":
        rt = score.get("regularTime") or {}
        h, a = rt.get("home"), rt.get("away")
        return (h, a) if h is not None and a is not None else None
    ft = score.get("fullTime", {})
    h, a = ft.get("home"), ft.get("away")
    return (h, a) if h is not None and a is not None else None


from .teams import team_match as _team_match


def _grade_day(day_picks: dict, scores: list[dict]) -> list[dict] | None:
    """Grade all slips for one day. Returns None if ANY needed score is
    missing (the whole day waits — partial settlement invites confusion)."""
    graded = []
    for slip_name, slip in day_picks.items():
        legs_out, slip_won = [], True
        for leg in slip["legs"]:
            res = _find_score(leg, scores)
            if res is None:
                # Diagnose why: name mismatch vs not-yet-finished
                cand = None
                for fd in scores:
                    ht = fd.get("homeTeam", {}).get("name", "")
                    at = fd.get("awayTeam", {}).get("name", "")
                    if _team_match(leg.get("home", ""), ht) and _team_match(leg.get("away", ""), at):
                        cand = fd
                        break
                if cand is None:
                    avail = ", ".join(
                        f"{f.get('homeTeam',{}).get('name','?')} v {f.get('awayTeam',{}).get('name','?')}"
                        for f in scores) or "(none returned)"
                    print(f"[i] Settle: no score row matched {leg.get('home','?')} v "
                          f"{leg.get('away','?')} (slip {slip_name}). "
                          f"football-data returned: {avail}")
                else:
                    st = cand.get("status", "?")
                    dur = cand.get("score", {}).get("duration", "?")
                    print(f"[i] Settle: {leg.get('home','?')} v {leg.get('away','?')} "
                          f"matched but no usable score (status={st}, duration={dur}). "
                          f"Day stays pending.")
                return None
            hg, ag = res
            won = _grade_leg(leg["market"], leg["outcome"], hg, ag)
            slip_won &= won
            legs_out.append({**leg, "score": f"{hg}-{ag}", "won": won})
        graded.append({
            "slip": slip_name,
            "combined_odds": slip["combined_odds"],
            "est_probability": slip["est_probability"],
            "legs": legs_out,
            "won": slip_won,
            "profit": round(slip["combined_odds"] - 1, 4) if slip_won else -1.0,
        })
    return graded


def _find_score(leg: dict, scores: list[dict]) -> tuple[int, int] | None:
    for fd in scores:
        ht = fd.get("homeTeam", {}).get("name", "")
        at = fd.get("awayTeam", {}).get("name", "")
        if _team_match(leg.get("home", ""), ht) and _team_match(leg.get("away", ""), at):
            return _regular_time_score(fd)
    return None


def _grade_leg(market: str, outcome: str, hg: int, ag: int) -> bool:
    total, margin = hg + ag, hg - ag
    if market == "1x2":
        return {"home": margin > 0, "draw": margin == 0, "away": margin < 0}[outcome]
    if market == "double_chance":
        return {"1x": margin >= 0, "x2": margin <= 0, "12": margin != 0}[outcome]
    if market == "btts":
        both = hg > 0 and ag > 0
        return both if outcome == "yes" else not both
    if market.startswith("over_under_"):
        point = float(market.replace("over_under_", "").replace("_", "."))
        return total > point if outcome == "over" else total < point
    if market.startswith("handicap_"):
        raw = market.replace("handicap_", "", 1)
        sign = -1 if raw.startswith("minus_") else 1
        point = sign * float(raw.split("_", 1)[1].replace("_", "."))
        adj = margin + point          # home margin after home handicap
        return adj > 0 if outcome == "home" else adj < 0
    raise ValueError(f"Unknown market for grading: {market}")


# -------------------------------------------------------------- scoreboard

def summarize(results: dict | None = None, picks: dict | None = None,
              today: str | None = None) -> dict:
    results = results if results is not None else _load(RESULTS_PATH, {"settled": {}})
    picks = picks if picks is not None else _load(PICKS_PATH, {})
    today = today or datetime.utcnow().date().isoformat()

    flat = [{**r, "day": day}
            for day in sorted(results["settled"]) for r in results["settled"][day]]
    n, wins = len(flat), sum(r["won"] for r in flat)
    units = sum(r["profit"] for r in flat)
    est_avg = sum(r["est_probability"] for r in flat) / n if n else 0.0

    def bucket(names):
        sel = [r for r in flat if r["slip"] in names]
        return {"n": len(sel), "wins": sum(r["won"] for r in sel),
                "units": round(sum(r["profit"] for r in sel), 2)}

    last_day = max(results["settled"]) if results["settled"] else None
    pending = sorted(d for d in picks
                     if d < today and d not in results["settled"] and picks[d])
    return {
        "n": n, "wins": wins, "units": round(units, 2),
        "actual_rate": wins / n if n else 0.0, "est_rate": est_avg,
        "safe": bucket({"A", "B"}), "longshot": bucket({"C"}),
        "slip_a": bucket({"A"}), "slip_b": bucket({"B"}), "slip_c": bucket({"C"}),
        "slip_d": bucket({"D"}),
        "latest_day": last_day,
        "latest": results["settled"].get(last_day, []),
        "pending_days": pending,
        "history": flat,
    }
