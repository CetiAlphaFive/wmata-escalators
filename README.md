# wmata-escalators

Hourly scraper for WMATA escalator outages. Runs on GitHub Actions, appends to `data/escalator_outages.csv`.

## Schema

One row per *outage observation per snapshot*. A unit that's out for 6 hours produces ~6 rows.

| column | source |
| --- | --- |
| `snapshot_ts` | UTC timestamp of API call (ISO-8601) |
| `StationCode` | WMATA station code (e.g. `A03`) |
| `StationName` | WMATA station name |
| `UnitName` | escalator unit ID |
| `LocationDescription` | where in station |
| `SymptomDescription` | reason out (e.g. Major Repair) |
| `DateOutOfServ` | when this outage started |
| `EstimatedReturnToService` | WMATA's estimate, often optimistic |

Filtered to `UnitType == "ESCALATOR"`. Elevators dropped.

## Schedule

`scrape.yml` cron `0 * * * *` (top of every hour, UTC). GitHub Actions cron is best-effort — can lag 5-15 min, occasional skip during platform load. Acceptable for this use case.

`workflow_dispatch` enabled for manual runs.

## Setup

1. Push this repo to GitHub
2. Add repo secret `WMATA_API_KEY` (Settings → Secrets and variables → Actions → New repository secret)
3. Workflow runs on next cron tick. Trigger immediately via Actions tab → scrape → Run workflow

## Local test

```sh
export WMATA_API_KEY=...
./scrape.sh
```

Requires `bash`, `curl`, `jq`. CSV appended to `data/escalator_outages.csv`.

## Known limits

- WMATA reports outages only — "no row for unit X" means up *or* WMATA hasn't reported. No way to distinguish.
- Hourly granularity loses sub-hour outages. If WMATA fixes a unit in 20 min between snapshots, scraper never sees it.
- Snapshot model means downtime = `last_seen_ts - first_seen_ts + 1h` (approximate).
