"""
Parlay construction.

Searches all 1-3 leg combinations whose combined decimal odds land in the
target band (default 2.0-2.99), then ranks them by estimated probability of
winning ("most likely outcome, relatively safe"), with expected value as a
tiebreaker. Produces two slips that share no matches when possible, so one
bad result is less likely to sink both.

Honest math you should keep in mind:
- A parlay multiplies probabilities AND multiplies the bookmaker margin.
  Three legs at a 5% margin each is roughly a 14% combined margin.
- "Safe" here means "highest estimated hit rate inside the odds band",
  not safe in any absolute sense. A 2.20 parlay built from fair prices
  wins ~45% of the time at best. Expect losing days and losing weeks.
- Same-match legs are correlated. On normal days the builder allows only
  one leg from each match. On short days with fewer than three matches, it
  may use 2-3 different market families from the same match, but blocks
  duplicate families such as over 1.5 + over 2.5.
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
        # Independence assumption: legs are usually from different matches.
        # Short-day same-match slips are more correlated than this number shows;
        # treat those estimates as rough sorting scores, not true probabilities.
        return prod(l.adj_prob for l in self.legs)

    @property
    def expected_value(self) -> float:
        """EV per 1 unit staked. Negative for almost any real parlay."""
        return self.est_probability * self.combined_odds - 1.0

    @property
    def market_probability(self) -> float:
        """Product of vig-stripped fair probs — what the market itself believes.
        This is the baseline we compare against to find genuine value."""
        return prod(l.fair_prob for l in self.legs)

    @property
    def perceived_edge(self) -> float:
        """How much our adjusted estimate exceeds the market's fair estimate.
        Positive = we think this is more likely than the market prices it.
        The key value signal: not raw probability, but divergence from the market."""
        mp = self.market_probability
        return (self.est_probability / mp - 1.0) if mp > 0 else 0.0

    @property
    def kelly_fraction(self) -> float:
        """Full Kelly fraction: f* = (p*b - q) / b
        Positive means our estimate implies positive EV vs the market price.
        Ranks parlays by the balance of perceived edge and odds offered."""
        b = self.combined_odds - 1.0
        if b <= 0:
            return -1.0
        return (self.est_probability * self.combined_odds - 1.0) / b

    @property
    def match_ids(self) -> set[str]:
        return {l.match_id for l in self.legs}


def build_parlays(
    legs: list[Leg],
    min_odds: float = 2.0,
    max_odds: float = 2.99,
    min_leg_prob: float = 0.55,
    max_legs: int = 3,
    allow_same_match_on_short_days: bool = True,
    short_day_match_threshold: int = 2,
    max_legs_per_match_short_day: int = 3,
) -> list[Parlay]:
    """All valid 1..max_legs combinations inside the odds band.

    Normal days with 3+ matches:
      - only one leg per match.

    Short days with <= short_day_match_threshold matches:
      - allow 2-3 legs from the same match,
      - never allow two legs from the same market family in the same match.

    This lets a one- or two-game day produce a slip without allowing obvious
    duplicates such as over 1.5 + over 2.5, home win + draw, or two handicaps.
    """
    safe_legs = [l for l in legs if l.adj_prob >= min_leg_prob]
    out: list[Parlay] = []

    total_matches_today = len({l.match_id for l in legs})
    short_day = (
        allow_same_match_on_short_days
        and total_matches_today <= short_day_match_threshold
    )

    for n in range(1, max_legs + 1):
        for combo in combinations(safe_legs, n):
            if short_day:
                if not _valid_short_day_combo(combo, max_legs_per_match_short_day):
                    continue
            else:
                ids = [l.match_id for l in combo]
                if len(set(ids)) != n:          # no two legs from one match
                    continue

            p = Parlay(list(combo))
            if min_odds <= p.combined_odds <= max_odds:
                out.append(p)

    # Rank by perceived edge first (how much our estimate diverges from the market's
    # own fair probability — the closest thing to genuine value in a parlay),
    # then Kelly fraction (balances that edge against the odds), then raw probability.
    out.sort(key=lambda p: (p.perceived_edge, p.kelly_fraction, p.est_probability),
             reverse=True)
    return out


def _valid_short_day_combo(
    combo: tuple[Leg, ...],
    max_legs_per_match: int,
) -> bool:
    """Validate same-match combos for days with very few games."""
    legs_by_match: dict[str, list[Leg]] = {}
    for leg in combo:
        legs_by_match.setdefault(leg.match_id, []).append(leg)

    for match_legs in legs_by_match.values():
        if len(match_legs) > max_legs_per_match:
            return False

        families = [_market_family(leg.market) for leg in match_legs]
        if len(families) != len(set(families)):
            return False

    return True


def _market_family(market: str) -> str:
    if market.startswith("over_under_"):
        return "totals"
    if market.startswith("handicap_"):
        # Handicaps are bets on the same underlying quantity as 1x2 and
        # double chance (the goal margin). A -0.5 handicap IS "to win";
        # a +1.5 line heavily overlaps double chance. Treating them as
        # one "result" family stops short-day slips from combining e.g.
        # "France to win" with "France -0.5" — the same event priced twice,
        # which would multiply odds while adding zero real probability.
        return "result"
    if market in {"1x2", "double_chance"}:
        return "result"
    if market == "btts":
        return "btts"
    return market


def band_for_day(
    legs: list[Leg],
    min_odds: float = 2.0,
    max_odds: float = 2.99,
    short_day_min_odds: float = 1.8,
    short_day_match_threshold: int = 2,
) -> tuple[float, float]:
    """Target odds band for slips A/B, widened on thin days.

    With 3+ matches there are plenty of leg combinations, so the band stays
    at 2.0-2.5. With <= 2 matches the floor drops to 1.8: two modest
    favourites (e.g. 1.40 x 1.32 = 1.85) can then still form a slip instead
    of forcing the builder to reach for shakier legs - or worse, stretch a
    thin day into a slip that only exists to satisfy the band. Note the
    floor only EXPANDS what qualifies; if nothing sensible exists, the
    right output is still no slip.
    """
    total_matches_today = len({l.match_id for l in legs})
    if total_matches_today <= short_day_match_threshold:
        return short_day_min_odds, max_odds
    return min_odds, max_odds


def _match_market_keys(p: Parlay) -> frozenset:
    """Cross-slip exclusion key: match + market family.

    Rule: the same market on a match (e.g. over/under goals for Sweden-Tunisia)
    should not appear across slips, even if the outcome differs (over vs under).
    But different markets from the same match ARE allowed across slips — so
    "Sweden to win" in Slip A and "Sweden-Tunisia under 2.5" in Slip B is fine.
    """
    return frozenset((l.match_id, _market_family(l.market)) for l in p.legs)


def pick_two_slips(parlays: list[Parlay]) -> tuple[Parlay | None, Parlay | None]:
    """Slip A = most probable qualifying parlay.
    Slip B = most probable qualifying parlay that shares no match+market with A.

    This guarantees A and B are the two most likely independent scenarios in the
    band. Same match CAN appear across A and B as long as it's a different market
    family (e.g. "Sweden to win" in A and "Sweden-Tunisia under 2.5" in B is fine;
    "over 2.5" in A and "under 2.5" in B from the same match is not).

    Thin-day fallbacks: if no fully independent B exists, relax to sharing a match
    (but never the same market on that match), then finally to any different parlay.
    """
    if not parlays:
        return None, None
    slip_a = parlays[0]                          # highest probability — guaranteed
    a_mk = _match_market_keys(slip_a)

    # Ideal: no shared match+market pairs at all (also covers no shared matches)
    slip_b = next((p for p in parlays[1:]
                   if not (_match_market_keys(p) & a_mk)), None)
    if slip_b is None:
        # Thin-day fallback: minimise overlap rather than just "not identical" —
        # picks the least-overlapping parlay, never silently allows a shared
        # match+market through. Genuinely last resort: very few matches today.
        candidates = parlays[1:]
        if candidates:
            min_overlap = min(len(_match_market_keys(p) & a_mk) for p in candidates)
            slip_b = next((p for p in candidates
                           if len(_match_market_keys(p) & a_mk) == min_overlap), None)
    return slip_a, slip_b


def pick_risky_slip(
    legs: list[Leg],
    min_odds: float = 3.0,
    max_odds: float = 5.0,
    exclude_legs: frozenset | None = None,
) -> Parlay | None:
    """One longshot slip in the 3.0-5.0 band.

    exclude_legs: frozenset of (match_id, market, outcome) tuples from
    slips A and B — Slip C avoids repeating any leg already on the page,
    so a single match result can't dominate all three tickets.

    Looser leg filter (45%) lets in moderate favourites; still ranked by
    probability so it's the most plausible longshot, not the wildest. At
    these odds the honest hit rate is roughly 20-30%: expect it to lose
    most days. It exists for fun, not for the bankroll.
    """
    risky = build_parlays(legs, min_odds, max_odds, min_leg_prob=0.45)
    if not exclude_legs:
        return risky[0] if risky else None
    # Prefer a slip sharing no match+market pairs with A/B
    clean = [p for p in risky if not (_match_market_keys(p) & exclude_legs)]
    if clean:
        return clean[0]
    # Nothing fully clean — take the least overlapping option
    return min(risky, key=lambda p: len(_match_market_keys(p) & exclude_legs)) if risky else None


def pick_value_slip(
    legs: list[Leg],
    min_odds: float = 1.3,
    max_odds: float = 6.0,
    exclude_legs: frozenset | None = None,
) -> Parlay | None:
    """Veltuseðill — the single best VALUE slip on the page, wherever its
    odds happen to land.

    Unlike A/B/C, this has no fixed odds box (2.0-2.99, 1.6-1.8, etc). Those
    bands are a price preference, not a value signal — a genuinely strong
    edge sitting one tick outside a band would otherwise never be picked.
    This slip searches a wide 1.3-6.0 range and takes whichever parlay has
    the highest perceived edge / Kelly fraction in the ENTIRE pool, full stop.

    On a quiet day with no Groq/enrichment adjustments, every parlay's edge
    is ~0 and this collapses to "most probable parlay somewhere in 1.3-6.0" —
    similar in spirit to the old banker, just without the box. On a day with
    a genuine signal, it surfaces the actual best pick regardless of price,
    which is the entire point: paying attention to value, not to a target
    payout multiple.

    exclude_legs: match+market pairs already used by A/B/C, so this doesn't
    simply echo another slip's leg.
    """
    pool = build_parlays(legs, min_odds, max_odds, min_leg_prob=0.50)
    if not pool:
        return None
    if not exclude_legs:
        return pool[0]   # already ranked by perceived_edge, kelly, probability
    clean = [p for p in pool if not (_match_market_keys(p) & exclude_legs)]
    if clean:
        return clean[0]
    return min(pool, key=lambda p: len(_match_market_keys(p) & exclude_legs))
