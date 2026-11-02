#!/usr/bin/env python3
"""Watchdog check for .github/workflows/watchdog.yml.

Reads data/escalator_outages.csv and decides whether the hourly scraper is
falling behind: the newest snapshot is more than MAX_AGE_HOURS old, or fewer
than MIN_HOURS_COVERED of the last 24 full UTC hours have a snapshot.

Writes `stale=true|false` to $GITHUB_OUTPUT and a Markdown report to
freshness.md (the alert issue's body, or its closing comment).
"""
import csv
import datetime as dt
import os
import sys

CSV = "data/escalator_outages.csv"
MAX_AGE_HOURS = 3
MIN_HOURS_COVERED = 20

now = dt.datetime.now(dt.timezone.utc)
if len(sys.argv) > 1:                          # testing: check as of a given time
    now = dt.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))

with open(CSV, newline="") as f:
    stamps = {r["snapshot_ts"] for r in csv.DictReader(f)}
snaps = sorted(dt.datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps)
snaps = [t for t in snaps if t <= now]

this_hour = now.replace(minute=0, second=0, microsecond=0)
window = [this_hour - dt.timedelta(hours=h) for h in range(24, 0, -1)]
have = {t.replace(minute=0, second=0, microsecond=0) for t in snaps}
missing = [h for h in window if h not in have]
covered = 24 - len(missing)

latest = snaps[-1] if snaps else None
age_h = (now - latest).total_seconds() / 3600 if latest else float("inf")
stale = age_h > MAX_AGE_HOURS or covered < MIN_HOURS_COVERED

repo = os.environ.get("GITHUB_REPOSITORY", "CetiAlphaFive/wmata-escalators")
latest_str = latest.strftime("%Y-%m-%d %H:%M UTC") if latest else "none"
missing_str = ", ".join(h.strftime("%m-%d %H:00") for h in missing) or "none"
lines = [
    ("The hourly escalator scraper is falling behind." if stale
     else "The hourly escalator scraper has recovered."),
    "",
    f"Checked {now:%Y-%m-%d %H:%M} UTC.",
    "",
    f"- Newest snapshot: {latest_str} ({age_h:.1f} h ago; alert above {MAX_AGE_HOURS} h)",
    f"- Hours with a snapshot, last 24: {covered}/24 (alert below {MIN_HOURS_COVERED})",
    f"- Missing hours (UTC): {missing_str}",
    "",
    f"Scrape runs: https://github.com/{repo}/actions/workflows/scrape.yml",
]
if stale:
    lines.append("This issue closes itself once both checks pass again.")
report = "\n".join(lines) + "\n"

with open("freshness.md", "w") as f:
    f.write(report)
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"stale={'true' if stale else 'false'}\n")
print(report)
print(f"stale={stale}")
