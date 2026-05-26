# Escalator inventory — source survey

Phase 1 deliverable. Date: 2026-05-25.

## Goal

Per-station authoritative count of escalators. WMATA system-wide total: **647** (per wmata.com/service/elevators-escalators/). No public per-station inventory dataset surfaced.

## Sources probed

| # | Source | Per-station? | Verdict |
|---|---|---|---|
| 1 | WMATA Incidents API (`Incidents.svc/json/ElevatorIncidents`) | implicit | **Outages only, but `UnitName` encodes ordinal** — usable via inference. See below. |
| 2 | WMATA `Rail.svc/json/jStations` | no | Station metadata; no escalator counts. |
| 3 | WMATA Service Status page (`/service/elevators-escalators/Elevator-Escalator-Service-Status.cfm`) | no | JS-rendered shell (300 B raw HTML). Out-of-service listing only. |
| 4 | WMATA rider-guide station pages | dynamic | Widgets rendered client-side; not scrapeable without headless browser. |
| 5 | WMATA Open Data Hub | no | No inventory dataset. Contact `ResearchCouncil@wmata.com` for non-listed data. |
| 6 | Data.gov WMATA tag | no | Ridership and survey datasets only. |
| 7 | WMATA Vertical Transportation / Scorecard | no | System-wide monthly availability, not per-station. |
| 8 | Wikipedia (`List_of_Washington_Metro_stations`, station infoboxes) | partial | Occasional mentions (e.g., Wheaton's long escalator). No systematic counts. |
| 9 | OpenStreetMap (Overpass `highway=escalator` inside station polygons) | yes | Not yet tested. Reasonable fallback for stations with zero outage history. |
| 10 | Press releases ("L'Enfant Plaza 31", "Gallery Pl 30", "Metro Center 25", "Bethesda 5") | partial | A few high-traffic stations only. |

## Inference from `UnitName`

`data/escalator_outages.csv` has 14 512 rows. Every `UnitName` matches the pattern:

```
^([A-Z]\d{2})([A-Z])(\d+)$
^ station ^zone   ^ordinal
```

— e.g. `A03N03` = station A03, zone N, escalator #03.

**Key insight**: `max(ordinal)` per `(station, zone)` is WMATA's own count of escalators in that zone, even if some ordinals have never broken in our window. Cross-checking against the three counts WMATA publishes:

| Whole station | Codes | Σ max-ord | WMATA stated |
|---|---|---|---|
| L'Enfant Plaza | D03 + F03 | 18 + 13 = **31** | 31 ✓ |
| Gallery Pl–Chinatown | F01 + B01 | 16 + 14 = **30** | 30 ✓ |
| Metro Center | C01 + A01 | 11 + 14 = **25** | 25 ✓ |

Three-for-three. Method validated.

## Coverage

- **94 / 102 stations**: outage history exists → `escalator_count = Σ max(ordinal per zone)`.
- **8 / 102 stations**: zero outage history → require fallback.
- Inferred system total from the 94 covered stations: **623**. WMATA says 647. Gap = 24, accounted for by the 8 below.

### Zero-history stations (need fallback)

| Code | Name | Lines | Reason |
|---|---|---|---|
| B09 | Forest Glen | RD | **Elevator-only station, zero escalators.** Deepest in system. |
| N07 | Reston Town Center | SV | Silver Line Phase 2 (Nov 2022). |
| N08 | Herndon | SV | Silver Line Phase 2 (Nov 2022). |
| N09 | Innovation Center | SV | Silver Line Phase 2 (Nov 2022). |
| N10 | Washington Dulles Intl Airport | SV | Silver Line Phase 2 (Nov 2022). |
| N11 | Loudoun Gateway | SV | Silver Line Phase 2 (Nov 2022). |
| N12 | Ashburn | SV | Silver Line Phase 2 (Nov 2022). |
| C11 | Potomac Yard | BL,YL | Opened May 2023. |

For the 7 non-zero ones: backfill via OSM Overpass or manual count from opening-day press releases / station diagrams.

## Conclusion

**Primary source = `UnitName` ordinal inference from `data/escalator_outages.csv`.**
**Fallback for 8 stations = manual + OSM cross-check.**

Pros:
- Costs zero new API surface; just compute over data we already have.
- Self-correcting: monotonically improves as more outages occur over time.
- Validated against WMATA's three published counts.

Cons / caveats:
- Lower bound only if the highest-ordinal unit at a station has never broken in our window. 32 / 94 stations have intermediate-ordinal gaps; some may also have top-ordinal gaps not detectable from data alone.
- Stations with very short outage history (new openings, very reliable) need manual fallback.
- Does not detect renumberings or unit retirements (none observed; unlikely).

## Next phase

Phase 2: write `scripts/build_inventory.py` to emit `data/escalator_inventory.csv` from this method, with manual entries for the 8 zero-history stations.
