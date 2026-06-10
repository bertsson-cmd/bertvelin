"""
Epicbet.is odds fetcher -- SKELETON, read before using.

IMPORTANT, PLEASE READ
----------------------
1. Most bookmakers' terms of service prohibit automated scraping, and
   Epicbet may rate-limit or ban accounts/IPs that do it. Before filling
   this in, read https://epicbet.is terms and robots.txt, and consider
   asking them if they expose an official feed. A licensed odds API
   (e.g. the-odds-api.com, OddsAPI, Betfair's official API) is the
   sturdier and cleaner route -- bookmaker sites change their HTML
   constantly and a scraper will break mid-tournament.
2. This file deliberately does NOT contain working selectors for
   Epicbet's pages. Site structure has to be inspected by you, in your
   browser (DevTools -> Network tab; most modern sportsbooks load odds
   from a JSON endpoint you can read directly instead of parsing HTML).
3. Until you wire this up, the analyzer runs from data/odds.json, which
   you can fill in by hand in ~5 minutes a day. For 2-6 matches that is
   honestly the most reliable "scraper" there is.

Expected output format: see data/sample_odds.json.
"""

from __future__ import annotations
import json
import urllib.robotparser

import requests

BASE_URL = "https://epicbet.is"
USER_AGENT = "wc26-analyzer (personal, low-volume)"


def robots_allows(path: str = "/") -> bool:
    """Check robots.txt before fetching anything."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{BASE_URL}/robots.txt")
    try:
        rp.read()
    except Exception:
        return False
    return rp.can_fetch(USER_AGENT, f"{BASE_URL}{path}")


def fetch_epicbet_odds() -> dict:
    """Fetch today's World Cup odds from Epicbet.

    NOT IMPLEMENTED on purpose -- see module docstring. Steps when you
    decide to implement it:

      1. Confirm robots_allows() and the site's ToS permit it.
      2. Open the World Cup page with browser DevTools open. Find the
         XHR/fetch request that returns odds as JSON (look for responses
         containing decimal numbers like 1.55, 4.10).
      3. Replicate that request here with requests.get(url, headers=...),
         at most a few times per day, and map the response into the
         odds.json schema (see data/sample_odds.json).
      4. Cache the result to data/odds.json so re-runs don't re-fetch.
    """
    raise NotImplementedError(
        "Epicbet fetching is not wired up. Edit analyzer/scraper_epicbet.py "
        "(read its docstring first) or maintain data/odds.json by hand."
    )


def load_local_odds(path: str = "data/odds.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
