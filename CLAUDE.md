# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Hourly snapshot tracker of DC Metro (WMATA) escalator outages. Two independent surfaces share the same data dir:

1. **Static site** (`docs/index.html`) — public dashboard rendered hourly by GitHub Actions, served via GitHub Pages at https://cetialphafive.github.io/wmata-escalators/.
2. **Shiny app** (`app.R`) — local live-view tool (not deployed). Polls WMATA API every 60 s. Falls back to bundled JSON/CSV fixtures when `WMATA_API_KEY` unset.

The two surfaces do not share code. The Shiny app is for ad-hoc inspection; the static site is the published artifact.

## Commands

```sh
# Scrape one snapshot (appends to data/escalator_outages.csv)
WMATA_API_KEY=... ./scrape.sh

# Rebuild docs/index.html from CSV history
python3 render.py

# Run Shiny app locally
R -e 'shiny::runApp(".")'
# or, live mode:
WMATA_API_KEY=... R -e 'shiny::runApp(".")'
```

```sh
# Rebuild ground-truth escalator inventory (data/escalator_inventory.csv)
python3 scripts/build_inventory.py

# Validate inventory against outage history + WMATA-published counts
python3 scripts/validate_inventory.py
```

No tests, no linter, no build step beyond `render.py`. Python stdlib only (no requirements.txt). R deps listed in README.local.md.

## Architecture

### Hourly pipeline (GitHub Actions, `.github/workflows/scrape.yml`)

`cron: "0 * * * *"` → `scrape.sh` → `render.py` → commit `data/` + `docs/` → push. Concurrency group `scrape` prevents overlapping runs. Bot identity: `github-actions[bot]`. Auto-commits get scheduled hourly; if you push manually, expect frequent merges from the bot.

### `scrape.sh`

Curl WMATA `Incidents.svc/json/ElevatorIncidents`, filter `UnitType == "ESCALATOR"` with `jq`, append rows tagged with UTC `snapshot_ts` to `data/escalator_outages.csv`. Header written only if file absent. **Escalator outages are reported via the elevator endpoint** — WMATA's API quirk, not a bug.

### `render.py`

Reads:
- `data/stations.csv` — canonical station list with `StationCode,StationName,Lines` (lines comma-separated, e.g. `RD,YL`).
- `data/escalator_outages.csv` — full append-only history (~14 k rows).

Computes per-station: current down count, trailing-24 h uptime, trailing-7 d uptime, all-time uptime, and a week down-count series for the sparkline. **Uptime definition: fraction of snapshots in which the station has zero rows in the outages CSV.** Day/week windows are defined relative to the latest snapshot in the file, not wall-clock now.

Emits one self-contained `docs/index.html` (inlined CSS + JS). Filtering is client-side only (status pills + line pills). Color gradient on uptime cells via `uptime_bg()` (HSL interpolation: green ≥1.0, yellow ≈0.95, red ≤0.80).

### `app.R` (Shiny)

`bslib` + `httr2` + `DT` + optional `leaflet`. Map tab appears only if leaflet namespace loads. `stations` reactive cached via `bindCache("stations")`. `incidents` re-fetched every 60 s (`invalidateLater`) or on refresh button. Fixture mode: `stations_sample.csv` + `incidents_sample.json` — six fake outages across five stations.

## Data files — invariants

- `data/escalator_outages.csv`: **append-only, immutable history**. Never rewrite or sort. Every row = one outage observed at one snapshot. Multiple rows per `(snapshot_ts, StationCode)` = multiple escalators down.
- `data/stations.csv`: canonical list. Edit by hand if WMATA opens/closes stations.
- `incidents_sample.json`, `stations_sample.csv`: demo fixtures for Shiny app — do not delete.
- `data/escalator_inventory.csv`: per-station escalator counts. Built by `scripts/build_inventory.py`. **Source = `UnitName` ordinal inference from outage history** (max ordinal per zone, summed per StationCode). Validated against three WMATA-published whole-station counts (L'Enfant 31, Gallery Pl 30, Metro Center 25). 7 zero-history stations (Silver Line Phase 2 + Potomac Yard) marked `pending`; Forest Glen B09 is manually 0 (elevator-only station). Regenerate when adding meaningful new outage history.

When changing CSV schema, update `scrape.sh` header, `render.py` `load_snapshots`, and verify the old rows still parse (no migration script exists).

## Editing notes

- `render.py` is structured so the big f-string in `render()` only interpolates values — CSS and JS live in plain-string module constants (`CSS`, `JS`). Do NOT inline CSS/JS back into the f-string: braces in selectors and JS blocks would need `{{` `}}` doubling.
- Line colors live in one dict: `LINE_COLORS` at top of `render.py`. `_line_color_rules()` emits `.line-pill` + `.line-chip` CSS; `_line_filter_pills()` emits the filter buttons. Add/remove a WMATA line by editing `LINE_COLORS` only.
- WMATA line codes: `RD OR YL GR BL SV`.
- `scrape.sh` uses `set -euo pipefail` and `curl --fail-with-body`. A 4xx/5xx aborts the workflow; the cron retries next hour.

## UnitName encoding

`UnitName` in `data/escalator_outages.csv` matches `^([A-Z]\d{2})([A-Z])(\d+)$` — station code + zone letter + ordinal. Examples: `A03N03`, `D03W09`. The **embedded station prefix is more authoritative than the `StationCode` column** — WMATA's source data mis-labels a small number of rows (e.g., escalators at E06 Brookland logged under B06 Rhode Island Ave). `scripts/validate_inventory.py` surfaces mismatches.

Inventory inference exploits this: `max(ordinal)` per `(station, zone)` summed across zones = WMATA's true count for that StationCode. Confirmed against three published whole-station counts.
