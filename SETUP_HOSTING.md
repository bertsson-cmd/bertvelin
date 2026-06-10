# Hosting setup: Google Sheet in, daily website out

End result: you type odds into a Google Sheet (works fine from a phone), and
every morning at 07:00 Reykjavík time a free GitHub Action rebuilds the
briefing and publishes it at a permanent URL like
`https://YOURNAME.github.io/wc26-analyzer/`. Total cost: 0 kr. One-time setup:
~15 minutes.

## 1. The Google Sheet (your input)

1. Create a new Google Sheet.
2. Import `data/sheet_template.csv` (File → Import → Upload → Replace sheet)
   so you start with the right columns: `match_id, home, away, market,
   outcome, odds, adjustment, note`.
3. One row per outcome. Markets must be complete (all three 1x2 rows, both
   over/under rows) or the analyzer rejects the input — vig removal needs the
   whole market.
4. File → Share → **Publish to web** → choose the sheet → **CSV** → Publish.
   Copy the long URL it gives you. That URL is read-only and only exposes
   this sheet, but note it is public-by-link — fine for odds, just don't put
   anything personal in it.

Daily routine becomes: open Epicbet, copy today's prices into the sheet, add
your adjustment/notes where you know something, done.

## 2. The website (your output)

1. Create a GitHub account if needed, then a new repository (must be Public — GitHub Pages is only free on public repos; see GETTING_STARTED.md),
   and upload this whole project folder to it.
2. Repo **Settings → Pages** → Source: **GitHub Actions**.
3. Repo **Settings → Secrets and variables → Actions → New repository
   secret**: name `ODDS_SHEET_URL`, value = the published-CSV URL from step 1.
4. Go to the **Actions** tab → "Daily briefing" → **Run workflow** to test.
   After ~1 minute, the page is live at the URL shown in the run.

From then on it rebuilds itself every morning automatically
(`.github/workflows/daily.yml` — change the cron line if you want a
different time; GitHub's scheduler can run 5–30 min late).

Bookmark the page on your phone's home screen and it behaves like an app.

## 3. Local fallback

Everything also still works on your machine:

```bash
python3 main.py --sheet "PASTE_PUBLISHED_CSV_URL"   # pull from the sheet
python3 main.py                                     # or use data/odds.json
```

## What about the Google Drive doc idea?

Doable with Google Apps Script, but it would mean rewriting the analyzer in
JavaScript inside Google's editor, and a Doc is a poor format for slips. The
Sheet-in / website-out split gives you the comfortable half of Drive (easy
mobile editing) with a much nicer output.

## A note on automating Epicbet

The daily Action currently reads *your* sheet, not Epicbet directly — that's
deliberate. If you later implement `analyzer/scraper_epicbet.py` (read its
docstring about terms of service first, or use a licensed odds API instead),
you can swap the build step in `daily.yml` to `python3 main.py --epicbet
--out reports/index.html` and the manual step disappears. Until then, the
two-minute sheet update also forces you to glance at the prices yourself,
which is honestly a feature.

---

# Fully automatic mode (no daily input at all)

The daily Action now runs `main.py --api --enrich` and needs at most three
secrets (Settings → Secrets and variables → Actions):

| Secret | Where | Cost | What it powers |
|---|---|---|---|
| `ODDS_API_KEY` | the-odds-api.com | free tier | the odds (EU consensus, median of books) |
| `FOOTBALL_DATA_KEY` | football-data.org | free tier | fixture → stadium mapping, which unlocks the Open-Meteo kickoff weather forecast (no key needed) and altitude notes |
| `ANTHROPIC_API_KEY` | console.anthropic.com | ~a few cents/day | the "news desk": Claude web-searches each fixture for confirmed injuries/suspensions/rotation and returns reasoning + conservative adjustments |

Each layer fails soft: missing key = that layer is skipped, the rest still runs.
Even with no AI key, you still get automatic weather reasoning, altitude notes,
and **odds-movement notes** — the Action commits each day's prices to
`data/history.json`, and a sharp overnight move (e.g. 1.60 → 1.45) is flagged
the next morning. Market moves are how team news reaches you for free: the
odds move *because* insiders and sharps reacted to the news.

Every adjustment from every layer is capped at ±5 probability points total per
outcome, so no single signal (including the AI) can drag a slip far from the
market's own view.

Your Google Sheet still works as an optional overlay for anything you
personally know — leave `ODDS_SHEET_URL` set and add rows only when you want.
