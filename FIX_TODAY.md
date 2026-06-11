# Repairing the repo — 5 minutes

## What broke
Several files in the repo contain each other's content from earlier copy-paste
edits. `analyzer/odds.py` is empty, so this morning's run died instantly with
`ImportError: cannot import name 'build_legs'` before fetching any odds.

## The fix: replace everything in one upload
1. Unzip the new package on your computer.
2. In the GitHub repo: **Add file → Upload files**.
3. Drag in: `main.py`, and the entire **`analyzer`** and **`data`** FOLDERS
   (drag the folders themselves — GitHub keeps the structure and overwrites
   the broken files). Commit.
4. The workflow file lives in the hidden `.github` folder, so fix it by hand:
   open `.github/workflows/daily.yml` in the repo → pencil icon → select all →
   paste the contents of `.github/workflows/daily.yml` from the package → Commit.
5. **Actions → Bertpicker → Run workflow.**

## How you'll know it's fixed
The run now starts with a "Code integrity check" step that imports every
module and prints `integrity OK: every module is in its right file`.
If any file ever has the wrong content again, THAT step fails with the exact
filename — no more silent stale pages.

## What's new in this package (tested)
- **Scoreboard** (stadan.exe window): slips won–lost, units at 1u/slip,
  actual vs estimated hit rate, A+B vs C split, yesterday's graded legs.
  Settles on 90-minute scores; extra-time games use regular-time score.
- **Archive** ("Gamlir seðlar" in the taskbar): every day's page kept at
  /archive/YYYY-MM-DD.html with an index, committed to git so it's auditable.
- **Team-name aliases**: "South Korea"/"Korea Republic", "Czechia"/"Czech
  Republic", "USA"/"United States" etc. now match across data sources —
  without this, settlement and weather notes silently failed for those teams.
