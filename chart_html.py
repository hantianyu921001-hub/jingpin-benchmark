#!/usr/bin/env python3
"""谱系图 HTML 版 — 白底简洁风格，品牌筛选/显隐，悬停查看详情。"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go

from spectrum_data import (
    build_chart_rows,
    chart_positions,
    length_ticks,
    load_live_dataset,
    offset_transformed_length,
    split_length_groups,
    transform_length,
)

LAUNCHED = {"正式上市", "已上市"}
EXCLUDED_STATUS = {"版本取消", "退市", "停售"}
POWER_LABEL = {
    "bev": "纯电",
    "erev": "增程",
    "phev": "插混",
    "erev_bev": "增程/纯电",
    "unknown": "能源待补",
}
PAIR_NAMES = [
    ("乐道L90", "乐道L80"),
    ("小米YU7", "小米SU7"),
    ("尚界Z7", "尚界Z7T"),
    ("蔚来ET5", "蔚来ET5T"),
]
BRAND_COLORS = {
    "理想": "#1B5E20",
    "问界": "#E53935",
    "智界": "#FF6D00",
    "尚界": "#795548",
    "小米": "#FF6900",
    "蔚来": "#0066FF",
    "乐道": "#00BFFF",
    "小鹏": "#00BE7A",
    "零跑": "#7B1FA2",
    "极氪": "#C6A83B",
    "智己": "#00838F",
    "腾势": "#B71C1C",
    "方程豹": "#455A64",
    "岚图": "#3949AB",
    "华境": "#00897B",
    "魏牌": "#6D4C41",
    "上汽大众": "#1565C0",
}
FALLBACK_COLORS = [
    "#546E7A", "#AD1457", "#2E7D32", "#6A1B9A", "#EF6C00", "#00695C",
]
EREV_OFFSET = -3
JITTER = 0.18
MIN_GAP = 1.2
HEADER_GAP = 1.0
HEADER_NAME_GAP = 0.9
HEADER_COLLISION_SHIFT = 5
HEADER_AXIS_EPSILON = 0.5


def normalized_name(value):
    return re.sub(r"\s+", "", str(value or ""))


def generation_year(value):
    match = re.search(r"(\d{4})", str(value or ""))
    return int(match.group(1)) if match else 0


def clean_version(version, model_name):
    value = str(version or "").replace("_", " ")
    compact_model_name = normalized_name(model_name)
    if normalized_name(value).startswith(compact_model_name):
        value = re.sub(r"^\s*" + r"\s*".join(map(re.escape, model_name)), "", value)
        if normalized_name(value).startswith(compact_model_name):
            value = normalized_name(value)[len(compact_model_name):]
    for word in [
        "纯电动", "增程式", "纯电版", "增程版", "插混版",
        "纯电型", "增程型", "纯电", "增程", "插混",
    ]:
        value = value.replace(word, "")
    value = re.sub(r"^[程电混]\s*", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if value in ("版", "版本"):
        return ""
    return value[:20]


def model_labels(rows):
    return {row["model_key"]: row["model_name"] for row in rows}


def header_key_for_name(name, power, x):
    return (normalized_name(name), power, round(x, 3))


def spine_label_top(rows):
    _, label_ys = compute_label_positions(rows)
    if label_ys:
        return label_ys[-1]
    return max(r["price"] for r in rows)


def compute_label_positions(rows):
    price_count = {}
    dots = []
    for row in sorted(rows, key=lambda r: r["price"]):
        key = round(row["price"], 2)
        count = price_count.get(key, 0)
        dots.append((row["price"] + count * JITTER, row.get("version", "")))
        price_count[key] = count + 1
    dots.sort(key=lambda d: d[0])
    label_ys = []
    for adjusted_price, _ in dots:
        y = adjusted_price
        if label_ys:
            y = max(y, label_ys[-1] + MIN_GAP)
        label_ys.append(y)
    return dots, label_ys


def compute_label_positions_ext(rows):
    """Same as compute_label_positions but preserves full row for hover."""
    price_count = {}
    dots = []
    for row in sorted(rows, key=lambda r: r["price"]):
        key = round(row["price"], 2)
        count = price_count.get(key, 0)
        dots.append((row["price"] + count * JITTER, row))
        price_count[key] = count + 1
    dots.sort(key=lambda d: d[0])
    label_ys = []
    for adjusted_price, _ in dots:
        y = adjusted_price
        if label_ys:
            y = max(y, label_ys[-1] + MIN_GAP)
        label_ys.append(y)
    return dots, label_ys


def model_axis_positions(model_data, model_x, pairs):
    paired_axes = {}
    for main_key, secondary_key in pairs:
        if main_key not in model_data or secondary_key not in model_data:
            continue
        main_x = model_x[main_key]
        paired_axes[main_key] = {list(model_data[main_key])[0]: main_x}
        paired_axes[secondary_key] = {
            list(model_data[secondary_key])[0]:
            offset_transformed_length(main_x, EREV_OFFSET),
        }
    axes_by_model = {}
    for model_key, powers in model_data.items():
        if model_key in paired_axes:
            axes_by_model[model_key] = paired_axes[model_key]
            continue
        x_base = model_x[model_key]
        has_bev = "bev" in powers
        other_power = next(
            (key for key in ("erev", "phev", "erev_bev", "unknown") if key in powers),
            None,
        )
        if has_bev and other_power:
            axes_by_model[model_key] = {
                "bev": x_base,
                other_power: offset_transformed_length(x_base, EREV_OFFSET),
            }
        else:
            power = "bev" if has_bev else other_power
            axes_by_model[model_key] = {power: x_base}
    return axes_by_model


def spine_points_by_axis(model_data, display_names, axes_by_model):
    points_by_axis = defaultdict(list)
    for model_key, axes in axes_by_model.items():
        for power, x in axes.items():
            key = header_key_for_name(display_names[model_key], power, x)
            points_by_axis[key].extend(model_data[model_key][power])
    return points_by_axis


def header_tops_by_axis(points_by_axis):
    return {key: spine_label_top(points) for key, points in points_by_axis.items()}


def shifted_header_x(x, own_header_keys, axis_x_by_key):
    for key, axis_x in axis_x_by_key.items():
        if key not in own_header_keys and abs(x - axis_x) <= HEADER_AXIS_EPSILON:
            return x + HEADER_COLLISION_SHIFT
    return x


def pair_candidate(keys, rows_by_key, model_x, reference_key=None):
    reference_length = None
    if reference_key:
        reference_length = model_x[reference_key]

    def sort_key(model_key):
        row = rows_by_key[model_key]
        distance = 0 if reference_length is None else abs(model_x[model_key] - reference_length)
        return (-generation_year(row.get("generation")), distance, model_key)

    return sorted(keys, key=sort_key)[0]


def model_name_pairs(model_names, rows, model_x):
    keys_by_name = defaultdict(list)
    for model_key, name in model_names.items():
        keys_by_name[normalized_name(name)].append(model_key)
    rows_by_key = {row["model_key"]: row for row in rows}
    pairs = []
    for main_name, secondary_name in PAIR_NAMES:
        mains = keys_by_name[normalized_name(main_name)]
        secondaries = keys_by_name[normalized_name(secondary_name)]
        if mains and secondaries:
            secondary = pair_candidate(secondaries, rows_by_key, model_x)
            main = pair_candidate(mains, rows_by_key, model_x, secondary)
            pairs.append((main, secondary))
    return pairs


def complete_brand_colors(brands):
    colors = dict(BRAND_COLORS)
    fallback_index = 0
    for brand in sorted(brands):
        if brand not in colors:
            colors[brand] = FALLBACK_COLORS[fallback_index % len(FALLBACK_COLORS)]
            fallback_index += 1
    return colors


# ── CSS for chart tab (used by both standalone page and combined site) ──
CHART_CSS = """
  .brand-bar{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
  .brand-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 10px 3px 7px;border-radius:12px;border:1px solid #DDD;background:#FFF;cursor:pointer;font-size:11px;color:#555;transition:all .15s ease;user-select:none;white-space:nowrap}
  .brand-pill:hover{border-color:#BBB;background:#FAFAFA}
  .brand-pill .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
  .brand-pill .count{font-size:10px;color:#AAA;margin-left:1px}
  .brand-pill.hidden{opacity:.55;border-color:#E8E8E8;background:#F8F8F8}
  .chart-card{background:#FFF;border:1px solid #E0E0E0;border-radius:4px;overflow:hidden}
"""


def build_chart_fragment(rows, row_warnings=None):
    """Given pre-filtered chart rows, build chart data for embedding.

    Returns dict: chart_div, brand_data_json, brand_ann_json, stats
    """
    if row_warnings:
        for msg in row_warnings:
            print(f"warning: {msg}", file=sys.stderr)
    if not rows:
        raise RuntimeError("没有可绘制的车型记录，请先检查 00/10/11 表数据")

    names = model_labels(rows)
    model_data = defaultdict(lambda: defaultdict(list))
    model_brand = {}
    model_launched = defaultdict(bool)
    model_presale = defaultdict(bool)
    for row in rows:
        mk = row["model_key"]
        model_data[mk][row["power"]].append(row)
        model_brand[mk] = row["brand"]
        if row["status"] in LAUNCHED:
            model_launched[mk] = True
        else:
            model_presale[mk] = True

    def display_name(model_key):
        name = names[model_key]
        if model_presale[model_key] and not model_launched[model_key]:
            return f"{name}（预售）"
        return name

    model_x = chart_positions(rows)
    pairs = model_name_pairs(names, rows, model_x)
    display_names = {mk: display_name(mk) for mk in model_data}
    axes_by_model = model_axis_positions(model_data, model_x, pairs)
    points_by_axis = spine_points_by_axis(model_data, display_names, axes_by_model)
    header_tops = header_tops_by_axis(points_by_axis)
    axis_x_by_key = {key: key[2] for key in points_by_axis}
    colors = complete_brand_colors(model_brand.values())

    brand_models = defaultdict(list)
    for mk in model_data:
        brand_models[model_brand[mk]].append(display_names[mk])

    # ── Build Plotly figure ──
    fig = go.Figure()
    rendered_spines = set()
    rendered_headers = set()
    annotation_brands = []

    def add_spine_traces(model_key, power, x, label_side, brand):
        key = header_key_for_name(display_names[model_key], power, x)
        if key in rendered_spines:
            return header_tops[key]
        color = colors.get(brand, "#888888")
        points = points_by_axis[key]
        prices = [r["price"] for r in points]
        fig.add_trace(go.Scatter(
            x=[x, x], y=[min(prices), max(prices)],
            mode="lines", line=dict(color=color, width=2.5),
            legendgroup=brand, showlegend=False, hoverinfo="skip",
        ))
        dots, label_ys = compute_label_positions_ext(points)
        connector_x, connector_y = [], []
        marker_x, marker_y, marker_custom = [], [], []
        for (jittered_price, row), label_y in zip(dots, label_ys):
            marker_x.append(x)
            marker_y.append(jittered_price)
            marker_custom.append([
                names[model_key], row.get("version", ""), row.get("price", 0),
                row.get("length", 0), row.get("seats", ""), row.get("drive", ""), row.get("battery", ""),
            ])
            if abs(label_y - jittered_price) > 0.15:
                connector_x += [x, x, None]
                connector_y += [jittered_price, label_y, None]
        if connector_x:
            fig.add_trace(go.Scatter(
                x=connector_x, y=connector_y, mode="lines",
                line=dict(color=color, width=0.5),
                legendgroup=brand, showlegend=False, hoverinfo="skip",
            ))
        fig.add_trace(go.Scatter(
            x=marker_x, y=marker_y, mode="markers",
            marker=dict(color=color, size=7.5, line=dict(color="white", width=1.2)),
            legendgroup=brand, showlegend=False, customdata=marker_custom,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br><br>"
                "<span style='color:#666'>价格</span>  ¥%{customdata[2]:.2f}万<br>"
                "<span style='color:#666'>车长</span>  %{customdata[3]}mm<br>"
                "<span style='color:#666'>座位</span>  %{customdata[4]}座<br>"
                "<span style='color:#666'>驱动</span>  %{customdata[5]}<br>"
                "<span style='color:#666'>电量</span>  %{customdata[6]}kWh<extra></extra>"
            ),
        ))
        rendered_spines.add(key)
        return label_ys[-1] if label_ys else max(prices)

    def header_y(header_keys, fallback_top):
        return max(header_tops.get(key, fallback_top) for key in header_keys) + HEADER_GAP

    def _add_label(x, y, text, brand, size=9.5, side="center", angle=0):
        clr = colors.get(brand, "#888888")
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False, xref="x", yref="y",
            font=dict(color=clr, size=size), textangle=angle, xanchor=side, yanchor="bottom",
        )
        annotation_brands.append(brand)

    def render_model(model_key, secondary_key=None):
        if secondary_key:
            main_power, main_x = next(iter(axes_by_model[model_key].items()))
            sec_power, sec_x = next(iter(axes_by_model[secondary_key].items()))
            main_top = add_spine_traces(model_key, main_power, main_x, +1, model_brand[model_key])
            sec_top = add_spine_traces(secondary_key, sec_power, sec_x, -1, model_brand[secondary_key])
            hk = [
                header_key_for_name(display_names[model_key], main_power, main_x),
                header_key_for_name(display_names[secondary_key], sec_power, sec_x),
            ]
            ey = header_y(hk, max(main_top, sec_top))
            mhx = shifted_header_x(main_x, {hk[0]}, axis_x_by_key)
            shx = shifted_header_x(sec_x, {hk[1]}, axis_x_by_key)
            _add_label(mhx, ey + HEADER_NAME_GAP, f"<b>{display_names[model_key]}</b>", model_brand[model_key], side="left", angle=38)
            _add_label(shx, ey + HEADER_NAME_GAP, f"<b>{display_names[secondary_key]}</b>", model_brand[secondary_key], side="right", angle=38)
            rendered_headers.update(hk)
            return
        powers = model_data[model_key]
        has_bev = "bev" in powers
        other_power = next((k for k in ("erev", "phev", "erev_bev", "unknown") if k in powers), None)
        if has_bev and other_power:
            bev_x = axes_by_model[model_key]["bev"]
            other_x = axes_by_model[model_key][other_power]
            bev_top = add_spine_traces(model_key, "bev", bev_x, +1, model_brand[model_key])
            other_top = add_spine_traces(model_key, other_power, other_x, -1, model_brand[model_key])
            name_x = (bev_x + other_x) / 2
            hk = [
                header_key_for_name(display_names[model_key], "bev", bev_x),
                header_key_for_name(display_names[model_key], other_power, other_x),
            ]
            ey = header_y(hk, max(bev_top, other_top))
            bhx = shifted_header_x(bev_x, {hk[0]}, axis_x_by_key)
            ohx = shifted_header_x(other_x, {hk[1]}, axis_x_by_key)
            _add_label(bhx, ey, POWER_LABEL["bev"], model_brand[model_key], size=7, side="left")
            _add_label(ohx, ey, POWER_LABEL[other_power], model_brand[model_key], size=7, side="right")
            mnx = shifted_header_x(name_x, set(hk), axis_x_by_key)
            _add_label(mnx, ey + HEADER_NAME_GAP, f"<b>{display_names[model_key]}</b>", model_brand[model_key], side="center", angle=38)
            rendered_headers.update(hk)
        else:
            power = "bev" if has_bev else other_power
            x_pos = axes_by_model[model_key][power]
            top = add_spine_traces(model_key, power, x_pos, +1, model_brand[model_key])
            hk = [header_key_for_name(display_names[model_key], power, x_pos)]
            ey = header_y(hk, top)
            if hk[0] not in rendered_headers:
                mnx = shifted_header_x(x_pos, set(hk), axis_x_by_key)
                _add_label(mnx, ey + HEADER_NAME_GAP, f"<b>{display_names[model_key]}</b>", model_brand[model_key], side="center", angle=38)
                rendered_headers.update(hk)

    rendered = set()
    for main, secondary in pairs:
        if main in model_data and secondary in model_data:
            render_model(main, secondary)
            rendered |= {main, secondary}
    for mk in model_data:
        if mk not in rendered:
            render_model(mk)

    x_values = list(model_x.values())
    real_ticks = length_ticks(min(r["length"] for r in rows), max(r["length"] for r in rows))
    y_max = max(r["price"] for r in rows) + 12

    fig.update_layout(
        template="none", plot_bgcolor="#F9F9F9", paper_bgcolor="#F9F9F9",
        autosize=True, height=800,
        title=dict(text="竞品品牌型谱对比（含预售车系）",
                   font=dict(size=15, color="#333333", family="system-ui,-apple-system,sans-serif"), x=0.5),
        xaxis=dict(
            title=dict(text="车身长度 (mm，4900mm以上区间放大显示)",
                       font=dict(size=11, color="#444444", family="system-ui,-apple-system,sans-serif")),
            range=[4700, max(x_values) + 80], tickmode="array",
            tickvals=[transform_length(l) for l in real_ticks],
            ticktext=[str(l) for l in real_ticks],
            showgrid=False, zeroline=False,
            tickfont=dict(size=9.5, color="#666666", family="system-ui,-apple-system,sans-serif"),
        ),
        yaxis=dict(
            title=dict(text="厂商指导价 (万元)",
                       font=dict(size=11, color="#444444", family="system-ui,-apple-system,sans-serif")),
            range=[10, y_max], dtick=5, showgrid=True, gridcolor="#E2E2E2",
            gridwidth=0.7, zeroline=False,
            tickfont=dict(size=9.5, color="#666666", family="system-ui,-apple-system,sans-serif"),
        ),
        legend=dict(title=dict(text="品牌", font=dict(size=10, color="#444444")), font=dict(size=9.5),
                    bgcolor="rgba(255,255,255,0.93)", bordercolor="#CCCCCC", borderwidth=1, itemsizing="constant"),
        hovermode="closest",
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#CCCCCC",
                        font=dict(size=11, color="#333333", family="system-ui,-apple-system,sans-serif")),
        margin=dict(l=60, r=30, t=60, b=60),
    )
    fig.add_annotation(
        x=1, y=-0.06, text="数据来源：竞品Benchmark 飞书多维表格 00/10/11",
        showarrow=False, xref="paper", yref="paper",
        font=dict(size=7.5, color="#AAAAAA", family="system-ui,-apple-system,sans-serif"),
        xanchor="right", yanchor="top",
    )

    brand_js_map = {
        brand: [i for i, b in enumerate(annotation_brands) if b == brand]
        for brand in set(annotation_brands)
    }
    brand_json_str = json.dumps(brand_js_map, ensure_ascii=False)

    BRAND_ORDER = [
        "理想", "问界", "智界", "尚界", "启境", "华境",
        "小米", "蔚来", "乐道", "小鹏", "极氪", "智己",
        "岚图", "零跑", "腾势", "方程豹", "比亚迪", "魏牌", "上汽大众",
    ]
    def brand_sort_key(b):
        try:
            return BRAND_ORDER.index(b)
        except ValueError:
            return len(BRAND_ORDER)

    all_brands_sorted = sorted(brand_models.keys(), key=brand_sort_key)
    ALWAYS_VISIBLE = {"理想", "问界", "蔚来"}
    brand_data_items = [
        {"name": brand, "count": len(brand_models[brand]),
         "color": colors.get(brand, "#888888"), "hiddenByDefault": brand not in ALWAYS_VISIBLE}
        for brand in all_brands_sorted
    ]
    brand_data_json = json.dumps(brand_data_items, ensure_ascii=False)

    fig.update_annotations(captureevents=True)
    chart_div = fig.to_html(include_plotlyjs=False, div_id="car-chart", full_html=False)

    return {
        "chart_div": chart_div,
        "brand_data_json": brand_data_json,
        "brand_ann_json": brand_json_str,
        "stats": {"models": len(model_data), "versions": len(rows), "brands": len(all_brands_sorted)},
    }




def _brand_bar_js(bar_id, chart_id, brand_data_json, brand_ann_json):
    """Generate brand filter pill JS for a given bar/chart id pair."""
    return f"""var BRAND_DATA = {brand_data_json};
var brandAnn = {brand_ann_json};
var bar = document.getElementById('{bar_id}');
var pillStates = {{}};
BRAND_DATA.forEach(function(b) {{
  var pill = document.createElement('button');
  pill.className = 'brand-pill' + (b.hiddenByDefault ? ' hidden' : '');
  pill.dataset.brand = b.name;
  pill.innerHTML = '<span class="dot" style="background:' + b.color + '"></span> ' +
    b.name + ' <span class="count">' + b.count + '</span>';
  pill.addEventListener('click', function() {{ toggleBrand(b.name); }});
  bar.appendChild(pill);
  pillStates[b.name] = !b.hiddenByDefault;
}});
var plotDiv = document.getElementById('{chart_id}');
function applyBrandState(brand, visible) {{
  var indices = [];
  for (var i = 0; i < plotDiv.data.length; i++) {{
    if (plotDiv.data[i].legendgroup === brand) indices.push(i);
  }}
  if (indices.length > 0) Plotly.restyle(plotDiv, 'opacity', visible ? null : 0.15, indices);
  var annIds = brandAnn[brand] || [];
  if (annIds.length > 0) {{
    var update = {{}};
    annIds.forEach(function(idx) {{ update['annotations[' + idx + '].visible'] = visible; }});
    Plotly.relayout(plotDiv, update);
  }}
}}
var inited = false;
function afterRender() {{
  if (!inited && plotDiv && plotDiv.data && plotDiv.data.length) {{
    inited = true;
    BRAND_DATA.forEach(function(b) {{ if (b.hiddenByDefault) applyBrandState(b.name, false); }});
  }}
}}
afterRender();
plotDiv.on('plotly_afterplot', afterRender);
function toggleBrand(brand) {{
  if (!plotDiv || !plotDiv.data) return;
  var newVisible = !pillStates[brand];
  applyBrandState(brand, newVisible);
  pillStates[brand] = newVisible;
  document.querySelectorAll('.brand-pill').forEach(function(p) {{
    if (p.dataset.brand === brand) p.classList.toggle('hidden', !newVisible);
  }});
}}"""


def render_html(out_path, exclude_sort_codes=None):
    if exclude_sort_codes is None:
        exclude_sort_codes = ["0901"]

    dataset = load_live_dataset()
    rows, row_warnings = build_chart_rows(
        dataset["models"], dataset["prices"], dataset["designs"]
    )
    rows = split_length_groups(rows)
    rows = [row for row in rows if row["status"] not in EXCLUDED_STATUS]
    if exclude_sort_codes:
        rows = [row for row in rows if row["sort_code"] not in exclude_sort_codes]
    if not rows:
        raise RuntimeError("没有可绘制的车型记录，请先检查 00/10/11 表数据")

    fragment = build_chart_fragment(rows, row_warnings)
    chart_div = fragment["chart_div"]
    brand_data_json = fragment["brand_data_json"]
    brand_ann_json = fragment["brand_ann_json"]
    stats = fragment["stats"]

    page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>竞品品牌型谱对比</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #F0F0F0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", system-ui, sans-serif; color: #333; min-height: 100vh; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 20px 20px 40px; }}
  .header {{ display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }}
  .header h1 {{ font-size: 15px; font-weight: bold; color: #333; }}
  .header .stats {{ font-size: 12px; color: #888; }}
  .header .stats strong {{ color: #555; }}
  .footer {{ text-align: center; padding: 14px 0 4px; font-size: 11px; color: #AAA; }}
  {CHART_CSS}
</style>
</head>
<body>
<div class="container">
  <header class="header">
    <h1>竞品品牌型谱对比（含预售车系）</h1>
    <div class="stats"><strong>{stats["models"]}</strong> 车型 · <strong>{stats["versions"]}</strong> 版本 · <strong>{stats["brands"]}</strong> 品牌</div>
  </header>
  <div class="brand-bar" id="brand-bar"></div>
  <div class="chart-card">{chart_div}</div>
  <div class="footer">点击品牌标签筛选 · 悬停查看版本详情</div>
</div>
<script>
{_brand_bar_js("brand-bar", "car-chart", brand_data_json, brand_ann_json)}
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page_html, encoding="utf-8")
    print(f"Saved: {out_path}")
    print(f"Rendered: {stats['models']} models, {stats['versions']} versions, {stats['brands']} brands")

def main():
    parser = argparse.ArgumentParser(description="生成竞品品牌车型谱系图（HTML 版）")
    parser.add_argument("--out", default="~/Desktop/car_model_chart.html",
                        help="输出 HTML 路径，默认写入桌面")
    parser.add_argument("--exclude", nargs="*", default=["0901"],
                        help="排除的车型排序码，默认排除 0901（尊界S800）")
    parser.add_argument("--no-exclude", action="store_true",
                        help="不排除任何车型")
    args = parser.parse_args()
    exclude = None if args.no_exclude else args.exclude
    render_html(Path(args.out).expanduser(), exclude_sort_codes=exclude)


if __name__ == "__main__":
    main()
