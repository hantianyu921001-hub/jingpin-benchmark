#!/usr/bin/env bash
set -euo pipefail

BASE_TOKEN="${BASE_TOKEN:-E571b0YbQa2MxysVn4RctXcDn7d}"
VEHICLE_RECORD_ID="${1:-}"

if [[ -z "$VEHICLE_RECORD_ID" ]]; then
  echo "Usage: $0 <vehicle_record_id>" >&2
  exit 2
fi

tables=(
  "00_车型:tbl92hQB5ngDEvRH"
  "10_版本价格:tblWDFfm3M3uX9qx"
  "11_设计(尺寸灯光车门):tblUAEHLyihXdwXn"
  "12_空间(座椅NVH空调):tblyyiC7y6r21Ti5"
  "13_智能驾驶:tblFLQjKa91NiFKz"
  "14_智能座舱:tblZv13LhbwJ4l6e"
  "15_底盘:tblVhYbXA8WQDSkS"
  "16_三电:tbllgpvch11HVnqq"
  "17_安全:tblTjuDT2NHD3xGR"
)

for entry in "${tables[@]}"; do
  name="${entry%%:*}"
  table_id="${entry#*:}"
  count="$(
    lark-cli base +record-list \
      --base-token "$BASE_TOKEN" \
      --table-id "$table_id" \
      --limit 500 |
      rg -c "$VEHICLE_RECORD_ID" || true
  )"
  printf "%s\t%s\n" "$name" "$count"
done
