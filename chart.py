#!/usr/bin/env python3
import argparse
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from spectrum_data import (
    build_chart_rows,
    chart_positions,
    length_ticks,
    load_live_dataset,
    offset_transformed_length,
    split_length_groups,
    transform_length,
)


for font_path in [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
]:
    try:
        plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()
        break
    except Exception:
        pass
plt.rcParams["axes.unicode_minus"] = False

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
LABEL_PT = 5
LABEL_FS = 5.6
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
    labels = {}
    for row in rows:
        labels[row["model_key"]] = row["model_name"]
    return labels


def compute_label_positions(points):
    price_count = {}
    dots = []
    for price, _, version in sorted(points, key=lambda point: point[0]):
        key = round(price, 2)
        count = price_count.get(key, 0)
        dots.append((price + count * JITTER, version))
        price_count[key] = count + 1
    dots.sort(key=lambda point: point[0])
    label_ys = []
    for adjusted_price, _ in dots:
        y = adjusted_price
        if label_ys:
            y = max(y, label_ys[-1] + MIN_GAP)
        label_ys.append(y)
    return dots, label_ys


def spine_label_top(points):
    label_ys = compute_label_positions(points)[1]
    if label_ys:
        return label_ys[-1]
    return max(price for price, _, _ in points)


def header_key_for_name(name, power, x):
    return (normalized_name(name), power, round(x, 3))


