#!/usr/bin/env python3
"""Render data/escalator_outages.csv + data/stations.csv to docs/index.html."""

import csv
import datetime as dt
import html
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


def load_stations():
    out = []
    with STATIONS.open() as f:
        for r in csv.DictReader(f):
            lines = [x for x in (r.get("Lines") or "").split(",") if x]
            out.append((r["StationCode"], r["StationName"], lines))
    return out


def load_snapshots():
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
    if not all_ts:
        return {code: dict(current=None, day=None, week=None, overall=None,
                           latest=None, current_units=[], week_series=[])
                for code, _, _ in stations}

    latest_ts = all_ts[-1]
    day_cutoff = latest_ts - DAY
    week_cutoff = latest_ts - WEEK

    by_snapshot = defaultdict(set)
    down_count = defaultdict(lambda: defaultdict(int))
    detail = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_snapshot[r["_ts"]].add(r["StationCode"])
        down_count[r["_ts"]][r["StationCode"]] += 1
        detail[r["_ts"]][r["StationCode"]].append(r)

    day_ts = [t for t in all_ts if t > day_cutoff]
    week_ts = [t for t in all_ts if t > week_cutoff]

    out = {}
    for code, _, _ in stations:
        current_units = detail[latest_ts].get(code, [])
        current_count = len(current_units)

        def uptime(ts_list):
            if not ts_list:
                return None
            up = sum(1 for t in ts_list if code not in by_snapshot[t])
            return up / len(ts_list)

        week_series = [down_count[t].get(code, 0) for t in week_ts]

        out[code] = dict(
            current=current_count,
            day=uptime(day_ts),
            week=uptime(week_ts),
            overall=uptime(all_ts),
            latest=latest_ts,
            current_units=current_units,
            week_series=week_series,
        )
    return out


def light(current):
    if current is None:
        return "gray", "no data"
    if current == 0:
        return "green", "all up"
    if current == 1:
        return "yellow", "1 down"
    return "red", f"{current} down"


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.0f}%"


def uptime_bg(x):
    """Gradient bg color for an uptime fraction (0..1). None → blank."""
    if x is None:
        return ""
    # 1.0 → green, 0.95 → yellow, ≤0.80 → red. Interpolate in HSL.
    if x >= 0.95:
        # 120° (green) at 1.0 → 60° (yellow) at 0.95
        h = 60 + (x - 0.95) / 0.05 * 60
    else:
        # 60° (yellow) at 0.95 → 0° (red) at 0.80
        h = max(0, (x - 0.80) / 0.15 * 60)
    return f"background:hsl({h:.0f}, 75%, 88%);"


def sparkline_svg(series, width=120, height=14):
    """Render week down-count series as compact SVG bars.

    0 (all up) → green tick at baseline. n>0 → red bar scaled by max.
    """
    if not series:
        return ""
    n = len(series)
    bar_w = width / n
    peak = max(series) or 1
    parts = [f'<svg class="spark" viewBox="0 0 {width} {height}" '
             f'preserveAspectRatio="none" width="{width}" height="{height}">']
    for i, v in enumerate(series):
        x = i * bar_w
        w = max(bar_w - 0.3, 0.5)
        if v == 0:
            parts.append(f'<rect x="{x:.2f}" y="{height-2}" width="{w:.2f}" '
                         f'height="2" fill="#2ecc71"/>')
        else:
            h = max(2, (v / peak) * (height - 1))
            parts.append(f'<rect x="{x:.2f}" y="{height-h:.2f}" width="{w:.2f}" '
                         f'height="{h:.2f}" fill="#e74c3c"/>')
    parts.append("</svg>")
    return "".join(parts)


