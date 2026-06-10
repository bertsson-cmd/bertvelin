"""
Google Sheet input source.

You maintain a Google Sheet with one row per market line — easy to edit
from a phone. Publish it as CSV (File -> Share -> Publish to web -> CSV)
and the analyzer pulls it from that URL each run.

Required columns (header row, exact names):

  match_id | home | away | market | outcome | odds | adjustment | note

Example rows:

  M01 | Mexico | Senegal | 1x2          | home | 1.45 | 0.02  | Altitude favours Mexico
  M01 | Mexico | Senegal | 1x2          | draw | 4.40 |       |
  M01 | Mexico | Senegal | 1x2          | away | 7.50 | -0.02 |
  M01 | Mexico | Senegal | over_under_2_5 | over | 2.10 |     |
  M01 | Mexico | Senegal | over_under_2_5 | under| 1.76 |     |

Notes:
- 'adjustment' is in absolute probability points (0.02 = +2pts), optional.
- Every market you include must be COMPLETE (all outcomes present),
  otherwise vig removal is wrong — the loader checks this loosely.
- 'note' rows are collected per match and shown on the report.
"""

from __future__ import annotations
import csv
import io
import urllib.request
from collections import defaultdict
from datetime import date


def fetch_sheet_csv(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "wc26-analyzer"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_sheet(csv_text: str, bookmaker: str = "epicbet.is (via sheet)") -> dict:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    matches: dict[str, dict] = {}
    notes: dict[str, list[str]] = defaultdict(list)

    for r in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        mid = r.get("match_id")
        if not mid or not r.get("odds"):
            continue
        m = matches.setdefault(mid, {
            "id": mid, "home": r.get("home", "?"), "away": r.get("away", "?"),
            "markets": {}, "adjustments": {},
        })
        market, outcome = r.get("market", ""), r.get("outcome", "")
        try:
            m["markets"].setdefault(market, {})[outcome] = float(r["odds"].replace(",", "."))
        except ValueError:
            raise ValueError(f"Bad odds value {r['odds']!r} in row {r}")
        if r.get("adjustment"):
            m["adjustments"].setdefault(market, {})[outcome] = float(r["adjustment"].replace(",", "."))
        if r.get("note"):
            notes[mid].append(r["note"])

    expected = {"1x2": 3, "double_chance": 3, "over_under_2_5": 2, "btts": 2}
    for m in matches.values():
        m["adjustments"]["notes"] = notes.get(m["id"], [])
        for market, odds_map in m["markets"].items():
            want = expected.get(market)
            if want and len(odds_map) != want:
                raise ValueError(
                    f"Match {m['id']} market '{market}' has {len(odds_map)} outcomes, "
                    f"expected {want}. Vig removal needs the complete market."
                )

    return {
        "date": date.today().isoformat(),
        "bookmaker": bookmaker,
        "matches": list(matches.values()),
    }


def load_from_sheet(url: str) -> dict:
    return parse_sheet(fetch_sheet_csv(url))
