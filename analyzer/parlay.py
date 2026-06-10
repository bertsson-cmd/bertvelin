"""
Parlay construction.

Searches all 1-3 leg combinations whose combined decimal odds land in the
target band (default 2.0-2.5), then ranks them by estimated probability of
winning ("most likely outcome, relatively safe"), with expected value as a
tiebreaker. Produces two slips that share no matches, so one bad result
can't sink both.

Honest math you should keep in mind:
- A parlay multiplies probabilities AND multiplies the bookmaker margin.
  Three legs at a 5% margin each is roughly a 14% combined margin.
- "Safe" here means "highest estimated hit rate inside the odds band",
  not safe in any absolute sense. A 2.20 parlay built from fair prices
  wins ~45% of the time at best. Expect losing days and losing weeks.
- Legs from the SAME match are correlated (e.g. "Mexico to win" and
  "under 2.5 goals" are not independent), so the builder never combines
  two legs from one match.
"""

from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from math import prod

from .odds import Leg


@dataclass
class Parlay:
    legs: list[Leg]

    @property
    def combined_odds(self) -> float:
        return prod(l.odds for l in self.legs)

    @property
    def est_probability(self) -> float:
        # Independence assumption: legs are from different matches.
        # Same-day group games can still be mildly correlated; treat the
        # number as an estimate, not a measurement.
        return prod(l.adj_prob for l in self.legs)

    @property
    def expected_value(self) -> float:
        """EV per 1 unit staked. Negative for almost any real parlay."""
        return self.est_probability * self.combined_odds - 1.0

    @property
    def match_ids(self) -> set[str]:
        return {l.match_id for l in self.legs}


def build_parlays(
    legs: list[Leg],
    min_odds: float = 2.0,
    max_odds: float = 2.5,
    min_leg_prob: float = 0.55,
    max_legs: int = 3,
) -> list[Parlay]:
    """All valid 1..max_legs combinations inside the odds band.

    min_leg_prob filters out individually risky legs before combining:
    the 'relatively safe' constraint. 0.55 keeps legs the market itself
    thinks are clear favourites (odds roughly <= 1.75 after vig removal).
    """
    safe_legs = [l for l in legs if l.adj_prob >= min_leg_prob]
    out: list[Parlay] = []

    for n in range(1, max_legs + 1):
        for combo in combinations(safe_legs, n):
            ids = [l.match_id for l in combo]
            if len(set(ids)) != n:          # no two legs from one match
                continue
            p = Parlay(list(combo))
            if min_odds <= p.combined_odds <= max_odds:
                out.append(p)

    # Rank: most likely to win first; break ties with EV (least bad price).
    out.sort(key=lambda p: (p.est_probability, p.expected_value), reverse=True)
    return out


def pick_two_slips(parlays: list[Parlay]) -> tuple[Parlay | None, Parlay | None]:
    """Slip A = best parlay. Slip B = best parlay sharing no matches with A."""
    if not parlays:
        return None, None
    slip_a = parlays[0]
    slip_b = next((p for p in parlays[1:] if not (p.match_ids & slip_a.match_ids)), None)
    return slip_a, slip_b


def pick_risky_slip(legs: list[Leg], min_odds: float = 3.0, max_odds: float = 5.0) -> Parlay | None:
    """One longshot slip in the 3.0-5.0 band.

    Looser leg filter (45%) lets in moderate favourites; still ranked by
    probability so it's the most plausible longshot, not the wildest. At
    these odds the honest hit rate is roughly 20-30%: expect it to lose
    most days. It exists for fun, not for the bankroll.
    """
    risky = build_parlays(legs, min_odds, max_odds, min_leg_prob=0.45)
    return risky[0] if risky else None
