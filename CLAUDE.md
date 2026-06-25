# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Hourly snapshot tracker of DC Metro (WMATA) escalator outages. Three things share the same `data/` dir but do not share code:

1. **Static site** (`docs/index.html`) — public dashboard rendered hourly by GitHub Actions, served via GitHub Pages at https://cetialphafive.github.io/wmata-escalators/. The published artifact.
2. **Shiny app** (`app.R`) — local live-view tool (not deployed). Polls WMATA API every 60 s. Falls back to bundled JSON/CSV fixtures when `WMATA_API_KEY` unset.
3. **Offline analysis layer** (`scripts/r/`) — exploratory tidyverse R scripts that read the same `data/` CSVs and emit plots to `plots/`. Run by hand; not wired into any pipeline, not deployed.

The static site is the only published surface. The Shiny app is for ad-hoc inspection; the R scripts are for one-off data exploration.

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

```sh
# Regenerate exploratory analysis plots (writes plots/*.png)
Rscript scripts/r/plot_cuts.R                     # 8 "cuts" of the outage history
Rscript scripts/r/plot_cut1_dig.R                 # drill-down on the pre-rush outage spike
Rscript scripts/r/plot_outage_count_by_hour.R     # raw outage count, hour-of-day x line
Rscript scripts/r/plot_outage_fraction_by_hour.R  # outage fraction, hour-of-day x line
```

No tests, no linter, no build step beyond `render.py`. Python stdlib only (no requirements.txt). R deps: the Shiny app's are in README.local.md; the analysis scripts need tidyverse (`readr dplyr tidyr lubridate ggplot2 stringr forcats scales`), plus `patchwork` for `plot_cut1_dig.R`.

## Architecture

### Hourly pipeline (GitHub Actions, `.github/workflows/scrape.yml`)

`cron: "0 * * * *"` → `scrape.sh` → `render.py` → commit `data/` + `docs/` → push. Concurrency group `scrape` prevents overlapping runs. Bot identity: `github-actions[bot]`. The push step is self-healing: on a non-fast-forward rejection it rebases the append-only CSV, re-renders `docs/index.html` from the merged data (never 3-way-merges generated HTML), amends into the single snapshot commit, and retries. If you push manually, expect frequent merges from the bot.

### `scrape.sh`

Curl WMATA `Incidents.svc/json/ElevatorIncidents`, filter `UnitType == "ESCALATOR"` with `jq`, append rows tagged with UTC `snapshot_ts` to `data/escalator_outages.csv`. Header written only if file absent. **Escalator outages are reported via the elevator endpoint** — WMATA's API quirk, not a bug.

### `render.py`

Reads:
- `data/stations.csv` — canonical station list with `StationCode,StationName,Lines` (lines comma-separated, e.g. `RD,YL`).
- `data/escalator_outages.csv` — full append-only history.

Computes per-station: current down count, trailing-24 h uptime, trailing-7 d uptime, all-time uptime, and a week down-count series for the sparkline. **Uptime definition: fraction of snapshots in which the station has zero rows in the outages CSV.** Day/week windows are defined relative to the latest snapshot in the file, not wall-clock now.

Emits one self-contained `docs/index.html` (inlined CSS + JS). Filtering is client-side only (status pills + line pills). Color gradient on uptime cells via `uptime_bg()` (HSL interpolation: green ≥1.0, yellow ≈0.95, red ≤0.80).

### `app.R` (Shiny)

`bslib` + `httr2` + `DT` + optional `leaflet`. Map tab appears only if leaflet namespace loads. `stations` reactive cached via `bindCache("stations")`. `incidents` re-fetched every 60 s (`invalidateLater`) or on refresh button. Fixture mode: `stations_sample.csv` + `incidents_sample.json` — six fake outages across five stations.

### `scripts/r/` (analysis cuts)

Exploratory, run-by-hand R that reads `data/*.csv` and writes `plots/`. None of it feeds the static site or the Shiny app. The unit of analysis here differs from `render.py`:

