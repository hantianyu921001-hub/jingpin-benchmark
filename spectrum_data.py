#!/usr/bin/env python3
"""Read normalized benchmark tables and build chart-ready vehicle rows."""
import json
import math
import subprocess
from statistics import mean


BASE_TOKEN = "E571b0YbQa2MxysVn4RctXcDn7d"
TABLES = {
    "models": "tbl92hQB5ngDEvRH",
    "prices": "tblWDFfm3M3uX9qx",
    "designs": "tblROhrR1M84SZrp",
}
LENGTH_EXPAND_FROM = 4900
LENGTH_EXPAND_FACTOR = 2


def payload_to_records(payload):
    """Convert lark-cli's positional rows into dictionaries keyed by field name."""
    data = payload["data"]
    fields = data["fields"]
    record_ids = data.get("record_id_list", [])
    records = []
    for index, row in enumerate(data.get("data", [])):
        record = dict(zip(fields, row))
        record["_record_id"] = record_ids[index] if index < len(record_ids) else None
        records.append(record)
    return records


def fetch_table_records(table_id):
    """Fetch all table rows sequentially because +record-list has a 200-row limit."""
    records = []
    offset = 0
    while True:
        cmd = [
            "lark-cli", "base", "+record-list",
            "--base-token", BASE_TOKEN,
            "--table-id", table_id,
            "--as", "user",
            "--offset", str(offset),
            "--limit", "200",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        payload = json.loads(result.stdout)
        page = payload_to_records(payload)
        records.extend(page)
        if not payload["data"].get("has_more"):
            return records
        offset += len(page)


def load_live_dataset():
    """Read 00, 10, and 11 in order. Do not parallelize Base list operations."""
    return {
        name: fetch_table_records(table_id)
        for name, table_id in TABLES.items()
    }


def link_ids(value):
    return {
        item["id"]
        for item in (value or [])
        if isinstance(item, dict) and item.get("id")
    }


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def display_brand(value):
    return str(first_value(value)).split("-")[-1]


def power_kind(value):
    energy = str(first_value(value))
    if "纯电" in energy and ("增程" in energy or "插混" in energy):
        return "erev_bev"
    if "纯电" in energy:
        return "bev"
    if "插混" in energy:
        return "phev"
    if "增程" in energy:
        return "erev"
    return "unknown"


def version_label(version_id, model_id, energy=None, version_level=None):
    label = str(version_id or "").strip()
    prefix = f"{model_id}_"
    if label.startswith(prefix):
        label = label[len(prefix):]
    if label:
        tokens = [
            str(item).strip()
            for item in (energy if isinstance(energy, list) else [energy])
            if str(item or "").strip()
        ]
        for token in tokens:
            label = label.replace(f"_{token}_", "_")
            if label.startswith(f"{token}_"):
                label = label[len(token) + 1:]
            if label.endswith(f"_{token}"):
                label = label[:-(len(token) + 1)]
            label = label.replace(token, "")
        label = "_".join(part for part in label.split("_") if part)
        if label:
            return label.replace("_", " ")

    standard_label = str(first_value(version_level)).strip()
    if standard_label:
        return standard_label
    return label.replace("_", " ")


def _valid_lengths(designs):
    return {
        int(design["长(mm)"])
        for design in designs
        if isinstance(design.get("长(mm)"), (int, float))
    }


def split_length_groups(rows):
    """Split chart groups only when one unified model has multiple body lengths."""
    lengths_by_model = {}
    for row in rows:
        lengths_by_model.setdefault(row["model_key"], set()).add(row["length"])

    grouped_rows = []
    for row in rows:
        grouped_row = dict(row)
        if len(lengths_by_model[row["model_key"]]) > 1:
            grouped_row["model_key"] = f"{row['model_key']}::{row['length']}"
        grouped_rows.append(grouped_row)
    return grouped_rows


def transform_length(length):
    """Expand the dense large-vehicle range while preserving real length order."""
    if length <= LENGTH_EXPAND_FROM:
        return length
    return LENGTH_EXPAND_FROM + (length - LENGTH_EXPAND_FROM) * LENGTH_EXPAND_FACTOR


def inverse_transform_length(position):
    """Convert a chart x position back to the real body length scale."""
    if position <= LENGTH_EXPAND_FROM:
        return position
    return LENGTH_EXPAND_FROM + (position - LENGTH_EXPAND_FROM) / LENGTH_EXPAND_FACTOR


def offset_transformed_length(position, real_delta):
    """Move a transformed x position by real millimeters, then remap to chart x."""
    return transform_length(inverse_transform_length(position) + real_delta)


def length_ticks(min_length, max_length):
    """Build real-length labels with a left boundary and denser large-car ticks."""
    ticks = []
    left_boundary = math.floor(min_length / 50) * 50
    if left_boundary < LENGTH_EXPAND_FROM:
        ticks.append(left_boundary)

    coarse_start = math.ceil(min_length / 100) * 100
    coarse_end = min(math.floor(max_length / 100) * 100, LENGTH_EXPAND_FROM)
    ticks.extend(range(coarse_start, coarse_end + 1, 100))

    dense_start = max(LENGTH_EXPAND_FROM + 50, math.ceil(min_length / 50) * 50)
    dense_end = math.floor(max_length / 50) * 50
    ticks.extend(range(dense_start, dense_end + 1, 50))
    return list(dict.fromkeys(ticks))


def chart_positions(rows):
    """Map each chart group to its transformed real body length without shifting."""
    lengths_by_model = {}
    for row in rows:
        lengths_by_model.setdefault(row["model_key"], []).append(row["length"])
    return {
        model_key: transform_length(int(mean(lengths)))
        for model_key, lengths in lengths_by_model.items()
    }


def build_chart_rows(models, prices, designs):
    """Join 00/10/11 records and return rows with price, energy, and length."""
    warnings = []
    models_by_id = {
        model["_record_id"]: model
        for model in models
        if model.get("_record_id") and model.get("车型统一ID")
    }
    designs_by_model = {}
    for design in designs:
        for model_record_id in link_ids(design.get("关联车型")):
            designs_by_model.setdefault(model_record_id, []).append(design)

    rows = []
    for price in prices:
        version_id = price.get("_record_id")
        model_record_ids = [
            record_id
            for record_id in link_ids(price.get("关联车型"))
            if record_id in models_by_id
        ]
        if not model_record_ids:
            warnings.append(f"跳过版本 {price.get('版本统一ID') or version_id}: 缺少关联车型")
            continue

        model_record_id = model_record_ids[0]
        model = models_by_id[model_record_id]
        model_designs = designs_by_model.get(model_record_id, [])
        specific_designs = [
            design
            for design in model_designs
            if version_id in link_ids(design.get("适用版本"))
        ]
        lengths = _valid_lengths(specific_designs)
        if not lengths:
            lengths = _valid_lengths(model_designs)
        if len(lengths) != 1:
            warnings.append(
                f"跳过版本 {price.get('版本统一ID') or version_id}: "
                f"无法唯一确定车长 {sorted(lengths)}"
            )
            continue

        price_value = price.get("价格(万元)")
        if not isinstance(price_value, (int, float)):
            warnings.append(f"跳过版本 {price.get('版本统一ID') or version_id}: 缺少价格")
            continue

        model_id = model["车型统一ID"]
        rows.append({
            "model_key": model_id,
            "model_name": str(model.get("车系") or model_id),
            "generation": str(model.get("年款/代际") or ""),
            "brand": display_brand(model.get("品牌")),
            "status": str(first_value(model.get("上市状态"))),
            "sort_code": str(model.get("车型排序码") or ""),
            "version": version_label(
                price.get("版本统一ID"),
                model_id,
                price.get("能源"),
                price.get("版本等级"),
            ),
            "power": power_kind(price.get("能源")),
            "price": float(price_value),
            "length": lengths.pop(),
            "seats": first_value(price.get("座位数")),
            "drive": first_value(price.get("驱动")),
            "battery": first_value(price.get("电池电量")),
        })
    return rows, warnings
