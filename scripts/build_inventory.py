#!/usr/bin/env python3
"""Build data/escalator_inventory.csv from outage history + manual overrides.

Primary method: max ordinal per (station, zone) from UnitName field of
data/escalator_outages.csv. Validates against three published WMATA counts
(L'Enfant 31, Gallery Pl 30, Metro Center 25). See notes/inventory_sources.md.

Stations with no outage history get manual overrides (8 stations: 6 Silver
Line Phase 2, Potomac Yard, Forest Glen). Forest Glen is famously
elevator-only — 0 escalators.

Output schema:
    StationCode, StationName, escalator_count, source, source_ref,
    retrieved_at, notes
"""

import csv
import datetime as dt
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTAGES = ROOT / "data" / "escalator_outages.csv"
STATIONS = ROOT / "data" / "stations.csv"
OUT = ROOT / "data" / "escalator_inventory.csv"

UNIT_PAT = re.compile(r"^([A-Z]\d{2})([A-Z])(\d+)$")

# Manual overrides for stations with no outage history (verified separately).
# Source/notes recorded per row. Set count=None to leave blank pending fallback.
MANUAL = {
    "B09": dict(
        count=0,
        source="manual_verified",
        source_ref="https://en.wikipedia.org/wiki/Forest_Glen_station",
        notes="Deepest station in system; elevator-only access, zero escalators.",
    ),
    # Silver Line Phase 2 + Potomac Yard: pending fallback (OSM or manual count).
    "N07": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "N08": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "N09": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "N10": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "N11": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "N12": dict(count=None, source="pending", source_ref="",
                notes="Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual."),
    "C11": dict(count=None, source="pending", source_ref="",
                notes="Potomac Yard (opened 2023-05-19). Needs OSM/manual."),
}


def load_stations():
    with STATIONS.open() as f:
        return [(r["StationCode"], r["StationName"]) for r in csv.DictReader(f)]


def infer_from_outages():
    """Return {station_code: {"count": int, "zones": {zone: max_ord, ...},
                              "observed_unique": int, "gaps": {...}}}."""
    max_ord = defaultdict(lambda: defaultdict(int))
    observed_ords = defaultdict(lambda: defaultdict(set))
    units_per_stn = defaultdict(set)

    with OUTAGES.open() as f:
        for r in csv.DictReader(f):
            m = UNIT_PAT.match(r["UnitName"] or "")
            if not m:
                continue
            stn, zone, num = m.group(1), m.group(2), int(m.group(3))
            if num > max_ord[stn][zone]:
                max_ord[stn][zone] = num
            observed_ords[stn][zone].add(num)
            units_per_stn[stn].add(r["UnitName"])

    out = {}
    for stn, zones in max_ord.items():
        total = sum(zones.values())
        gaps = {}
        for zone, mx in zones.items():
            miss = sorted(set(range(1, mx + 1)) - observed_ords[stn][zone])
            if miss:
                gaps[zone] = miss
        out[stn] = dict(
            count=total,
            zones=dict(zones),
            observed_unique=len(units_per_stn[stn]),
            gaps=gaps,
        )
    return out


def main():
    stations = load_stations()
    inferred = infer_from_outages()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    for code, name in stations:
        if code in inferred:
            i = inferred[code]
            zones_str = ", ".join(f"{z}:{n}" for z, n in sorted(i["zones"].items()))
            gap_str = (
                "" if not i["gaps"]
                else " | ordinal gaps: " + ", ".join(
                    f"{z}={i['gaps'][z]}" for z in sorted(i["gaps"])
                )
            )
            rows.append(dict(
                StationCode=code,
                StationName=name,
                escalator_count=i["count"],
                source="unitname_max_ord",
                source_ref="data/escalator_outages.csv",
                retrieved_at=now,
                notes=f"zones {zones_str}; observed_unique={i['observed_unique']}"
                      + gap_str,
            ))
        elif code in MANUAL:
            m = MANUAL[code]
            rows.append(dict(
                StationCode=code,
                StationName=name,
                escalator_count="" if m["count"] is None else m["count"],
                source=m["source"],
                source_ref=m["source_ref"],
                retrieved_at=now,
                notes=m["notes"],
            ))
        else:
            # Unexpected: in stations.csv but no outage history and no manual.
            rows.append(dict(
                StationCode=code,
                StationName=name,
                escalator_count="",
                source="unknown",
                source_ref="",
                retrieved_at=now,
                notes="No outage history, no manual override. Investigate.",
            ))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "StationCode", "StationName", "escalator_count",
            "source", "source_ref", "retrieved_at", "notes",
        ])
        w.writeheader()
        w.writerows(rows)

    # Summary
    counted = [r for r in rows if r["escalator_count"] != ""]
    total = sum(int(r["escalator_count"]) for r in counted)
    pending = [r["StationCode"] for r in rows if r["escalator_count"] == ""]
    print(f"wrote {OUT}")
    print(f"  {len(rows)} stations")
    print(f"  {len(counted)} with count; {len(pending)} pending: {pending}")
    print(f"  sum of known counts: {total}")
    print(f"  WMATA system-wide claimed: 647")
    print(f"  gap: {647 - total}")


if __name__ == "__main__":
    main()