- **Outage instance** := unique `(UnitName, DateOutOfServ)` — one physical breakdown, regardless of how many hourly snapshots observed it. (`render.py` instead counts per-snapshot zero/non-zero presence; do not conflate the two.)
- **Duration** := last snapshot in which the instance was seen − `DateOutOfServ`. **Censored** when last-seen == the max snapshot in the file (still down at end of data).
- **Line attribution double-counts transfer stations.** An outage row is attributed to every line serving its `StationCode` (F01 → GR+YL, B01 → RD). Per-line series are "outages affecting line L", not a partition of total outages. The outage CSV records the platform-specific `StationCode`, so e.g. F01 outages count only toward Green/Yellow, never Red.
- `plot_cuts.R` writes `plots/cut_NN_<name>.png` (8 cuts). `plot_cut1_dig.R` drills into the pre-rush-hour spike, testing whether it's scheduled maintenance vs. genuine failures via the symptom mix.

## Data files — invariants

- `data/escalator_outages.csv`: **append-only, immutable history**. Never rewrite or sort. Every row = one outage observed at one snapshot. Multiple rows per `(snapshot_ts, StationCode)` = multiple escalators down. Columns: `snapshot_ts,StationCode,StationName,UnitName,LocationDescription,SymptomDescription,DateOutOfServ,EstimatedReturnToService`.
- `data/stations.csv`: canonical list. Edit by hand if WMATA opens/closes stations.
- `incidents_sample.json`, `stations_sample.csv`: demo fixtures for Shiny app — do not delete.
- `data/escalator_inventory.csv`: per-station escalator counts. Built by `scripts/build_inventory.py`. **Source = `UnitName` ordinal inference from outage history** (max ordinal per zone, summed per StationCode). Validated against three WMATA-published whole-station counts (L'Enfant 31, Gallery Pl 30, Metro Center 25). 7 zero-history stations (Silver Line Phase 2 + Potomac Yard) marked `pending`; Forest Glen B09 is manually 0 (elevator-only station). Regenerate when adding meaningful new outage history.

When changing CSV schema, update `scrape.sh` header, `render.py` `load_snapshots`, the `read_csv` calls in `scripts/r/*.R`, and verify the old rows still parse (no migration script exists).

## Cross-surface conventions

These leak across the otherwise-independent surfaces. Get them wrong and the surfaces silently disagree.

- **`LINE_COLORS` is duplicated, not shared.** The WMATA brand hex map (`RD OR YL GR BL SV`) is copy-pasted into `render.py` AND into every `scripts/r/*.R`. Changing a line color means editing all of them; there is no single source of truth across surfaces. (Within `render.py` it really is one dict — see Editing notes.)
- **Timezone depends on the column.** `snapshot_ts` carries a `Z` and is UTC. `DateOutOfServ` and `EstimatedReturnToService` have **no timezone marker** in WMATA's source; the R scripts treat them as `America/New_York` (WMATA's operational TZ). `render.py` works in snapshot-presence space and sidesteps this, but any new time math on the outage start/ETA fields must choose a TZ deliberately.

## Editing notes

- `render.py` is structured so the big f-string in `render()` only interpolates values — CSS and JS live in plain-string module constants (`CSS`, `JS`). Do NOT inline CSS/JS back into the f-string: braces in selectors and JS blocks would need `{{` `}}` doubling.
- Line colors within the static site live in one dict: `LINE_COLORS` at top of `render.py`. `_line_color_rules()` emits `.line-pill` + `.line-chip` CSS; `_line_filter_pills()` emits the filter buttons. Add/remove a WMATA line by editing `LINE_COLORS` (then mirror it into the R scripts — see Cross-surface conventions).
- WMATA line codes: `RD OR YL GR BL SV`.
- `scrape.sh` uses `set -euo pipefail` and `curl --fail-with-body`. A 4xx/5xx aborts the workflow; the cron retries next hour.

## UnitName encoding

`UnitName` in `data/escalator_outages.csv` matches `^([A-Z]\d{2})([A-Z])(\d+)$` — station code + zone letter + ordinal. Examples: `A03N03`, `D03W09`. The **embedded station prefix is more authoritative than the `StationCode` column** — WMATA's source data mis-labels a small number of rows (e.g., escalators at E06 Brookland logged under B06 Rhode Island Ave). `scripts/validate_inventory.py` surfaces mismatches.

Inventory inference exploits this: `max(ordinal)` per `(station, zone)` summed across zones = WMATA's true count for that StationCode. Confirmed against three published whole-station counts.
