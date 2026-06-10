# WC26 Parlay Analyzer

A daily World Cup 2026 tool that takes bookmaker odds (e.g. from Epicbet.is),
strips out the bookmaker margin, applies your own team-news/weather/injury
adjustments, and proposes **two slips of 1–3 legs with combined odds of 2.0–2.5**,
ranked by estimated probability of landing.

## Quick start

```bash
python3 main.py            # runs on demo data, prints slips, writes reports/daily.html
open reports/daily.html    # the visual briefing
```

Requires Python 3.10+ (standard library only; `requests` only if you implement the scraper).

## Daily workflow

1. **Get the odds.** Copy today's Epicbet prices into `data/odds.json`
   (copy `data/sample_odds.json` as a template). For a handful of matches this
   takes ~5 minutes and never breaks. If you want automation, read
   `analyzer/scraper_epicbet.py` first — it explains how, and why you should
   check Epicbet's terms of service and robots.txt before scraping, and why a
   licensed odds API is usually the better route.
2. **Add what you know.** Injuries, suspensions, weather, altitude, travel,
   rotation rumours go into each match's `adjustments` block as probability
   points (e.g. `"home": -0.03` if the favourite's striker is out) plus a
   human-readable note. The analyzer caps any adjustment at ±5 points,
   because a private view further than that from a heavily traded World Cup
   market is more likely overconfidence than insight.
3. **Run it.** `python3 main.py` prints both slips and writes the HTML report.

## What the numbers mean

- **Fair probability**: market odds with the vig removed (markets here run ~5%).
- **Est. probability**: fair probability after your capped adjustments.
- **EV per unit**: average return per 1 unit staked *if the estimates are right*.
  It is negative on almost every real parlay, because a parlay multiplies the
  bookmaker margin as well as the odds. The analyzer finds the *least bad* slips,
  not winning ones.
- **Hit rate**: a 2.2-odds slip built from fair prices wins well under half the
  time. Losing days and losing weeks are the normal, expected behaviour.

## Honest limitations (read once, believe forever)

- **The market already knows.** Team news, weather and injuries are priced into
  World Cup odds within minutes. Public information gives you almost no edge;
  this tool mainly protects you from *bad* parlays rather than finding good ones.
- **No parlay is "safe."** "Relatively safe" here means "highest estimated hit
  rate inside your odds band" — nothing more.
- **Independence assumption.** Legs come from different matches, but tournament
  results still correlate mildly (group permutations, same-day conditions).
- **Demo data is fictional.** Everything in `sample_odds.json` is illustrative.

## Bankroll & responsible gambling

Flat-stake (same small amount every day, ≤1–2% of a bankroll you can fully
afford to lose), never chase losses, and treat the spend as entertainment cost.
If it stops feeling like entertainment: in Iceland, SÁÁ (saa.is) treats gambling
problems and the Red Cross helpline **1717** is free and anonymous.

## Project layout

```
main.py                       CLI entry point
analyzer/odds.py              implied prob, vig removal, adjustments, leg building
analyzer/parlay.py            1–3 leg combination search, ranking, two-slip picker
analyzer/report.py            HTML briefing renderer
analyzer/scraper_epicbet.py   Epicbet fetcher skeleton (read its docstring)
data/sample_odds.json         demo input — the schema to copy
reports/daily.html            generated each run
```