def model_axis_positions(model_data, model_x, pairs):
    paired_axes = {}
    for main_key, secondary_key in pairs:
        if main_key not in model_data or secondary_key not in model_data:
            continue
        main_x = model_x[main_key]
        paired_axes[main_key] = {
            list(model_data[main_key])[0]: main_x,
        }
        paired_axes[secondary_key] = {
            list(model_data[secondary_key])[0]: offset_transformed_length(main_x, EREV_OFFSET),
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
    tops = {}
    for key, points in points_by_axis.items():
        tops[key] = spine_label_top(points)
    return tops


def shifted_header_x(x, own_header_keys, axis_x_by_key):
    for key, axis_x in axis_x_by_key.items():
        if key not in own_header_keys and abs(x - axis_x) <= HEADER_AXIS_EPSILON:
            return x + HEADER_COLLISION_SHIFT
    return x


def draw_spine(ax, x, points, color, label_side, model_name):
    prices = [price for price, _, _ in points]
    ax.plot(
        [x, x], [min(prices), max(prices)],
        color=color, linewidth=2.5, solid_capstyle="round", zorder=4, alpha=0.85,
    )
    dots, label_ys = compute_label_positions(points)
    alignment = "left" if label_side > 0 else "right"
    for (adjusted_price, version), label_y in zip(dots, label_ys):
        ax.scatter(
            x, adjusted_price, color=color, s=52, zorder=6,
            edgecolors="white", linewidths=1.2, marker="o",
        )
        if abs(label_y - adjusted_price) > 0.15:
            ax.plot(
                [x, x], [adjusted_price, label_y],
                color=color, alpha=0.2, linewidth=0.5, zorder=3,
            )
        version = clean_version(version, model_name)
        label = f"{version}\n{adjusted_price:.2f}万" if version else f"{adjusted_price:.2f}万"
        ax.annotate(
            label, xy=(x, label_y), xytext=(label_side * LABEL_PT, 0),
            textcoords="offset points", ha=alignment, va="center",
            fontsize=LABEL_FS, color=color, zorder=8, multialignment=alignment,
        )
    return label_ys[-1] if label_ys else max(prices)


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


def render(out_path):
    dataset = load_live_dataset()
    rows, row_warnings = build_chart_rows(
        dataset["models"], dataset["prices"], dataset["designs"]
    )
    rows = split_length_groups(rows)
    rows = [row for row in rows if row["status"] not in EXCLUDED_STATUS]
    rows = [row for row in rows if row["sort_code"] != "0901"]  # 排除尊界S800
    for message in row_warnings:
        print(f"warning: {message}", file=sys.stderr)
    if not rows:
        raise RuntimeError("没有可绘制的车型记录，请先检查 00/10/11 表数据")

    names = model_labels(rows)
    model_data = defaultdict(lambda: defaultdict(list))
    model_brand = {}
    model_launched = defaultdict(bool)
    model_presale = defaultdict(bool)
    for row in rows:
        model_key = row["model_key"]
        model_data[model_key][row["power"]].append(
            (row["price"], row["length"], row["version"])
        )
        model_brand[model_key] = row["brand"]
        if row["status"] in LAUNCHED:
            model_launched[model_key] = True
        else:
            model_presale[model_key] = True

    def display_name(model_key):
        name = names[model_key]
        if model_presale[model_key] and not model_launched[model_key]:
            return f"{name}（预售）"
        return name

    model_x = chart_positions(rows)
    pairs = model_name_pairs(names, rows, model_x)
    display_names = {model_key: display_name(model_key) for model_key in model_data}
    axes_by_model = model_axis_positions(model_data, model_x, pairs)
    points_by_axis = spine_points_by_axis(model_data, display_names, axes_by_model)
    header_tops = header_tops_by_axis(points_by_axis)
    axis_x_by_key = {key: key[2] for key in points_by_axis}

    colors = complete_brand_colors(model_brand.values())
    fig, ax = plt.subplots(figsize=(28, 16))
    fig.patch.set_facecolor("#F9F9F9")
    ax.set_facecolor("#F9F9F9")
    ax.grid(axis="y", color="#E2E2E2", linewidth=0.7, alpha=0.9, zorder=1)
    rendered_headers = set()
    rendered_spines = set()

    def header_key(model_key, power, x):
        return header_key_for_name(display_names[model_key], power, x)

    def header_y(header_keys, fallback_top):
        return max(header_tops.get(key, fallback_top) for key in header_keys) + HEADER_GAP

    def draw_axis_spine(model_key, power, x, label_side):
        key = header_key(model_key, power, x)
        if key in rendered_spines:
            return header_tops[key]
        top = draw_spine(
            ax, x, points_by_axis[key], colors.get(model_brand.get(model_key), "#888888"),
            label_side, names[model_key],
        )
        rendered_spines.add(key)
        return top

    def render_model(model_key, secondary_key=None):
        color = colors.get(model_brand.get(model_key), "#888888")
        fontweight = "heavy" if model_brand.get(model_key) == "理想" else "bold"
        if secondary_key:
            main_power, main_x = next(iter(axes_by_model[model_key].items()))
            secondary_power, secondary_x = next(iter(axes_by_model[secondary_key].items()))
            main_top = draw_axis_spine(model_key, main_power, main_x, +1)
            secondary_top = draw_axis_spine(secondary_key, secondary_power, secondary_x, -1)
            header_keys = [
                header_key(model_key, main_power, main_x),
                header_key(secondary_key, secondary_power, secondary_x),
            ]
            energy_y = header_y(header_keys, max(main_top, secondary_top))
            main_header_key = header_keys[0]
            secondary_header_key = header_keys[1]
            main_header_x = shifted_header_x(main_x, {main_header_key}, axis_x_by_key)
            secondary_header_x = shifted_header_x(
                secondary_x, {secondary_header_key}, axis_x_by_key
            )
            ax.text(
                main_header_x, energy_y + HEADER_NAME_GAP, display_names[model_key],
                fontsize=9.5, ha="left", va="bottom", color=color,
                fontweight=fontweight, rotation=38, zorder=9,
            )
            ax.text(
                secondary_header_x, energy_y + HEADER_NAME_GAP, display_names[secondary_key],
                fontsize=9.5, ha="right", va="bottom", color=color,
                fontweight=fontweight, rotation=38, zorder=9,
            )
            rendered_headers.update(header_keys)
            return

        x_base = model_x[model_key]
        powers = model_data[model_key]
        has_bev = "bev" in powers
        other_power = next(
            (key for key in ("erev", "phev", "erev_bev", "unknown") if key in powers),
            None,
        )
        if has_bev and other_power:
            bev_x = axes_by_model[model_key]["bev"]
            other_x = axes_by_model[model_key][other_power]
            bev_top = draw_axis_spine(model_key, "bev", bev_x, +1)
            other_top = draw_axis_spine(model_key, other_power, other_x, -1)
            name_x = (bev_x + other_x) / 2
        else:
            power = "bev" if has_bev else other_power
            x_base = axes_by_model[model_key][power]
            top = draw_axis_spine(model_key, power, x_base, +1)
            name_x = x_base
        if has_bev and other_power:
            header_keys = [
                header_key(model_key, "bev", bev_x),
                header_key(model_key, other_power, other_x),
            ]
            energy_y = header_y(header_keys, max(bev_top, other_top))
        else:
            header_keys = [header_key(model_key, power, x_base)]
            energy_y = header_y(header_keys, top)
        if any(key not in rendered_headers for key in header_keys):
            if has_bev and other_power:
                bev_header_key = header_key(model_key, "bev", bev_x)
                other_header_key = header_key(model_key, other_power, other_x)
                bev_header_x = shifted_header_x(bev_x, {bev_header_key}, axis_x_by_key)
                other_header_x = shifted_header_x(other_x, {other_header_key}, axis_x_by_key)
                ax.text(
                    bev_header_x, energy_y, POWER_LABEL["bev"],
                    fontsize=7, ha="left", va="bottom", color=color, alpha=0.85, zorder=9,
                )
                ax.text(
                    other_header_x, energy_y, POWER_LABEL[other_power],
                    fontsize=7, ha="right", va="bottom", color=color, alpha=0.85, zorder=9,
                )
                model_name_x = shifted_header_x(name_x, set(header_keys), axis_x_by_key)
            else:
                model_header_key = header_key(model_key, power, x_base)
                model_name_x = shifted_header_x(x_base, {model_header_key}, axis_x_by_key)
                ax.text(
                    model_name_x, energy_y, POWER_LABEL.get(power, "能源待补"),
                    fontsize=7, ha="center", va="bottom", color=color, alpha=0.85, zorder=9,
                )
            ax.text(
                model_name_x, energy_y + HEADER_NAME_GAP, display_names[model_key],
                fontsize=9.5, ha="center", va="bottom", color=color,
                fontweight=fontweight, rotation=38, zorder=9,
            )
            rendered_headers.update(header_keys)

    rendered = set()
    for main, secondary in pairs:
        if main in model_data and secondary in model_data:
            render_model(main, secondary)
            rendered |= {main, secondary}
    for model_key in model_data:
        if model_key not in rendered:
            render_model(model_key)

    used_brands = [brand for brand in colors if brand in set(model_brand.values())]
    patches = [mpatches.Patch(color=colors[brand], label=brand) for brand in used_brands]
    ax.legend(
        handles=patches, loc="upper left", frameon=True, fontsize=9.5,
        framealpha=0.93, edgecolor="#CCCCCC", ncol=2,
    )
    ax.set_xlabel("车身长度 (mm，4900mm以上区间放大显示)", fontsize=11, labelpad=10, color="#444444")
    ax.set_ylabel("厂商指导价 (万元)", fontsize=11, labelpad=10, color="#444444")
    ax.set_title("竞品品牌型谱对比（含预售车系）", fontsize=15, fontweight="bold", pad=18)
    x_values = list(model_x.values())
    real_ticks = length_ticks(
        min(row["length"] for row in rows),
        max(row["length"] for row in rows),
    )
    ax.set_xlim(4700, max(x_values) + 80)
    ax.set_ylim(10, max(row["price"] for row in rows) + 12)
    ax.set_xticks([transform_length(length) for length in real_ticks])
    ax.set_xticklabels([str(length) for length in real_ticks])
    ax.yaxis.set_major_locator(plt.MultipleLocator(5))
    ax.tick_params(colors="#666666", labelsize=9.5)
    for spine in ax.spines.values():
        spine.set_color("#DDDDDD")
    ax.text(
        0.99, 0.01, "数据来源：竞品Benchmark 飞书多维表格 00/10/11",
        transform=ax.transAxes, fontsize=7.5, ha="right", va="bottom", color="#AAAAAA",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout(pad=2)
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="#F9F9F9")
    print(f"Saved: {out_path}")
    print(f"Rendered: {len(model_data)} models, {len(rows)} versions")
    print(f"Skipped: {len(row_warnings)} versions")


def main():
    parser = argparse.ArgumentParser(description="生成竞品品牌车型谱系图")
    parser.add_argument(
        "--out",
        default="~/Desktop/car_model_chart7.png",
        help="输出 PNG 路径，默认写入桌面",
    )
    args = parser.parse_args()
    render(Path(args.out).expanduser())


if __name__ == "__main__":
    main()
