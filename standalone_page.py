#!/usr/bin/env python3
"""
独立车型展示页 — 基于 Canonical Schema，不依赖现有 Flask 系统。
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canonical_schema import CANONICAL_SCHEMA, dim_labels, field_labels

# 旧系统字段名 → 新 canonical key 映射（用于迁移现有数据）
LEGACY_TO_CANONICAL = {
    # size
    "长(mm)": "length_mm", "宽(mm)": "width_mm", "高(mm)": "height_mm",
    "轴距(mm)": "wheelbase_mm", "轮胎规格": "tire_spec", "风阻系数Cd": "drag_coefficient",
    # ev
    "能源形式": "energy_type", "电池容量(kWh)": "battery_capacity_kwh",
    "CLTC纯电续航(km)": "cltc_range_km", "WLTC纯电续航(km)": "wltc_range_km",
    "综合续航(km)": "combined_range_km", "最大功率(kW)": "max_power_kw",
    "最大扭矩(Nm)": "max_torque_nm", "零百加速(s)": "accel_0_100_s",
    "平台架构": "platform", "驱动形式": "drive_type", "电池体系": "battery_type",
    "动力系统": "platform",
    # chassis
    "前悬架": "front_suspension", "后悬架": "rear_suspension",
    "空气悬架": "air_suspension", "CDC": "cdc_damper",
    "主动悬架/主动稳定杆": "active_stabilizer", "后轮转向角度()": "rear_wheel_steer_deg",
    "后轮转向": "rear_wheel_steer_deg", "制动": "brake_system",
    "转弯半径": "turning_radius_m", "涉水深度(mm)": "wading_depth_mm",
    "底盘材质": "chassis_material", "特殊通过能力": "ground_clearance_mm",
    "拖挂资质": None,
    # ad
    "智驾系统/芯片": "ad_chip", "激光雷达数量/位置": "lidar",
    "毫米波雷达数量/位置": "radar_mmwave", "超声波雷达数量/位置": "radar_ultrasonic",
    "摄像头数量/位置": "cameras", "智能驾驶能力": "ad_capability",
    "主动安全能力": "active_safety",
    # cockpit
    "座舱系统/芯片": "cockpit_chip", "前排屏": "center_screen",
    "HUD": "hud", "后排控制屏": "rear_control_screen",
    "后排娱乐屏": "rear_screen", "音响系统": "audio_system",
    "扬声器数量": "speaker_count", "功放功率(W)": "audio_power_w",
    "杜比认证": "dolby_cert", "头枕音响": "headrest_speaker",
    "音响技术": None, "音响材质": None, "车外麦克风/扬声器": None,
    "流媒体后视镜": None,
    # seat
    "座椅布局": "seat_layout", "一排座椅": "row1_seat_function",
    "二排座椅": "row2_seat_function", "三排座椅": "row3_seat_function",
    "一排其它配置": None, "二排其它配置": "row2_table",
    "三排其它配置": None, "二排中岛": "row2_console",
    "座椅卖点": "seat_highlight", "方向盘": "steering_wheel",
    "遮阳帘/玻璃": "sunshade", "阅读灯/氛围灯": "ambient_light",
    # comfort
    "一排空间": "row1_space", "二排空间": "row2_space",
    "三排空间": "row3_space", "后备箱空间": "trunk_volume_l",
    "前备箱容积(L)": "frunk_volume_l", "乘坐空间(mm)": None,
    "NVH": "nvh", "空调": "ac_system", "冰箱": "fridge",
    "健康座舱": "healthy_cabin", "车内面积(m)": None,
    "前备箱开关方式": None,
    # light
    "头灯": "headlight", "尾灯": "taillight",
    "ADB/DLP大灯": "matrix_light", "车门": "door_type",
    "电吸/防夹": "soft_close", "电动开关": "soft_close",
    "迎宾光毯": "welcome_light", "电动踏板": "side_step",
    # design_ext
    "外观特征": "exterior_feature", "车漆颜色": "paint_colors",
    "内饰颜色": "interior_colors", "内饰材质": "interior_material",
    "轮毂/轮胎": "wheels",
    # safety
    "车身结构": "body_structure", "安全气囊数量": "airbag_count",
    "重点气囊": "airbag_detail", "安全带": "seatbelt",
    "主动安全": "aeb", "主动安全增强": "aeb",
    "AI防护系统": "aeb", "车门解锁冗余": "door_unlock_redundancy",
    "关键材料/工艺": "key_material",
}


def migrate_to_canonical(legacy_data: dict) -> dict:
    """将旧系统 PROFILE_DATA 的一项转换为 Canonical Schema。"""
    versions = []
    for v in legacy_data.get("versions", []):
        versions.append({
            "id": v.get("id", "")[:8],
            "name": v.get("version", ""),
            "price": v.get("price", 0),
            "energy_type": v.get("energy", "") or "纯电",
            "drive_type": v.get("drive", ""),
            "seats": v.get("seats", ""),
            "battery": v.get("battery", ""),
        })

    dims = {}
    for legacy_dk, by_version in legacy_data.get("dims", {}).items():
        canonical_dk = legacy_dk  # 大部分key相同
        # 特殊映射
        if legacy_dk == "ev":
            canonical_dk = "powertrain"
        elif legacy_dk == "design_ext":
            canonical_dk = "exterior"
        elif legacy_dk == "nvh":
            canonical_dk = "comfort"
        elif legacy_dk == "space":
            canonical_dk = "comfort"

        for vid, fields in by_version.items():
            short_vid = vid[:8]
            for fn, fv in fields.items():
                ck = LEGACY_TO_CANONICAL.get(fn)
                if ck is None:
                    continue
                dims.setdefault(canonical_dk, {}).setdefault(short_vid, {})[ck] = str(fv)

    basic = {
        "brand": legacy_data.get("brand", ""),
        "series_name": legacy_data.get("model_name", legacy_data.get("name", "")),
        "generation": legacy_data.get("generation", ""),
        "model_type": legacy_data.get("model_type", ""),
        "status": legacy_data.get("status", ""),
        "price_range": legacy_data.get("price_range", ""),
    }

    return {"basic": basic, "versions": versions, "dims": dims}


def build_standalone_html(canonical_data: dict, model_name: str) -> str:
    """生成独立 HTML 页面。"""
    basic = canonical_data.get("basic", {})
    versions = canonical_data.get("versions", [])
    dims = canonical_data.get("dims", {})
    dim_titles = dim_labels()
    f_labels = field_labels()

    # 构建维度表格
    dim_html = ""
    for d in CANONICAL_SCHEMA:
        dk = d.key
        if dk == "basic":
            continue
        bv = dims.get(dk, {})
        if not bv:
            continue
        title = d.title
        field_keys = [f.key for f in d.fields]

        # 收集visible fields
        visible = []
        for fk in field_keys:
            has_val = any(fk in (bv.get(vid, {}) or {}) for vid in bv)
            if has_val:
                visible.append(fk)

        if not visible:
            continue

        rows = []
        for fk in visible:
            label = f_labels.get(fk, fk)
            cells = []
            for v in versions:
                vid = v["id"]
                val = (bv.get(vid, {}) or {}).get(fk, "")
                cells.append(val)
            # 所有相同则不需要diff
            all_same = len(set(cells)) <= 1
            rows.append({"label": label, "cells": cells, "all_same": all_same})

        # 渲染表格
        dim_html += f'<div class="dim-section" id="dim-{dk}">'
        dim_html += f'<div class="dim-title">{title}</div>'
        dim_html += '<div class="dim-table-wrap"><table>'
        dim_html += '<thead><tr><th class="field-col">参数</th>'
        for v in versions:
            dim_html += f'<th>{v["name"][:20]}</th>'
        dim_html += '</tr></thead><tbody>'
        for row in rows:
            dim_html += f'<tr><td class="field-col">{row["label"]}</td>'
            for i, cell in enumerate(row["cells"]):
                cls = "" if row["all_same"] else ("diff-val" if i > 0 and cell != row["cells"][0] else "")
                dim_html += f'<td class="{cls}">{cell or "-"}</td>'
            dim_html += '</tr>'
        dim_html += '</tbody></table></div></div>'

    # 版本表
    ver_html = '<div class="section"><div class="section-title">版本配置</div>'
    ver_html += '<div class="dim-table-wrap"><table>'
    ver_html += '<thead><tr><th>版本</th><th>指导价</th><th>能源</th><th>驱动</th><th>座位</th></tr></thead><tbody>'
    for v in versions:
        ver_html += f'<tr><td>{v["name"][:25]}</td><td class="price-col">{v["price"]} 万</td><td>{v["energy_type"]}</td><td>{v["drive_type"]}</td><td>{v["seats"]}</td></tr>'
    ver_html += '</tbody></table></div></div>'

    # 侧栏
    sidebar = '<div class="sidebar">'
    for d in CANONICAL_SCHEMA:
        if d.key == "basic":
            continue
        if d.key in dims and dims[d.key]:
            sidebar += f'<a class="side-pill" href="#dim-{d.key}">{d.title}</a>'
    sidebar += '</div>'

    # 组装完整 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{model_name} — 配置档案</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:#F0F0F0;color:#333;min-height:100vh}}
.page{{max-width:1200px;margin:0 auto;padding:24px}}
.header{{background:#FFF;border-radius:12px;padding:28px 32px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.header h1{{font-size:24px;font-weight:700}}
.header .meta{{margin-top:8px;font-size:14px;color:#888;display:flex;gap:16px}}
.layout{{display:flex;gap:20px;align-items:flex-start}}
.sidebar{{position:sticky;top:20px;width:110px;flex-shrink:0;display:flex;flex-direction:column;gap:4px}}
.side-pill{{display:block;padding:6px 8px;font-size:11px;color:#555;background:#FFF;border-radius:6px;cursor:pointer;text-decoration:none;border:1px solid #EEE;text-align:center;transition:all .15s}}
.side-pill:hover{{border-color:#1A3C6E;color:#1A3C6E;background:#F0F4FF}}
.content{{flex:1;min-width:0}}
.section-title{{font-size:16px;font-weight:600;margin-bottom:12px}}
.dim-section{{margin-bottom:28px}}
.dim-title{{font-size:14px;font-weight:600;color:#1A3C6E;margin-bottom:8px;padding-left:6px;border-left:3px solid #1A3C6E}}
.dim-table-wrap{{background:#FFF;border-radius:10px;overflow-x:auto;box-shadow:0 1px 4px rgba(0,0,0,.06);padding:4px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#F7F7F7;color:#555;font-weight:600;padding:8px 12px;text-align:left;border-bottom:2px solid #E8E8E8;white-space:nowrap}}
td{{padding:6px 12px;border-bottom:1px solid #F4F4F4;color:#444;word-break:break-all}}
tr:last-child td{{border-bottom:none}}
.field-col{{color:#888;font-size:11px;white-space:nowrap;min-width:100px}}
.price-col{{font-weight:600;color:#D32F2F}}
.diff-val{{background:#FFF9C4}}
footer{{text-align:center;padding:20px;font-size:11px;color:#CCC}}
</style>
</head>
<body>
<div class="page">
<div class="header">
  <h1>{basic.get('series_name', model_name)}</h1>
  <div class="meta">
    <span>品牌: {basic.get('brand','')}</span>
    <span>级别: {basic.get('model_type','')}</span>
    <span>状态: {basic.get('status','')}</span>
    <span>价格: {basic.get('price_range','')}</span>
    <span>{len(versions)} 个版本</span>
  </div>
</div>
<div class="layout">
  {sidebar}
  <div class="content">
    {ver_html}
    {dim_html}
  </div>
</div>
</div>
<footer>Canonical Schema v1 · 数据来源: autohome + 飞书校核</footer>
<script>
document.querySelectorAll('.side-pill').forEach(function(a){{
  a.addEventListener('click',function(e){{
    e.preventDefault();
    var el=document.getElementById(this.getAttribute('href').slice(1));
    if(el) el.scrollIntoView({{behavior:'smooth',block:'start'}});
  }});
}});
</script>
</body>
</html>"""
    return html


def main():
    if len(sys.argv) < 2:
        print("用法: python3 standalone_page.py <es9_raw.json | autohome_url>")
        sys.exit(1)

    arg = sys.argv[1]
    if arg.endswith(".json"):
        with open(arg) as f:
            legacy = json.load(f)
        canonical = migrate_to_canonical(legacy)
    elif arg.startswith("http"):
        from normalizer import extract_from_url
        canonical = extract_from_url(arg)
    else:
        print("参数须为 JSON 文件或 URL")
        sys.exit(1)

    if "_error" in canonical:
        print(f"错误: {canonical['_error']}")
        sys.exit(1)

    model_name = canonical["basic"].get("series_name", "未知车型")
    html = build_standalone_html(canonical, model_name)
    out = Path.home() / "Desktop" / f"{model_name}_canonical.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ 输出: {out}")


if __name__ == "__main__":
    main()
