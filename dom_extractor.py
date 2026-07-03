#!/usr/bin/env python3
"""
DOM / API 提取引擎 —— 从汽车参数页提取结构化配置数据。

支持多种提取策略（按优先级）：
  1. 汽车之家 API：直接请求 JSON 配置数据（最快、最可靠）
  2. 懂车帝 API：请求懂车帝的参数接口
  3. HTML 表格兜底：用 Playwright 渲染后解析 table/DOM

用法：
    python3 dom_extractor.py <url>               # 提取并输出 JSON
    python3 dom_extractor.py <url> --save         # 提取并保存为本地车型
"""
import json, re, sys, time, urllib.request, urllib.error
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from vehicle_profile import DIMENSION_DEFS

# ── HTTP 工具 ──────────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _fetch_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Referer": "https://www.autohome.com.cn/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ── 汽车之家 API 提取 ─────────────────────────────────────────────────

# autohome 分类 → 我们的 dim_key
AUTOHOME_CAT_TO_DIM: dict[str, str] = {
    "基本参数": "ev",
    "车身": "size",
    "发动机": "ev",
    "变速箱": "ev",
    "底盘转向": "chassis",
    "车轮制动": "chassis",
    "被动安全": "safety",
    "主动安全": "safety",
    "驾驶操控": "chassis",
    "驾驶硬件": "ad",
    "驾驶功能": "ad",
    "外观/防盗": "design_ext",
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


def extract_autohome(spec_id: str) -> dict:
    """通过汽车之家 API 提取配置数据。"""
    api_url = (
        f"https://www.autohome.com.cn/web-main/car/param/getParamConf"
        f"?mode=1&site=2&specid={spec_id}"
    )
    print(f"  → API: {api_url}", file=sys.stderr)
    data = _fetch_json(api_url, timeout=20)

    if data.get("returncode") != 0:
        return {"_error": f"autohome API error: {data.get('message','')}"}

    result = data["result"]

    # 基础信息
    bread = result.get("bread", {})
    brand = bread.get("brandname", "")
    series = bread.get("seriesname", "")

    # 解析参数名 → titleid 映射
    # titlelist: [{itemtype, groupname, items: [{titleid, itemname}]}]
    param_names: dict[int, str] = {}
    param_cats: dict[int, str] = {}
    for group in result.get("titlelist", []):
        cat = group.get("itemtype", "")
        for item in group.get("items", []):
            tid = item.get("titleid")
            name = item.get("itemname", "")
            if tid is not None and name:
                param_names[tid] = name
                param_cats[tid] = cat

    # 提取版本和配置
    versions: list[dict] = []
    dims: dict[str, dict] = {}

    for spec in result.get("datalist", []):
        specname = spec.get("specname", "")
        minprice = spec.get("minprice", "")
        spec_status = spec.get("specstatus", 0)

        # 跳过概念车等无效 spec (specstatus=0=未发布, 只过滤明确不可用的)
        if spec_status == 0:
            continue

        vid = f"v{len(versions)+1}"
        price = 0
        if minprice:
            try:
                price = float(minprice.replace("万", "").strip())
            except ValueError:
                pass

        versions.append({
            "id": vid,
            "version": specname,
            "price": price,
            "energy": "",
            "drive": "",
            "seats": "",
            "battery": "",
            "summary": "",
        })

        # 提取配置值
        for param in spec.get("paramconflist") or []:
            tid = param.get("titleid")
            if tid is None:
                continue

            field_name = param_names.get(tid)
            if not field_name:
                continue

            val = _get_param_value(param)
            if not val:
                continue

            cat = param_cats.get(tid, "")
            dim_key = AUTOHOME_CAT_TO_DIM.get(cat, "other")

            dims.setdefault(dim_key, {}).setdefault(vid, {})[field_name] = val

    # 从基本参数中提取 energy / drive / seats 等版本级信息
    basic_params = next(
        (g for g in result.get("titlelist", []) if g.get("itemtype") == "基本参数"),
        None,
    )
    if basic_params and versions:
        _name_to_titleid = {item["itemname"]: item["titleid"] for item in basic_params.get("items", [])}

        for i, spec in enumerate(result.get("datalist", [])):
            if i >= len(versions):
                break
            pcl = {p["titleid"]: p for p in (spec.get("paramconflist") or [])}

            # 能源类型
            tid = _name_to_titleid.get("能源类型")
            if tid and tid in pcl:
                versions[i]["energy"] = _get_param_value(pcl[tid])

            # 驱动方式
            tid = _name_to_titleid.get("驱动方式")
            if tid and tid in pcl:
                versions[i]["drive"] = _get_param_value(pcl[tid])

            # 座位数 → extract from 车身 or 基本参数
            for seat_key in ["座位数(个)", "座位数"]:
                tid = _name_to_titleid.get(seat_key)
                if tid and tid in pcl:
                    val = _get_param_value(pcl[tid])
                    if val and "座" not in val:
                        val = f"{val}座"
                    versions[i]["seats"] = val or ""
                    break

    # 清理 other（如果只有少量杂项）
    if "other" in dims and len(dims["other"]) < 2:
        del dims["other"]

    return {
        "brand": brand,
        "model_name": series,
        "spec_id": spec_id,
        "versions": versions,
        "dims": dims,
    }


def _get_param_value(param: dict) -> str:
    """从 paramconflist 的一项中提取实际值。"""
    # 值可能在 value, sublist, 或其他字段中
    if "value" in param and param["value"]:
        return str(param["value"]).strip()
    if "sublist" in param and param["sublist"]:
        parts = []
        for sub in param["sublist"]:
            if isinstance(sub, dict):
                v = sub.get("value") or sub.get("name") or sub.get("subvalue") or ""
                if v:
                    parts.append(str(v).strip())
            elif isinstance(sub, str):
                parts.append(sub.strip())
        return " / ".join(parts) if parts else ""
    # 可能 value 在其他字段
    for k in ("configvalue", "paramvalue", "itemvalue"):
        if k in param and param[k]:
            return str(param[k]).strip()
    return ""


# ── URL 解析 ──────────────────────────────────────────────────────────


def _parse_autohome_url(url: str) -> Optional[str]:
    """从汽车之家 URL 提取 spec_id。"""
    # https://www.autohome.com.cn/spec/1001152/config.html
    m = re.search(r"/spec/(\d+)", url)
    if m:
        return m.group(1)
    return None


def detect_site(url: str) -> Optional[str]:
    if "autohome.com.cn" in url:
        return "autohome"
    if "dongchedi.com" in url:
        return "dongchedi"
    return None


# ── HTML 提取（非 autohome 站点兜底）──────────────────────────────────


def _extract_html_fallback(url: str) -> dict:
    """Playwright 渲染 + HTML 解析兜底。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(2000)
            html = page.content()
        finally:
            ctx.close()
            browser.close()

    # 解析 HTML 中的 table
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    best = None
    best_rows = 0
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > best_rows:
            best_rows = len(rows)
            best = t

    if not best or best_rows < 3:
        return {"_error": "未找到配置表格", "versions": [], "dims": {}}

    # 解析
    rows = best.find_all("tr")
    header_cells = rows[0].find_all(["th", "td"])
    versions = []
    for cell in header_cells[1:]:
        vname = cell.get_text(strip=True)
        if vname and len(vname) < 60:
            versions.append({"id": f"v{len(versions)+1}", "version": vname, "price": 0})

    if not versions:
        return {"_error": "未找到版本列", "versions": [], "dims": {}}

    dims = {}
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        fn = cells[0].get_text(strip=True)
        if not fn or len(fn) > 50:
            continue
        dk = _classify_field(fn)
        for i, cell in enumerate(cells[1:]):
            if i >= len(versions):
                break
            val = cell.get_text(strip=True)
            if not val or val in ("-", "●", "○", "—", "无", "暂无", "标配", ""):
                continue
            dims.setdefault(dk, {}).setdefault(versions[i]["id"], {})[fn] = val

    return {"versions": versions, "dims": dims, "brand": "", "model_name": ""}


DIM_KW_MAP = {
    "车身尺寸|长度|宽度|高度|轴距|整备|风阻": "size",
    "外观|车灯|头灯|大灯|尾灯|车门|天窗|车漆|轮毂|轮胎|格栅": "design_ext",
    "座椅|内饰颜色|内饰材质|方向盘材质|遮阳帘|氛围灯|阅读灯": "seat",
    "空调|冰箱|NVH|隔音|静谧|空气净化|香氛|行李|后备箱|后备厢|乘坐空间|二排.*空间|三排.*空间|前备箱": "comfort",
    "智驾|辅助驾驶|自动驾驶|激光雷达|毫米波|超声波|摄像头.*数量|Orin|Thor|ADAS": "ad",
    "座舱芯片|中控|仪表|屏幕|音响|扬声器|HUD|抬头显示|后排.*屏|车机": "cockpit",
    "悬架|悬挂|转向|制动|刹车|CDC|稳定杆|后轮转向|转弯半径|涉水": "chassis",
    "电池|续航|充电|电机|功率|扭矩|能耗|百公里加速|零百|驱动方式|能源类型|平台|架构": "ev",
    "气囊|车身结构|ABS|ESP|安全带|AEB|车门解锁|AI防护": "safety",
}


def _classify_field(name: str) -> str:
    for keywords, dk in DIM_KW_MAP.items():
        for kw in keywords.split("|"):
            if re.search(kw, name):
                return dk
    return "other"


# ── 主入口 ────────────────────────────────────────────────────────────


def extract_from_url(url: str) -> dict:
    site = detect_site(url)

    if site == "autohome":
        spec_id = _parse_autohome_url(url)
        if spec_id:
            return extract_autohome(spec_id)
        else:
            return {"_error": "无法从URL解析autohome spec_id"}

    # 其他站点：Playwright HTML 提取
    print(f"  → 站点: {site or '未知'}", file=sys.stderr)
    return _extract_html_fallback(url)


# ── 保存 ──────────────────────────────────────────────────────────────


def save_as_local_model(data: dict, model_id: str = "") -> str:
    import db

    brand = (data.get("brand") or "").strip()
    model_name = (data.get("model_name") or "").strip()

    if not model_id:
        slug = re.sub(r"[^\w一-鿿]", "_", f"{brand}_{model_name}")
        model_id = f"local_{slug}" if slug else f"local_{int(time.time())}"

    for i, v in enumerate(data.get("versions", [])):
        if not v.get("id"):
            v["id"] = f"{model_id}_v{i+1}"

    prices = [v.get("price") for v in data["versions"] if isinstance(v.get("price"), (int, float)) and v["price"] > 0]
    price_range = ""
    if prices:
        lo, hi = min(prices), max(prices)
        price_range = f"{lo}-{hi}万" if lo != hi else f"{lo}万"

    model_data = {
        "id": model_id,
        "name": f"{brand} {model_name}".strip(),
        "model_name": model_name or f"{brand} {model_name}".strip(),
        "brand": brand,
        "model_type": data.get("model_type", ""),
        "status": "正式上市",
        "generation": data.get("generation", ""),
        "price_range": price_range,
        "sort_code": "",
        "versions": data["versions"],
        "dims": data["dims"],
    }

    db.init_db()
    db.save_local_model(model_id, model_data)
    print(f"  ✓ 已保存: {model_id}", file=sys.stderr)
    return model_id


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <URL> [--save] [--model-id ID]", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    do_save = "--save" in sys.argv
    model_id = ""
    if "--model-id" in sys.argv:
        idx = sys.argv.index("--model-id")
        model_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""

    result = extract_from_url(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if do_save and result.get("versions"):
        mid = save_as_local_model(result, model_id)
        print(f"\n刷新: http://localhost:5000", file=sys.stderr)
