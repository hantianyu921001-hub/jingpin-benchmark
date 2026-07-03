#!/usr/bin/env bash
set -uo pipefail

BASE_TOKEN="${BASE_TOKEN:-E571b0YbQa2MxysVn4RctXcDn7d}"
VEHICLE_RECORD_ID="${1:-}"
MAX_ROWS="${MAX_ROWS:-3}"

if [[ -z "$VEHICLE_RECORD_ID" ]]; then
  echo "Usage: $0 <vehicle_record_id>" >&2
  exit 2
fi

if ! [[ "$MAX_ROWS" =~ ^[0-9]+$ ]]; then
  echo "MAX_ROWS must be a non-negative integer" >&2
  exit 2
fi

tables=(
  "20_设计:tblUAEHLyihXdwXn"
  "21_尺寸:tblROhrR1M84SZrp"
  "22_空间:tbll00EXYEc4S0hf"
  "23_座椅&内饰:tblWUYBYTprgY55P"
  "24_NVH&空调:tblyyiC7y6r21Ti5"
  "25_灯光&车门:tblFxRXeclZexjq6"
  "30_智能驾驶AD:tblFLQjKa91NiFKz"
  "40_智能座舱SS:tblZv13LhbwJ4l6e"
  "50_底盘:tblVhYbXA8WQDSkS"
  "60_三电:tbllgpvch11HVnqq"
  "70_安全:tblTjuDT2NHD3xGR"
)

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
status=0

for entry in "${tables[@]}"; do
  name="${entry%%:*}"
  table_id="${entry#*:}"
  payload="$workdir/$table_id.json"

  if ! lark-cli base +record-list \
    --base-token "$BASE_TOKEN" \
    --table-id "$table_id" \
    --limit 200 >"$payload"; then
    echo "ERROR\t$name\tunable to read table" >&2
    status=2
    continue
  fi

  if ! node - "$payload" "$VEHICLE_RECORD_ID" "$MAX_ROWS" "$name" <<'NODE'
const fs = require('fs');
const [path, vehicleId, maxRowsText, tableName] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(path, 'utf8'));
const data = payload.data;

if (!data || data.has_more) {
  console.error(`ERROR\t${tableName}\tpagination required before row-count verification`);
  process.exit(2);
}

const fieldIndex = data.fields.indexOf('关联车型');
if (fieldIndex < 0) {
  console.error(`ERROR\t${tableName}\tmissing 关联车型 field`);
  process.exit(2);
}

const count = data.data.filter((cells) =>
  Array.isArray(cells[fieldIndex]) && cells[fieldIndex].some((link) => link.id === vehicleId)
).length;
console.log(`${tableName}\t${count}`);

if (count > Number(maxRowsText)) {
  console.error(`ROW_COUNT_GUARD\t${tableName}\t${count} rows exceed ${maxRowsText}; review parameter differences before completion`);
  process.exit(1);
}
NODE
  then
    status=1
  fi
done

exit "$status"
