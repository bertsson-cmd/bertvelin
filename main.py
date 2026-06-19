#!/usr/bin/env python3
"""
WC26 Parlay Analyzer — daily runner.

Usage:
    python3 main.py                       # uses data/odds.json (falls back to sample)
    python3 main.py --odds data/odds.json --min 2.0 --max 2.5
    python3 main.py --epicbet             # only after you wire up the scraper
"""

from __future__ import annotations
import argparse
import os
import sys

from analyzer.odds import build_legs, market_margin
from analyzer.parlay import band_for_day, build_parlays, pick_two_slips, pick_risky_slip, pick_banker_slip, Parlay
from analyzer.report import render_report
from analyzer.scraper_epicbet import fetch_epicbet_odds, load_local_odds


def describe(name: str, p: Parlay) -> None:
    print(f"\n  {name}  —  combined odds {p.combined_odds:.2f}")
    for leg in p.legs:
        print(f"    • {leg.label:<45} @ {leg.odds:.2f}  (est. {leg.adj_prob:.0%})")
    print(f"    est. hit rate {p.est_probability:.0%}   EV per unit {p.expected_value:+.1%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds", default="data/odds.json")
    ap.add_argument("--epicbet", action="store_true", help="fetch from Epicbet (requires you to implement the scraper)")
    ap.add_argument("--sheet", default=os.environ.get("ODDS_SHEET_URL", ""),
                    help="published-as-CSV Google Sheet URL (or set ODDS_SHEET_URL)")
    ap.add_argument("--api", action="store_true",
                    help="fetch consensus odds from the-odds-api.com (needs ODDS_API_KEY)")
    ap.add_argument("--sport-key", default="",
                    help="override The Odds API sport key (auto-discovered otherwise)")
    ap.add_argument("--extra-markets", action="store_true",
                    help="also fetch both-teams-to-score per event (uses more API quota)")
    ap.add_argument("--enrich", action="store_true",
                    help="auto-add reasoning: venues, weather, odds movement, AI news desk")
    ap.add_argument("--min", type=float, default=2.0)
    ap.add_argument("--max", type=float, default=2.99)
    ap.add_argument("--min-leg-prob", type=float, default=0.55)
    ap.add_argument("--out", default="reports/daily.html")
    args = ap.parse_args()

    if args.epicbet:
        data = fetch_epicbet_odds()
    elif args.api:
        from analyzer.api_source import load_from_api, merge_sheet_adjustments
        data = load_from_api(args.sport_key or None, extra_markets=args.extra_markets)
        if args.sheet:  # optional: overlay your notes/adjustments from the sheet
            from analyzer.sheet_source import load_from_sheet
            data = merge_sheet_adjustments(data, load_from_sheet(args.sheet))
    elif args.sheet:
        from analyzer.sheet_source import load_from_sheet
        print(f"[i] Loading odds from Google Sheet…")
        data = load_from_sheet(args.sheet)
    else:
        path = args.odds if os.path.exists(args.odds) else "data/sample_odds.json"
        if path != args.odds:
            print(f"[i] {args.odds} not found — using DEMO data ({path}). "
                  f"Replace with real odds before reading anything into the output.")
        data = load_local_odds(path)

    print(f"[i] Enrich flag: {args.enrich}")
    print(f"[i] Matches available before enrichment: {len(data.get('matches', []))}")

    if args.enrich:
        print("[i] Running enrichment layer...")
        print(f"[i] FOOTBALL_DATA_KEY present: {bool(os.environ.get('FOOTBALL_DATA_KEY'))}")
        print(f"[i] GEMINI_API_KEY present: {bool(os.environ.get('GEMINI_API_KEY'))}")
        from analyzer.enrich import enrich
        enrich(data["matches"])
    else:
        print("[i] Enrichment disabled — run with --enrich to enable venues/weather/news.")

    legs, notes = [], []
    _form_notes: dict[str, list[str]] = {}   # match_id → form-goals notes, added after slips
    print(f"\nWC26 Parlay Analyzer — {data.get('date','?')} — source: {data.get('bookmaker','?')}")
    for m in data["matches"]:
        margin = market_margin(m["markets"]["1x2"]) if "1x2" in m["markets"] else 0
        print(f"  {m['home']} vs {m['away']}  (1x2 margin {margin:.1%})")
        legs += build_legs(m)
        for n in m.get("adjustments", {}).get("notes", []):
            # Separate form-goals notes — added later only when O/U is in a slip
            if "goals/game" in n or n.startswith("WC form") or n.startswith("Form (last"):
                _form_notes.setdefault(m["id"], []).append(
                    f"<b>{m['home']} v {m['away']}</b>: {n}")
            else:
                notes.append(f"<b>{m['home']} v {m['away']}</b>: {n}")

    locked = None
    try:
        from analyzer.results import load_locked_slips
        locked = load_locked_slips(data.get("date", ""), legs)
    except Exception as e:
        print(f"[!] Slip lock check failed ({e}) — picking fresh.")

    if locked:
        print("[i] Slips already published today — LOCKED. Re-run refreshes odds only; "
              "legs stay as picked at the first run.")
        slip_a, slip_b, slip_c, slip_d = locked["A"], locked["B"], locked["C"], locked["D"]
        # Gemini intelligence re-runs even on locked days — news changes through the day
        # and the reasoning box should reflect the latest information even when legs are frozen.
        if args.enrich:
            try:
                from analyzer.enrich import attach_gemini_intelligence
                print("[i] Re-running Gemini intelligence to refresh notes on locked slips...")
                # Clear old Gemini notes so they don't duplicate
                for m in data["matches"]:
                    notes_list = m.get("adjustments", {}).get("notes", [])
                    m["adjustments"]["notes"] = [
                        n for n in notes_list if not n.startswith("Gemini")]
                attach_gemini_intelligence(data["matches"])
                # Re-collect notes now they're refreshed
                for m in data["matches"]:
                    for n in m.get("adjustments", {}).get("notes", []):
                        if "goals/game" in n or n.startswith("WC form") or n.startswith("Form (last"):
                            _form_notes.setdefault(m["id"], []).append(
                                f"<b>{m['home']} v {m['away']}</b>: {n}")
                        elif f"<b>{m['home']} v {m['away']}</b>: {n}" not in notes:
                            notes.append(f"<b>{m['home']} v {m['away']}</b>: {n}")
            except Exception as _ge:
                print(f"[!] Gemini re-run failed ({_ge}) — using cached notes.")
    else:
        band_min, band_max = band_for_day(legs, args.min, args.max)
        if band_min != args.min:
            print(f"[i] Short day (<=2 matches): slip A/B band widened to {band_min:.2f}-{band_max:.2f}")
        parlays = build_parlays(legs, band_min, band_max, args.min_leg_prob)
        print(f"\n{len(parlays)} qualifying parlays in the {args.min:.2f}–{args.max:.2f} band.")

        slip_a, slip_b = pick_two_slips(parlays)
        # exclude A+B match+market pairs from C so the same market on a match
        # can't dominate multiple slips (but different markets from the same
        # match are still allowed, e.g. "Sweden to win" vs "Sweden-Tunisia under")
        from analyzer.parlay import _match_market_keys, _market_family
        ab_markets = frozenset()
        for sl in (slip_a, slip_b):
            if sl:
                ab_markets |= _match_market_keys(sl)
        slip_c = pick_risky_slip(legs, exclude_legs=ab_markets or None)
        # Veltusedill: banker 1.6-1.8, excluding markets already used by A/B/C
        abc_markets = ab_markets
        if slip_c:
            abc_markets = abc_markets | _match_market_keys(slip_c)
        slip_d = pick_banker_slip(legs, exclude_legs=abc_markets or None)
    if slip_a:
        describe("SLIP A (primary)", slip_a)
    if slip_b:
        describe("SLIP B (alternate, no shared matches)", slip_b)
    if slip_c:
        describe("SLIP C (longshot 3-5, expect it to lose most days)", slip_c)
    if slip_d:
        describe("VELTUSEDILL (banker 1.6-1.8)", slip_d)
    if not slip_a:
        print("  No qualifying parlay today — that's a legitimate answer. Don't force a bet.")

    # Append form-goals notes only for matches that have an O/U leg in a slip
    for sl in (slip_a, slip_b, slip_c, slip_d):
        if sl:
            for leg in sl.legs:
                if leg.market.startswith("over_under_") and leg.match_id in _form_notes:
                    notes.extend(_form_notes.pop(leg.match_id))

    day = data.get("date", "")
    scoreboard = None
    try:
        from analyzer.results import settle_pending, record_picks
        scoreboard = settle_pending(day)          # grade older picks first
        if scoreboard is None:
            scoreboard = {"n": 0, "wins": 0, "units": 0.0, "actual_rate": 0.0,
                          "est_rate": 0.0, "safe": {"n":0,"wins":0,"units":0.0},
                          "longshot": {"n":0,"wins":0,"units":0.0},
                          "latest_day": None, "latest": [], "pending_days": [],
                          "history": []}
        if not locked:                            # the first run of the day decides
            record_picks(day, {"A": slip_a, "B": slip_b, "C": slip_c, "D": slip_d})
    except Exception as e:
        print(f"[!] Results tracking failed ({e}) — briefing continues without it.")
        # Provide an empty but valid scoreboard so the stadan window still renders
        scoreboard = {"n": 0, "wins": 0, "units": 0.0, "actual_rate": 0.0,
                      "est_rate": 0.0, "safe": {"n":0,"wins":0,"units":0.0},
                      "longshot": {"n":0,"wins":0,"units":0.0},
                      "latest_day": None, "latest": [], "pending_days": [],
                      "history": []}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out = render_report(slip_a, slip_b, data.get("bookmaker", "manual"), notes, args.out,
                        slip_c=slip_c, scoreboard=scoreboard, archive_href="archive/index.html",
                        slip_d=slip_d)
    try:
        from analyzer.archive import archive_report
        archive_report(out, day, reports_dir=os.path.dirname(args.out) or "reports")
        print(f"[i] Archived as {day}.html")
    except Exception as e:
        print(f"[!] Archiving failed ({e}) — briefing continues without it.")
    print(f"\nReport written to {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