def worst_table(stations_by_code, metrics, key, label, n=10):
    """Top-n stations by downtime (1 - uptime[key])."""
    ranked = []
    for code, m in metrics.items():
        u = m.get(key)
        if u is None:
            continue
        ranked.append((1 - u, code, m))
    ranked.sort(reverse=True)
    rows = []
    for rank, (down, code, m) in enumerate(ranked[:n], 1):
        if down <= 0:
            break
        name = stations_by_code.get(code, code)
        style = uptime_bg(1 - down)
        rows.append(
            f'<tr><td class="rank">{rank}</td>'
            f'<td>{html.escape(name)}</td>'
            f'<td class="code">{html.escape(code)}</td>'
            f'<td class="num" style="{style}">{down*100:.1f}%</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="4" class="empty">no downtime recorded</td></tr>')
    return (f'<div class="worst-card"><h3>{label}</h3>'
            f'<table class="worst"><thead><tr><th>#</th><th>Station</th>'
            f'<th>Code</th><th class="num">Down</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render(stations, metrics, all_ts):
    latest = all_ts[-1] if all_ts else None
    day_ts_count = sum(1 for t in all_ts if t > (latest - DAY)) if latest else 0
    week_ts_count = sum(1 for t in all_ts if t > (latest - WEEK)) if latest else 0

    rows_html = []
    for code, name, lines in sorted(stations, key=lambda x: x[1]):
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
        line_chips = "".join(
            f'<span class="line-chip line-{l}" title="{l}">{l}</span>' for l in lines
        )
        spark = sparkline_svg(m.get("week_series", []))
        day_style = uptime_bg(m["day"])
        week_style = uptime_bg(m["week"])
        overall_style = uptime_bg(m["overall"])
        rows_html.append(f"""
<tr class="row-{color}" data-status="{color}" data-lines="{','.join(lines)}">
  <td><span class="dot dot-{color}" title="{label}"></span></td>
  <td>{html.escape(name)}</td>
  <td class="code">{html.escape(code)}</td>
  <td class="lines-cell">{line_chips}</td>
  <td>{label}</td>
  <td class="num" style="{day_style}">{fmt_pct(m['day'])}</td>
  <td class="num" style="{week_style}">{fmt_pct(m['week'])}</td>
  <td class="num" style="{overall_style}">{fmt_pct(m['overall'])}</td>
  <td class="spark-cell">{spark}</td>
  <td class="units">{units_text}</td>
</tr>""")

    summary_green = sum(1 for m in metrics.values() if m["current"] == 0)
    summary_yellow = sum(1 for m in metrics.values() if m["current"] == 1)
    summary_red = sum(1 for m in metrics.values() if (m["current"] or 0) >= 2)
    summary_unknown = sum(1 for m in metrics.values() if m["current"] is None)
    fully_up_week = sum(1 for m in metrics.values()
                        if m["week"] is not None and m["week"] >= 0.999)
    partial_week = sum(1 for m in metrics.values()
                       if m["week"] is not None and m["week"] < 0.999)

    name_by_code = {code: name for code, name, _ in stations}
    worst_panels = (
        '<div class="worst-grid">'
        + worst_table(name_by_code, metrics, "week", "10 Worst — Last Week")
        + worst_table(name_by_code, metrics, "overall", "10 Worst — Overall")
        + "</div>"
    )

    latest_str = latest.strftime("%Y-%m-%d %H:%M UTC") if latest else "no snapshots yet"
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    unknown_pill = ""
    if summary_unknown:
        unknown_pill = (f"<span class='pill' data-filter-status='gray'>"
                        f"<span class='dot dot-gray'></span> {summary_unknown} no data</span>")

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
  .filters {{ display: flex; gap: 1rem; flex-wrap: wrap; align-items: center;
              margin-bottom: 1rem; }}
  .filter-group {{ display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }}
  .filter-label {{ font-size: 0.8rem; color: #666; margin-right: 0.25rem; }}
  .pill {{ padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.85rem;
          border: 1px solid #ddd; background: #fafafa; cursor: pointer;
          user-select: none; transition: opacity 0.15s, filter 0.15s; }}
  .pill:hover {{ background: #f0f0f0; }}
  .pill.off {{ opacity: 0.35; filter: grayscale(0.6); }}
  .line-pill {{ color: white; font-weight: 600; border: none;
                padding: 0.2rem 0.7rem; }}
  .line-pill.line-RD {{ background: #BF0D3E; }}
  .line-pill.line-OR {{ background: #ED8B00; }}
  .line-pill.line-YL {{ background: #d6a800; }}
  .line-pill.line-GR {{ background: #00B140; }}
  .line-pill.line-BL {{ background: #009CDE; }}
  .line-pill.line-SV {{ background: #7a8585; }}
  .reset-btn {{ font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 4px;
                border: 1px solid #ccc; background: white; cursor: pointer; }}
  .reset-btn:hover {{ background: #f0f0f0; }}
  .lines-cell {{ white-space: nowrap; }}
  .line-chip {{ display: inline-block; color: white; font-size: 0.7rem;
                font-weight: 600; padding: 0.1rem 0.35rem; border-radius: 3px;
                margin-right: 2px; }}
  .line-chip.line-RD {{ background: #BF0D3E; }}
  .line-chip.line-OR {{ background: #ED8B00; }}
  .line-chip.line-YL {{ background: #d6a800; }}
  .line-chip.line-GR {{ background: #00B140; }}
  .line-chip.line-BL {{ background: #009CDE; }}
  .line-chip.line-SV {{ background: #7a8585; }}
  .empty-msg {{ padding: 1.5rem; text-align: center; color: #888; display: none; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; text-align: left;
           vertical-align: top; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
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
  .spark-cell {{ width: 130px; padding: 0.3rem 0.4rem; }}
  .spark {{ display: block; }}
  .summary-stats {{ display: flex; gap: 1rem; flex-wrap: wrap;
                    margin: 0.5rem 0 1rem; font-size: 0.85rem; color: #555; }}
  .summary-stats span strong {{ color: #222; }}
  .worst-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
                 margin: 1.5rem 0; }}
  @media (max-width: 700px) {{ .worst-grid {{ grid-template-columns: 1fr; }} }}
  .worst-card {{ border: 1px solid #e5e5e5; border-radius: 6px; padding: 0.75rem 1rem;
                 background: #fafafa; }}
  .worst-card h3 {{ margin: 0 0 0.5rem; font-size: 1rem; }}
  table.worst {{ width: 100%; font-size: 0.85rem; }}
  table.worst th, table.worst td {{ padding: 0.25rem 0.4rem; }}
  table.worst .rank {{ color: #888; width: 1.5rem; text-align: right; }}
  table.worst .empty {{ color: #888; text-align: center; padding: 0.6rem; }}
  footer {{ margin-top: 2rem; color: #888; font-size: 0.8rem; }}
  a {{ color: #2858b8; }}
</style>
</head>
<body>
<h1>DC Metro Escalator Status</h1>
<div class="meta">
  Latest snapshot: <strong>{latest_str}</strong> · Page generated: {generated}
</div>
<div class="filters">
  <div class="filter-group">
    <span class="filter-label">Status:</span>
    <span class="pill" data-filter-status="green"><span class="dot dot-green"></span> {summary_green} all up</span>
    <span class="pill" data-filter-status="yellow"><span class="dot dot-yellow"></span> {summary_yellow} one down</span>
    <span class="pill" data-filter-status="red"><span class="dot dot-red"></span> {summary_red} multiple down</span>
    {unknown_pill}
  </div>
  <div class="filter-group">
    <span class="filter-label">Line:</span>
    <span class="pill line-pill line-RD" data-filter-line="RD">RD</span>
    <span class="pill line-pill line-OR" data-filter-line="OR">OR</span>
    <span class="pill line-pill line-YL" data-filter-line="YL">YL</span>
    <span class="pill line-pill line-GR" data-filter-line="GR">GR</span>
    <span class="pill line-pill line-BL" data-filter-line="BL">BL</span>
    <span class="pill line-pill line-SV" data-filter-line="SV">SV</span>
  </div>
  <button class="reset-btn" id="reset-filters">Reset</button>
</div>
<div class="summary-stats">
  <span>Past week: <strong>{fully_up_week}</strong> fully up · <strong>{partial_week}</strong> partially up (any outage)</span>
</div>
{worst_panels}
<table>
<thead>
<tr><th></th><th>Station</th><th>Code</th><th>Lines</th><th>Now</th>
    <th class="num">Day</th><th class="num">Week</th><th class="num">Overall</th>
    <th>Week trend</th>
    <th>Currently down</th></tr>
</thead>
<tbody id="station-rows">
{''.join(rows_html)}
</tbody>
</table>
<div class="empty-msg" id="empty-msg">No stations match current filters.</div>
<script>
(function() {{
  var pills = document.querySelectorAll('.pill[data-filter-status], .pill[data-filter-line]');
  var rows = document.querySelectorAll('#station-rows tr');
  var emptyMsg = document.getElementById('empty-msg');
  var resetBtn = document.getElementById('reset-filters');

  function activeSet(attr) {{
    var s = new Set();
    document.querySelectorAll('.pill[' + attr + ']').forEach(function(p) {{
      if (!p.classList.contains('off')) s.add(p.getAttribute(attr));
    }});
    return s;
  }}

  function apply() {{
    var statuses = activeSet('data-filter-status');
    var lines = activeSet('data-filter-line');
    var shown = 0;
    rows.forEach(function(r) {{
      var s = r.getAttribute('data-status');
      var ls = (r.getAttribute('data-lines') || '').split(',').filter(Boolean);
      var statusOk = statuses.size === 0 || statuses.has(s);
      var lineOk = lines.size === 0 || ls.some(function(l) {{ return lines.has(l); }});
      var visible = statusOk && lineOk;
      r.style.display = visible ? '' : 'none';
      if (visible) shown++;
    }});
    emptyMsg.style.display = shown === 0 ? 'block' : 'none';
  }}

  pills.forEach(function(p) {{
    p.addEventListener('click', function() {{
      p.classList.toggle('off');
      apply();
    }});
  }});

  resetBtn.addEventListener('click', function() {{
    pills.forEach(function(p) {{ p.classList.remove('off'); }});
    apply();
  }});
}})();
</script>
<footer>
  Click status or line pills to filter. Click again to re-enable.
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
