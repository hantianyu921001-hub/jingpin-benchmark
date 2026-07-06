#!/usr/bin/env python3
"""
规范化引擎 — 将各源原始数据转换为 Canonic Schema 统一格式。
"""
import json, re, sys, urllib.request, urllib.parse
from pathlib import Path
from typing import Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from canonical_schema import CANONICAL_SCHEMA, get_dim_by_key, get_field_keys
from source_mappings import AUTOHOME_MAP

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _fetch_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.autohome.com.cn/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── autohome 提取 + 规范化 ────────────────────────────────────────────

AUTOHOME_CAT_TO_DIM = {
    "基本参数": "basic",
    "车身": "size",
    "发动机": "powertrain",
    "变速箱": "powertrain",
    "底盘转向": "chassis",
    "车轮制动": "chassis",
    "被动安全": "safety",
    "主动安全": "safety",
    "驾驶操控": "chassis",
    "驾驶硬件": "ad",
    "驾驶功能": "ad",
    "外观/防盗": "exterior",
    "车外灯光": "light",
    "天窗/玻璃": "light",
    "外后视镜": "light",
    "互联/智能化": "cockpit",
    "方向盘/内后视镜": "seat",
    "车内充电": "cockpit",
    "座椅配置": "seat",
    "音响/车内灯光": "cockpit",
    "空调/冰箱": "comfort",
}

# 合并字段（autohome 多行拼一行）
MERGE_FIELDS = {
    "airbag_detail", "row1_seat_function", "row1_seat_adjust",
    "row2_seat_function", "row2_seat_adjust", "row3_seat_function",
    "headlight", "center_screen", "audio_system", "ad_capability",
}


def _get_param_value(param: dict) -> str:
    """从 autohome paramconflist 项提取值。"""
    if param.get("value") and str(param["value"]).strip():
        return str(param["value"]).strip()
    if param.get("sublist"):
        parts = []
        for sub in param["sublist"]:
            if isinstance(sub, dict):
                v = sub.get("value") or sub.get("subvalue") or sub.get("name") or ""
                if v: parts.append(str(v).strip())
            elif isinstance(sub, str):
                parts.append(sub.strip())
        return " / ".join(parts) if parts else ""
    val = str(param.get("itemname", "")).strip()
    if val and val not in ("●", "○", "—", "-", "无", "暂无", "标配"):
        return val
    return ""


def extract_autohome_canonical(spec_id: str) -> dict:
    """从 autohome API 提取并规范化为 Canonical Schema。"""
    api = f"https://www.autohome.com.cn/web-main/car/param/getParamConf?mode=1&site=2&specid={spec_id}"
    print(f"  → API: {api}", file=sys.stderr)
    data = _fetch_json(api, timeout=20)
    if data.get("returncode") != 0:
        return {"_error": data.get("message", "unknown")}

    result = data["result"]
    bread = result.get("bread", {})
    brand = bread.get("brandname", "")
    series = bread.get("seriesname", "")

    # 解析 titleid → (field_name, category)
    title_info: dict[int, tuple] = {}
    for group in result.get("titlelist", []):
        cat = group.get("itemtype", "")
        for item in group.get("items", []):
            tid = item.get("titleid")
            if tid is not None:
                title_info[tid] = (item.get("itemname", ""), cat)

    # 收集所有版本
    output = {
        "basic": {
            "brand": brand,
            "series_name": series,
            "generation": "",
            "model_type": "",
            "status": "正式上市",
            "price_range": "",
        },
        "versions": [],
        "dims": defaultdict(lambda: defaultdict(dict)),
    }

    prices = []
    for spec in result.get("datalist", []):
        if spec.get("specstatus") == 0:
            continue
        specname = spec.get("specname", "")
        minprice_raw = spec.get("minprice", "0")
        try:
            price = float(minprice_raw.replace("万", "").strip())
        except ValueError:
            price = 0
        prices.append(price)

        vid = f"v{len(output['versions'])+1}"
        output["versions"].append({
            "id": vid,
            "name": specname,
            "price": price,
            "energy_type": "",
            "drive_type": "",
            "seats": "",
            "battery": "",
        })

        # 提取每个参数
        for param in spec.get("paramconflist") or []:
            tid = param.get("titleid")
            if tid not in title_info:
                continue
            fn_ah, cat = title_info[tid]
            val = _get_param_value(param)
            if not val:
                continue

            # 映射
            canonical_key = AUTOHOME_MAP.get(fn_ah)
            if canonical_key is None:
                continue
            if canonical_key == "":
                continue

            dim_key = AUTOHOME_CAT_TO_DIM.get(cat, "other")
            if dim_key == "other":
                continue

            target = output["dims"][dim_key].setdefault(vid, {})
            if canonical_key in MERGE_FIELDS and canonical_key in target:
                if val not in target[canonical_key]:
                    target[canonical_key] = f"{target[canonical_key]}；{val}"
            else:
                target[canonical_key] = val

    # 计算价格区间
    if prices:
        lo, hi = min(prices), max(prices)
        output["basic"]["price_range"] = f"{lo}-{hi}万" if lo != hi else f"{lo}万"

    # 从参数字段提取版本级信息
    basic_tids = {}
    for group in result.get("titlelist", []):
        if group.get("itemtype") == "基本参数":
            for item in group.get("items", []):
                basic_tids[item["titleid"]] = item["itemname"]

    for i, spec in enumerate(result.get("datalist", [])):
        if i >= len(output["versions"]):
            break
        pcl = {p["titleid"]: p for p in (spec.get("paramconflist") or [])}
        for tid, fn_ah in basic_tids.items():
            if tid not in pcl:
                continue
            val = _get_param_value(pcl[tid])
            if fn_ah == "能源类型" and val:
                output["versions"][i]["energy_type"] = val
            elif fn_ah == "驱动方式" and val:
                output["versions"][i]["drive_type"] = val
            elif fn_ah in ("座位数", "座位数(个)") and val:
                s = val.strip()
                if "座" not in s:
                    s = f"{s}座"
                output["versions"][i]["seats"] = s

    # 转为普通 dict
    output["dims"] = {dk: dict(bv) for dk, bv in output["dims"].items()}
    return output


# ── 提取入口 ──────────────────────────────────────────────────────────

def extract_from_url(url: str) -> dict:
    """从 URL 提取数据并规范化为 Canonical Schema。"""
    if "autohome.com.cn" in url:
        m = re.search(r"/spec/(\d+)", url)
        if m:
            return extract_autohome_canonical(m.group(1))
    return {"_error": "unsupported source"}


# ── JSON 输出辅助 ────────────────────────────────────────────────────

def to_display_json(data: dict) -> dict:
    """将 canonical 数据转为前端展示用的 JSON（用 label 而非 key）。"""
    field_labels = {}
    dim_titles = {}
    for d in CANONICAL_SCHEMA:
        dim_titles[d.key] = d.title
        for f in d.fields:
            field_labels[f.key] = f.label

    dims_display = {}
    for dk, bv in data.get("dims", {}).items():
        title = dim_titles.get(dk, dk)
        rows = []
        for vid, fields in bv.items():
            for fk, fv in fields.items():
                label = field_labels.get(fk, fk)
                rows.append({"vid": vid, "field": fk, "label": label, "value": fv})
        dims_display[dk] = {"title": title, "rows": rows}

    return {
        "basic": data.get("basic", {}),
        "versions": data.get("versions", []),
        "dims": dims_display,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 normalizer.py <autohome_url>")
        sys.exit(1)

    result = extract_from_url(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
