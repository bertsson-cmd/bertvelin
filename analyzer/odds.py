"""
Core odds mathematics.

Decimal odds -> implied probability -> "fair" (vig-free) probability.

Key idea: a bookmaker's 1X2 market sums to more than 100% implied
probability. The excess is the margin (vig / overround). To estimate what
the bookmaker actually believes, we strip the margin out. The default
method is proportional normalisation, which is simple and adequate for
short-priced favourites (the legs a 2.0-2.5 parlay is built from).
"""

from __future__ import annotations
from dataclasses import dataclass, field


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError(f"Decimal odds must be > 1.0, got {decimal_odds}")
    return 1.0 / decimal_odds


def remove_vig(odds_by_outcome: dict[str, float]) -> dict[str, float]:
    """Proportionally normalise a full market so probabilities sum to 1."""
    implied = {k: implied_probability(v) for k, v in odds_by_outcome.items()}
    total = sum(implied.values())  # the overround, e.g. 1.06 = 6% margin
    return {k: p / total for k, p in implied.items()}


def market_margin(odds_by_outcome: dict[str, float]) -> float:
    """Bookmaker margin on a market, e.g. 0.06 = 6%."""
    return sum(implied_probability(v) for v in odds_by_outcome.values()) - 1.0


@dataclass
class Leg:
    """One selectable outcome (a potential parlay leg)."""
    match_id: str
    label: str            # e.g. "Mexico to win"
    market: str           # e.g. "1x2"
    outcome: str          # e.g. "home"
    odds: float           # bookmaker decimal odds
    fair_prob: float      # vig-free market probability
    adj_prob: float       # after your news/weather/injury adjustments
    notes: list[str] = field(default_factory=list)

    @property
    def edge(self) -> float:
        """Expected value per 1 unit staked: adj_prob * odds - 1.

        Almost always negative once the margin is in the price. The
        analyzer's job is to find the legs where it is least negative
        (or, rarely, positive if your adjustment disagrees with the market).
        """
        return self.adj_prob * self.odds - 1.0


def build_legs(match: dict, max_adjustment: float = 0.05) -> list[Leg]:
    """Turn one match's markets into candidate legs.

    Adjustments (from team news, injuries, weather, etc.) are added to the
    fair probability in absolute points, then capped at +/- max_adjustment
    and the market is re-normalised. The cap exists on purpose: World Cup
    markets are heavily traded and already price in public information, so
    a private view more than ~5 points from the market is usually a sign
    of overconfidence, not insight.
    """
    legs: list[Leg] = []
    adjustments = match.get("adjustments", {})
    notes = adjustments.get("notes", [])

    for market_name, odds_map in match.get("markets", {}).items():
        fair = remove_vig(odds_map)
        market_adj = adjustments.get(market_name, {})

        # apply capped adjustments, then re-normalise
        raw = {}
        for outcome, p in fair.items():
            delta = float(market_adj.get(outcome, 0.0))
            delta = max(-max_adjustment, min(max_adjustment, delta))
            raw[outcome] = max(0.001, p + delta)
        total = sum(raw.values())
        adj = {k: v / total for k, v in raw.items()}

        for outcome, odds in odds_map.items():
            legs.append(Leg(
                match_id=match["id"],
                label=_label(match, market_name, outcome),
                market=market_name,
                outcome=outcome,
                odds=odds,
                fair_prob=fair[outcome],
                adj_prob=adj[outcome],
                notes=notes,
            ))
    return legs


def _label(match: dict, market: str, outcome: str) -> str:
    home, away = match["home"], match["away"]
    names = {
        ("1x2", "home"): f"{home} to win",
        ("1x2", "draw"): f"{home} vs {away}: draw",
        ("1x2", "away"): f"{away} to win",
        ("double_chance", "1x"): f"{home} or draw",
        ("double_chance", "x2"): f"{away} or draw",
        ("double_chance", "12"): f"{home} or {away} (no draw)",
        ("over_under_2_5", "over"): f"{home} vs {away}: over 2.5 goals",
        ("over_under_2_5", "under"): f"{home} vs {away}: under 2.5 goals",
        ("btts", "yes"): f"{home} vs {away}: both teams to score",
        ("btts", "no"): f"{home} vs {away}: not both teams to score",
    }
    return names.get((market, outcome), f"{home} vs {away}: {market}/{outcome}")
