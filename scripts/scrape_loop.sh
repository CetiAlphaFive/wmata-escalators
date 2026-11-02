#!/usr/bin/env bash
# Hourly scrape relay, run by .github/workflows/scrape.yml.
#
# GitHub drops most scheduled runs: by fall 2026 only ~5 of the 24 hourly crons
# fired each day. So instead of one cron run per snapshot, one run stays up for
# most of the 6 h job limit, takes a snapshot at :02 past every UTC hour, and
# dispatches the next run of the workflow just before it exits. The workflow's
# sparse cron only restarts the relay if a hand-off is ever lost, and
# .github/workflows/watchdog.yml raises an alert issue if snapshots stop.
#
# One snapshot per UTC clock hour: an hour already in the CSV (e.g. taken by the
# previous run just before the hand-off) is skipped.
#
# Env (all optional): BUDGET_SECONDS, how long this run keeps looping (default
# 5 h 30 m, leaving room under the job's 355-minute timeout); SNAP_MINUTE (2);
# SCRAPE_CMD (./scrape.sh); DRY_RUN=1 skips the commit/push and the hand-off,
# for local testing.
set -euo pipefail

BUDGET_SECONDS="${BUDGET_SECONDS:-19800}"
SNAP_MINUTE="${SNAP_MINUTE:-2}"
SCRAPE_CMD="${SCRAPE_CMD:-./scrape.sh}"
CSV=data/escalator_outages.csv
deadline=$(( $(date +%s) + BUDGET_SECONDS ))

# "YYYY-MM-DDTHH" of the newest snapshot (rows start with "YYYY-MM-DDTHH:MM:SSZ").
newest_hour() { tail -n 1 "$CSV" | cut -c2-14; }

while :; do
  hour="$(date -u +%Y-%m-%dT%H)"
  if [[ "$(newest_hour)" == "$hour" ]]; then
    echo "$hour: already have this hour's snapshot"
  else
    scraped=false
    for attempt in 1 2 3; do
      if $SCRAPE_CMD; then scraped=true; break; fi
      echo "::warning title=Scrape failed::$hour, attempt $attempt"
      sleep 120
    done
    if [[ "$scraped" != true ]]; then
      echo "::warning title=Snapshot skipped::no snapshot for $hour after 3 attempts"
    elif [[ -n "${DRY_RUN:-}" ]]; then
      echo "DRY_RUN: not committing"
    elif ! ./scripts/commit_snapshot.sh; then
      # The commit stays local and goes out with the next hour's push.
      echo "::warning title=Push failed::$hour snapshot not pushed yet"
    fi
  fi

  now=$(date +%s)
  next=$(( (now / 3600 + 1) * 3600 + SNAP_MINUTE * 60 ))
  if (( next >= deadline )); then break; fi
  sleep $(( next - now ))
done

# Hand off. The workflow's concurrency group holds the new run until this one
# exits; a run dispatched with GITHUB_TOKEN is allowed to start (workflow_dispatch
# is the documented exception to the no-recursive-runs rule).
if [[ -n "${DRY_RUN:-}" ]]; then
  echo "DRY_RUN: not dispatching the next run"
  exit 0
fi
for attempt in 1 2 3; do
  if gh workflow run scrape.yml -R "$GITHUB_REPOSITORY" --ref "$GITHUB_REF_NAME"; then
    echo "dispatched the next run"
    exit 0
  fi
  sleep 30
done
echo "::error title=Relay hand-off failed::the backstop cron will restart the relay"
exit 1
