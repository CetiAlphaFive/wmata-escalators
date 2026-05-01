#!/usr/bin/env bash
set -euo pipefail

: "${WMATA_API_KEY:?WMATA_API_KEY must be set}"

OUT="${OUT:-data/escalator_outages.csv}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEADER='snapshot_ts,StationCode,StationName,UnitName,LocationDescription,SymptomDescription,DateOutOfServ,EstimatedReturnToService'

if [[ ! -f "$OUT" ]]; then
  mkdir -p "$(dirname "$OUT")"
  echo "$HEADER" > "$OUT"
fi

resp="$(curl -sS --fail-with-body \
  -H "api_key: ${WMATA_API_KEY}" \
  "https://api.wmata.com/Incidents.svc/json/ElevatorIncidents")"

rows="$(printf '%s' "$resp" | jq -r --arg ts "$TS" '
  (.ElevatorIncidents // [])
  | map(select(.UnitType == "ESCALATOR"))
  | .[]
  | [ $ts,
      (.StationCode // ""),
      (.StationName // ""),
      (.UnitName // ""),
      (.LocationDescription // ""),
      (.SymptomDescription // ""),
      (.DateOutOfServ // ""),
      (.EstimatedReturnToService // "")
    ]
  | @csv
')"

if [[ -n "$rows" ]]; then
  printf '%s\n' "$rows" >> "$OUT"
  count="$(printf '%s\n' "$rows" | wc -l)"
else
  count=0
fi

echo "snapshot=$TS escalator_outages=$count appended_to=$OUT"
