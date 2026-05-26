# Escalator inventory — validation

Phase 3 deliverable. Re-run via `python3 scripts/validate_inventory.py`.

## Summary

- stations total: 102
- stations with count: 95
- stations pending: 7 → ['N12', 'N08', 'N09', 'N11', 'C11', 'N07', 'N10']
- sum of known counts: **623**
- WMATA system-wide claimed: **647**
- residual gap (accounted for by pending stations): 24

## Spot-check vs published WMATA counts

| Whole station | Codes | Computed | WMATA stated | OK |
|---|---|---|---|---|
| L'Enfant Plaza | D03+F03 | 31 | 31 | ✓ |
| Gallery Pl-Chinatown | F01+B01 | 30 | 30 | ✓ |
| Metro Center | C01+A01 | 25 | 25 | ✓ |

## Errors

None.

## Warnings

- ⚠ WMATA source-data mislabels (StationCode disagrees with UnitName prefix): 76 outage rows across 2 (StationCode, UnitName) pairs.

### Mislabeled outage rows

Outages where the `StationCode` column disagrees with the station prefix embedded in `UnitName`. The escalator is physically at the *UnitName-prefix* station; the `StationCode` column is wrong in the source data.

| StationCode (logged) | UnitName | UnitName-prefix (true station) | rows |
|---|---|---|---|
| B06 | E06X05 | E06 | 13 |
| B06 | E06X06 | E06 | 63 |

## Pending stations (no count yet)

- **N12 Ashburn** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
- **N08 Herndon** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
- **N09 Innovation Center** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
- **N11 Loudoun Gateway** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
- **C11 Potomac Yard** — Potomac Yard (opened 2023-05-19). Needs OSM/manual.
- **N07 Reston Town Center** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
- **N10 Washington Dulles International Airport** — Silver Line Phase 2 (opened 2022-11-15). Needs OSM/manual.
