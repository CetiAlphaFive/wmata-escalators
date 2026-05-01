#!/usr/bin/env python3
"""Render data/escalator_outages.csv + data/stations.csv to docs/index.html."""

import csv
import datetime as dt
import html
import os
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent
SNAPSHOTS = ROOT / "data" / "escalator_outages.csv"
STATIONS = ROOT / "data" / "stations.csv"
OUT = ROOT / "docs" / "index.html"

DAY = dt.timedelta(days=1)
WEEK = dt.timedelta(days=7)


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_stations() -> list[tuple[str, str]]:
    with STATIONS.open() as f:
        return [(r["StationCode"], r["StationName"]) for r in csv.DictReader(f)]


def load_snapshots():
    """Returns (rows, all_ts_sorted). rows = list of dict."""
    rows = []
    if not SNAPSHOTS.exists():
        return rows, []
    with SNAPSHOTS.open() as f:
        for r in csv.DictReader(f):
            r["_ts"] = parse_ts(r["snapshot_ts"])
            rows.append(r)
    all_ts = sorted({r["_ts"] for r in rows})
    return rows, all_ts


def compute_metrics(stations, rows, all_ts):
    """Per station: current outage count, day uptime %, week uptime %, latest snapshot ts."""
    if not all_ts:
        return {code: dict(current=None, day=None, week=None, latest=None,
                           current_units=[]) for code, _ in stations}

    latest_ts = all_ts[-1]
    day_cutoff = latest_ts - DAY
    week_cutoff = latest_ts - WEEK

    # snapshot_ts -> set of station codes that had >=1 outage at that snapshot
    by_snapshot = defaultdict(set)
    # snapshot_ts -> station -> list of unit dicts (for current outage details)
    detail = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_snapshot[r["_ts"]].add(r["StationCode"])
        detail[r["_ts"]][r["StationCode"]].append(r)

    day_ts = [t for t in all_ts if t > day_cutoff]
    week_ts = [t for t in all_ts if t > week_cutoff]

    out = {}
    for code, _ in stations:
        current_units = detail[latest_ts].get(code, [])
        current_count = len(current_units)

        def uptime(ts_list):
            if not ts_list:
                return None
            up = sum(1 for t in ts_list if code not in by_snapshot[t])
            return up / len(ts_list)

        out[code] = dict(
            current=current_count,
            day=uptime(day_ts),
            week=uptime(week_ts),
            latest=latest_ts,
            current_units=current_units,
        )
    return out


def light(current: int | None) -> tuple[str, str]:
    if current is None:
        return "gray", "no data"
    if current == 0:
        return "green", "all up"
    if current == 1:
        return "yellow", "1 down"
    return "red", f"{current} down"


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.0f}%"


def fmt_frac(x, total):
    if x is None:
        return "—"
    return f"{int(round(x * total))}/{total}"


def render(stations, metrics, all_ts) -> str:
    latest = all_ts[-1] if all_ts else None
    day_ts_count = sum(1 for t in all_ts if t > (latest - DAY)) if latest else 0
    week_ts_count = sum(1 for t in all_ts if t > (latest - WEEK)) if latest else 0

    rows_html = []
    for code, name in sorted(stations, key=lambda x: x[1]):
        m = metrics[code]
        color, label = light(m["current"])
        units_text = ""
        if m["current_units"]:
            parts = []
            for u in m["current_units"]:
                loc = u.get("LocationDescription", "") or ""
                sym = u.get("SymptomDescription", "") or ""
                unit_id = u.get("UnitName", "") or ""
                parts.append(f"{html.escape(unit_id)}: {html.escape(loc)} ({html.escape(sym)})")
            units_text = "<br>".join(parts)
        rows_html.append(f"""
<tr class="row-{color}">
  <td><span class="dot dot-{color}" title="{label}"></span></td>
  <td>{html.escape(name)}</td>
  <td class="code">{html.escape(code)}</td>
  <td>{label}</td>
  <td class="num">{fmt_pct(m['day'])}</td>
  <td class="num">{fmt_pct(m['week'])}</td>
  <td class="units">{units_text}</td>
</tr>""")

    summary_green = sum(1 for m in metrics.values() if m["current"] == 0)
    summary_yellow = sum(1 for m in metrics.values() if m["current"] == 1)
    summary_red = sum(1 for m in metrics.values() if (m["current"] or 0) >= 2)
    summary_unknown = sum(1 for m in metrics.values() if m["current"] is None)

    latest_str = latest.strftime("%Y-%m-%d %H:%M UTC") if latest else "no snapshots yet"
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>DC Metro Escalator Status</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1100px; margin: 1.5rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ margin: 0 0 0.25rem; font-size: 1.4rem; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 1rem; }}
  .summary {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  .pill {{ padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.85rem;
          border: 1px solid #ddd; background: #fafafa; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; text-align: left;
           vertical-align: top; }}
  th {{ background: #f5f5f5; font-weight: 600; cursor: default; user-select: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .code {{ font-family: ui-monospace, monospace; color: #888; font-size: 0.85rem; }}
  .units {{ font-size: 0.8rem; color: #555; max-width: 360px; }}
  .dot {{ display: inline-block; width: 14px; height: 14px; border-radius: 50%;
         vertical-align: middle; }}
  .dot-green  {{ background: #2ecc71; }}
  .dot-yellow {{ background: #f1c40f; }}
  .dot-red    {{ background: #e74c3c; }}
  .dot-gray   {{ background: #bbb; }}
  .row-red td {{ background: #fff5f4; }}
  .row-yellow td {{ background: #fffdf2; }}
  footer {{ margin-top: 2rem; color: #888; font-size: 0.8rem; }}
  a {{ color: #2858b8; }}
</style>
</head>
<body>
<h1>DC Metro Escalator Status</h1>
<div class="meta">
  Latest snapshot: <strong>{latest_str}</strong> · Page generated: {generated}
</div>
<div class="summary">
  <span class="pill"><span class="dot dot-green"></span> {summary_green} all up</span>
  <span class="pill"><span class="dot dot-yellow"></span> {summary_yellow} one down</span>
  <span class="pill"><span class="dot dot-red"></span> {summary_red} multiple down</span>
  {"<span class='pill'><span class='dot dot-gray'></span> " + str(summary_unknown) + " no data</span>" if summary_unknown else ""}
</div>
<table>
<thead>
<tr><th></th><th>Station</th><th>Code</th><th>Now</th>
    <th class="num">Day uptime</th><th class="num">Week uptime</th>
    <th>Currently down</th></tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
<footer>
  Uptime = % of hourly snapshots with zero outages reported at that station.
  Day = trailing 24 h ({day_ts_count} snapshots). Week = trailing 7 d ({week_ts_count} snapshots).
  Source: <a href="https://developer.wmata.com/">WMATA API</a> · scraper:
  <a href="https://github.com/CetiAlphaFive/wmata-escalators">wmata-escalators</a>.
</footer>
</body>
</html>
"""


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    stations = load_stations()
    rows, all_ts = load_snapshots()
    metrics = compute_metrics(stations, rows, all_ts)
    OUT.write_text(render(stations, metrics, all_ts))
    print(f"wrote {OUT} with {len(stations)} stations, {len(all_ts)} snapshots")


if __name__ == "__main__":
    main()
