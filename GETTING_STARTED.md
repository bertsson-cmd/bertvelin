# Getting started — complete walkthrough

Follow this top to bottom and you'll go from the zip file to a self-updating
daily briefing page in roughly 30–45 minutes. No programming needed — it's
all clicking and copy-pasting. Nothing here requires a credit card except the
optional AI news desk at the very end.

What you'll end up with: a web address like
`https://YOURNAME.github.io/wc26-analyzer/` that rebuilds itself every
morning at 07:00 Icelandic time with the day's three slips and the reasoning
behind them.

---

## Phase 1 — Unpack the project (2 min)

1. Unzip `wc26-parlay-analyzer.zip` somewhere you can find it, e.g. your
   Desktop. You should see folders called `analyzer`, `data`, `.github`
   (this one may be invisible — that's fine, more on it in Phase 3) and
   files like `main.py` and `README.md`.

## Phase 2 — Create a GitHub account and repository (5 min)

GitHub is a free code-hosting service. It will both store the project and
run it for you every morning ("GitHub Actions"), and host the result as a
website ("GitHub Pages").

1. Go to **github.com** → **Sign up**. Pick the free plan.
2. Once logged in, click the **+** in the top-right corner → **New repository**.
3. Fill in:
   - **Repository name:** `wc26-analyzer` (this becomes part of your URL)
   - **Visibility:** **Public** — required: GitHub Pages is only free on
     public repositories. The repo contains no secrets (your API keys are
     stored separately in Phase 5), so public is safe.
   - Leave everything else unticked.
4. Click **Create repository**. You'll land on a mostly-empty page — keep it open.

## Phase 3 — Upload the project (10 min)

**Part A — the normal files:**

1. On your new repository page, click the link **"uploading an existing file"**
   (it's in the setup text), or go to **Add file → Upload files**.
2. Open the unzipped project folder on your computer, select **everything
   inside it** (Ctrl+A / Cmd+A) and drag it onto the GitHub upload area.
   Drag the *contents*, not the outer folder itself, so `main.py` ends up at
   the top level of the repo.
3. Wait for the file list to appear, then click **Commit changes** at the bottom.

**Part B — the automation file (do not skip):**

The daily schedule lives in a hidden folder called `.github`, and hidden
folders usually don't survive a drag-and-drop upload. Create it by hand:

1. In your repo, click **Add file → Create new file**.
2. In the filename box, type exactly:
   `.github/workflows/daily.yml`
   (GitHub turns the slashes into folders as you type — that's correct.)
3. On your computer, open the file `.github/workflows/daily.yml` from the
   unzipped project in any text editor (Notepad/TextEdit). If you can't see
   the `.github` folder: Windows → File Explorer → View → tick "Hidden
   items"; Mac → press Cmd+Shift+. (period) in Finder.
4. Copy its entire contents, paste into the GitHub editor, click
   **Commit changes**.
5. Sanity check: your repo's file list should now show a `.github` folder.

## Phase 4 — Get the API keys (10 min)

Two free signups, one optional paid one. As each key arrives, paste it
somewhere temporary (a note) — you'll add them all to GitHub in Phase 5.

**Key 1 — the odds (required): The Odds API**

1. Go to **the-odds-api.com** → **Get API key** → choose the **free** tier.
2. Enter your email; the key arrives by email within a minute. It's a long
   string of letters and numbers.
3. Quota math so you can relax: free tier gives 500 requests/month; the
   daily build uses about 2 (one to find the World Cup, one to fetch odds).
   A whole tournament uses well under 100.

**Key 2 — venues & weather (recommended, free): football-data.org**

1. Go to **football-data.org** → **Get your free API token** → register
   with your email.
2. The token appears on your account page / arrives by email.
3. This maps each fixture to its stadium, which unlocks the kickoff weather
   forecast (the weather service itself, Open-Meteo, needs no key) and the
   altitude notes for the Mexican venues.

**Key 3 — AI news desk (optional, ~a few cents/day): Anthropic**

Skip this entirely if you want a 100% free setup — you'll still get weather,
altitude and odds-movement reasoning. With it, Claude web-searches each
fixture every morning for confirmed injuries, suspensions and rotation news.

1. Go to **console.anthropic.com** → create an account.
2. **Settings → Billing** → add the minimum credit (US$5 lasts the whole
   tournament at this usage).
3. **Settings → API keys → Create key**. Copy it immediately — it's shown
   only once.

## Phase 5 — Give the keys to GitHub, securely (5 min)

Secrets are encrypted storage attached to your repo; they never appear in
the public files.

1. In your repo: **Settings** (top tab) → left sidebar **Secrets and
   variables → Actions** → green button **New repository secret**.
2. Add one secret per key. The **Name must match exactly**, including
   capitals and underscores:

   | Name | Value |
   |---|---|
   | `ODDS_API_KEY` | your The Odds API key |
   | `FOOTBALL_DATA_KEY` | your football-data.org token |
   | `ANTHROPIC_API_KEY` | your Anthropic key (only if you did Key 3) |

3. Paste each value with no extra spaces or quotes, click **Add secret**.

## Phase 6 — Turn on the website (2 min)

1. Repo **Settings → Pages** (left sidebar).
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. That's it — nothing else on that page.

## Phase 7 — First run (3 min)

1. Click the **Actions** tab. If a banner asks you to enable workflows,
   click **"I understand my workflows, go ahead and enable them"**.
2. In the left sidebar, click **Daily briefing** → button **Run workflow**
   → green **Run workflow**.
3. Refresh after a few seconds; a run appears. Yellow dot = working,
   green tick = done (1–2 minutes), red X = see troubleshooting below.
4. Click the finished run — the website URL is shown in the **deploy** step,
   in the form `https://YOURNAME.github.io/wc26-analyzer/`.
5. Open it. Your briefing is live.

From now on it re-runs by itself every morning. GitHub's scheduler can run
5–30 minutes late — normal, nothing to fix.

## Phase 8 — Make it feel like an app (1 min)

On your phone, open the URL in the browser → Share / menu → **Add to Home
Screen**. One tap each morning with your coffee.

---

## Troubleshooting

**"Daily briefing" doesn't appear in the Actions tab.**
Phase 3 Part B was missed or the path is wrong. The file must be exactly at
`.github/workflows/daily.yml` — check the repo file list for the `.github`
folder and fix the path if needed.

**Run fails with a red X.**
Click the run → click the failed step → read the last lines of the log.
The usual suspects:
- `Set the ODDS_API_KEY environment variable` → the secret is missing or
  the name has a typo. Re-do Phase 5; names are case-sensitive.
- `401`/`Unauthorized` → key pasted with a stray space or quote. Delete the
  secret and re-add it.
- `No FIFA World Cup sport key found` → bookmakers haven't listed the next
  round's matches yet (common in the gap between rounds). It fixes itself;
  re-run later or just wait for tomorrow's run.

**Run is green but `0 events` / empty page.**
Same gap-between-rounds situation: <not a bug — bookmakers list matches
closer to kickoff. The page will say there's nothing to bet today, which is
the correct answer on such days.

**Website shows 404.**
Phase 6 not done (Pages source must be **GitHub Actions**), or the first
deploy hasn't finished. Give it two minutes after a green run.

**The weather/news notes are missing but odds work.**
Those layers fail soft. The run log says exactly which key was skipped or
which service errored; everything else continues.

**I want a different time than 07:00.**
Edit `.github/workflows/daily.yml` in the GitHub web editor: the line
`- cron: "0 7 * * *"` is minute hour in UTC (= Icelandic time year-round),
so `"30 8 * * *"` = 08:30.

---

## Cost summary

| Item | Cost |
|---|---|
| GitHub account, Actions, Pages | free (public repo) |
| The Odds API | free tier, well within quota |
| football-data.org + Open-Meteo weather | free |
| Anthropic AI news desk (optional) | ≈ $0.02–0.05 per day |

And the standing reminder: the analyzer finds the *least bad* slips, not
winning ones — the EV stamp on every ticket stays negative for a reason.
Stake small, treat it as part of enjoying the tournament, and if it stops
being fun: SÁÁ (saa.is) and the Red Cross helpline 1717.
