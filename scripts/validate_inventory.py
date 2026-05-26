#!/usr/bin/env python3
"""Validate data/escalator_inventory.csv against outage history and known truths.

Hard checks (fail loud):
  1. Every StationCode in data/stations.csv has an inventory row.
  2. escalator_count >= 0 for filled rows (B09 = 0 allowed).
  3. Lower-bound: unique(UnitName-prefix) per station <= inferred count.
     Uses UnitName prefix as canonical station, not the StationCode column,
     because WMATA's source data occasionally mis-labels (StationCode
     disagrees with UnitName's embedded prefix).
  4. Whole-station spot-check vs WMATA's three published counts:
       L'Enfant Plaza (D03+F03) = 31
       Gallery Pl-Chinatown (F01+B01) = 30
       Metro Center (C01+A01) = 25
  5. Data-quality: flag rows where StationCode != UnitName prefix.

Writes notes/inventory_validation.md.
"""

import csv
import pathlib
import re
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
INV = ROOT / "data" / "escalator_inventory.csv"
STATIONS = ROOT / "data" / "stations.csv"
OUTAGES = ROOT / "data" / "escalator_outages.csv"
REPORT = ROOT / "notes" / "inventory_validation.md"

UNIT_PAT = re.compile(r"^([A-Z]\d{2})([A-Z])(\d+)$")

KNOWN_WHOLE_STATION = {
    "L'Enfant Plaza":      (["D03", "F03"], 31),
    "Gallery Pl-Chinatown": (["F01", "B01"], 30),
    "Metro Center":         (["C01", "A01"], 25),
}


def load_inv():
    with INV.open() as f:
        return list(csv.DictReader(f))


def load_station_codes():
    with STATIONS.open() as f:
        return [r["StationCode"] for r in csv.DictReader(f)]


def scan_outages():
    """Return (units_by_prefix, mislabel_rows).

    units_by_prefix[station_code_from_unitname] = set(UnitName).
    mislabel_rows = list of (StationCode, UnitName) where prefix != StationCode.
    """
    units = defaultdict(set)
    mislabel = []
    with OUTAGES.open() as f:
        for r in csv.DictReader(f):
            u = r["UnitName"] or ""
            m = UNIT_PAT.match(u)
            if not m:
                continue
            stn_from_unit = m.group(1)
            units[stn_from_unit].add(u)
            if stn_from_unit != r["StationCode"]:
                mislabel.append((r["StationCode"], u))
    return units, mislabel


def main():
    inv = load_inv()
    stations = load_station_codes()
    units, mislabel = scan_outages()

    errors = []
    warnings = []
    notes = []

    # Check 1: coverage
    inv_codes = {r["StationCode"] for r in inv}
    missing = set(stations) - inv_codes
    extra = inv_codes - set(stations)
    if missing:
        errors.append(f"Stations missing from inventory: {sorted(missing)}")
    if extra:
        errors.append(f"Inventory rows for unknown stations: {sorted(extra)}")

    # Check 2: count >= 0 for filled rows
    pending = []
    for r in inv:
        c = r["escalator_count"]
        if c == "":
            pending.append(r["StationCode"])
            continue
        if int(c) < 0:
            errors.append(f"{r['StationCode']}: negative count {c}")

    # Check 3: lower bound vs outages (using UnitName-derived station)
    lb_failures = []
    for r in inv:
        if r["escalator_count"] == "":
            continue
        code = r["StationCode"]
        observed = len(units.get(code, set()))
        count = int(r["escalator_count"])
        if observed > count:
            lb_failures.append((code, observed, count))
    if lb_failures:
        errors.append("Lower-bound violations (observed unique units > inferred count): "
                      + str(lb_failures))

    # Check 4: spot-check known whole-station totals
    counts_by_code = {r["StationCode"]: r["escalator_count"] for r in inv}
    spot = []
    for name, (codes, expected) in KNOWN_WHOLE_STATION.items():
        actual = 0
        for c in codes:
            v = counts_by_code.get(c, "")
            if v == "":
                actual = None
                break
            actual += int(v)
        spot.append((name, codes, expected, actual))
        if actual != expected:
            errors.append(f"Spot-check FAIL: {name} ({'+'.join(codes)}) "
                          f"= {actual}, expected {expected}")

    # Check 5: mislabeled rows (StationCode != UnitName prefix)
    if mislabel:
        # collapse to (rows-affected, unique pairs)
        pair_counts = defaultdict(int)
        for sc, u in mislabel:
            pair_counts[(sc, u)] += 1
        warnings.append(
            f"WMATA source-data mislabels (StationCode disagrees with UnitName prefix): "
            f"{len(mislabel)} outage rows across {len(pair_counts)} (StationCode, UnitName) pairs."
        )

    # Summary stats
    filled = [int(r["escalator_count"]) for r in inv if r["escalator_count"] != ""]
    total = sum(filled)
    notes.append(f"- stations total: {len(inv)}")
    notes.append(f"- stations with count: {len(filled)}")
    notes.append(f"- stations pending: {len(pending)} → {pending}")
    notes.append(f"- sum of known counts: **{total}**")
    notes.append(f"- WMATA system-wide claimed: **647**")
    notes.append(f"- residual gap (accounted for by pending stations): {647 - total}")

    # Write report
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w") as f:
        f.write("# Escalator inventory — validation\n\n")
        f.write("Phase 3 deliverable. Re-run via `python3 scripts/validate_inventory.py`.\n\n")
        f.write("## Summary\n\n")
        f.write("\n".join(notes) + "\n\n")
        f.write("## Spot-check vs published WMATA counts\n\n")
        f.write("| Whole station | Codes | Computed | WMATA stated | OK |\n")
        f.write("|---|---|---|---|---|\n")
        for name, codes, expected, actual in spot:
            ok = "✓" if actual == expected else "✗"
            f.write(f"| {name} | {'+'.join(codes)} | {actual} | {expected} | {ok} |\n")
        f.write("\n## Errors\n\n")
        if errors:
            for e in errors:
                f.write(f"- ❌ {e}\n")
        else:
            f.write("None.\n")
        f.write("\n## Warnings\n\n")
        if warnings:
            for w in warnings:
                f.write(f"- ⚠ {w}\n")
            if mislabel:
                f.write("\n### Mislabeled outage rows\n\n")
                f.write("Outages where the `StationCode` column disagrees with the station prefix "
                        "embedded in `UnitName`. The escalator is physically at the *UnitName-prefix* "
                        "station; the `StationCode` column is wrong in the source data.\n\n")
                pair_counts = defaultdict(int)
                for sc, u in mislabel:
                    pair_counts[(sc, u)] += 1
                f.write("| StationCode (logged) | UnitName | UnitName-prefix (true station) | rows |\n")
                f.write("|---|---|---|---|\n")
                for (sc, u), n in sorted(pair_counts.items()):
                    m = UNIT_PAT.match(u)
                    true_stn = m.group(1) if m else "?"
                    f.write(f"| {sc} | {u} | {true_stn} | {n} |\n")
        else:
            f.write("None.\n")
        f.write("\n## Pending stations (no count yet)\n\n")
        if pending:
            for code in pending:
                row = next(r for r in inv if r["StationCode"] == code)
                f.write(f"- **{code} {row['StationName']}** — {row['notes']}\n")
        else:
            f.write("None.\n")

    print(f"wrote {REPORT}")
    print(f"errors: {len(errors)}, warnings: {len(warnings)}, pending: {len(pending)}")
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  ❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
