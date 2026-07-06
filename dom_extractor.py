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

# autohome 字段名 → 系统字段名映射
AH_FIELD_MAP = {
    # 尺寸
    "长度(mm)": "长(mm)", "宽度(mm)": "宽(mm)", "高度(mm)": "高(mm)",
    "轴距(mm)": "轴距(mm)", "前轮距(mm)": None, "后轮距(mm)": None,
    "最小离地间隙(mm)": "特殊通过能力", "最小转弯半径(m)": "转弯半径",
    "车门数(个)": None, "座位数(个)": None, "油箱容积(L)": None,
    "车身结构": None, "车门开启方式": None,
    # 三电
    "能源类型": "能源形式", "厂商指导价(元)": None, "级别": None,
    "CLTC纯电续航里程(km)": "CLTC纯电续航(km)",
    "WLTC纯电续航里程(km)": "WLTC纯电续航(km)",
    "WLTC综合油耗(L/100km)": None,
    "官方0-100km/h加速(s)": "零百加速(s)",
    "最大功率(kW)": "最大功率(kW)", "最大马力(Ps)": None,
    "最大扭矩(N·m)": "最大扭矩(Nm)", "最高车速(km/h)": None,
    "发动机": None, "变速箱": None, "电动机(Ps)": None,
    "电池能量(kWh)": "电池容量(kWh)", "电芯品牌": None,
    "电池类型": None, "整车质保": None,
    "驱动方式": "驱动形式", "环保标准": None,
    # 底盘
    "前悬架类型": "前悬架", "后悬架类型": "后悬架",
    "空气悬挂类型": "空气悬架", "可变悬架功能": "CDC",
    "前制动器类型": "制动", "后制动器类型": None,
    "前轮胎规格": "轮胎规格", "后轮胎规格": None,
    "驾驶模式切换": None, "助力类型": "转向",
    "车体结构": "底盘材质", "四驱形式": None, "驻车制动类型": None,
    # 智能驾驶
    "辅助驾驶系统": "智驾系统/芯片", "辅助驾驶等级": "智能驾驶能力",
    "辅助驾驶芯片": None, "巡航系统": "智能驾驶能力",
    "激光雷达数量": "激光雷达数量/位置",
    "毫米波雷达数量": "毫米波雷达数量/位置",
    "超声波雷达数量": "超声波雷达数量/位置",
    "摄像头数量": "摄像头数量/位置",
    "前方感知摄像头": None, "车内摄像头数量": None,
    "驾驶辅助影像": None, "激光雷达线数": None,
    "前/后驻车雷达": None, "辅助驾驶路段": None, "地图品牌": None,
    # 智能座舱
    "中控彩色屏幕": "前排屏", "中控屏幕尺寸": "前排屏",
    "中控屏幕类型": None, "中控屏幕分辨率": None,
    "副驾娱乐屏尺寸": "前排屏", "副驾屏幕类型": None,
    "后排液晶屏幕": "后排娱乐屏", "后排液晶屏幕尺寸": "后排娱乐屏",
    "后排液晶屏幕类型": None, "后排多媒体屏幕数量": None,
    "扬声器品牌名称": "音响系统", "扬声器数量": "扬声器数量",
    "手机互联/映射": None, "语音识别控制系统": None,
    "4G/5G网络": None, "车机智能芯片": "座舱系统/芯片",
    "车载智能系统": "座舱系统/芯片",
    "手机APP远程功能": None, "手机无线充电功能": None,
    "车内环境氛围灯": "阅读灯/氛围灯",
    # 座椅
    "座椅材质": "一排座椅", "座椅布局": "座椅布局",
    "主座椅调节方式": "一排座椅", "副座椅调节方式": "一排座椅",
    "前排座椅功能": "一排座椅", "第二排座椅调节": "二排座椅",
    "第二排座椅功能": "二排座椅", "第三排座椅调节": "三排座椅",
    "第三排座椅功能": "三排座椅", "零重力座椅": "座椅卖点",
    "方向盘材质": "方向盘", "方向盘位置调节": "方向盘",
    "HUD抬头尺寸": "HUD", "内后视镜功能": None,
    "电动座椅记忆功能": None, "换挡形式": None,
    "主/副驾驶座电动调节": None,
    # 灯光
    "近光灯光源": "头灯", "远光灯光源": "头灯",
    "灯光特色功能": "ADB/DLP大灯", "天窗类型": "车门",
    "电动吸合车门": "电吸/防夹", "感应雨刷功能": None,
    "前/后电动车窗": None, "车窗一键升降功能": None,
    "侧窗多层隔音玻璃": None, "车内化妆镜": None,
    "外后视镜功能": None, "后排侧窗遮阳帘": "遮阳帘/玻璃",
    # 外观
    "轮圈材质": "轮毂/轮胎", "钥匙类型": None,
    "无钥匙进入功能": None, "远程启动功能": None,
    "车侧脚踏板": None,
    # 安全
    "主/副驾驶座安全气囊": "安全气囊数量",
    "前/后排侧气囊": "安全气囊数量",
    "前/后排头部气囊(气帘)": "安全气囊数量",
    "胎压监测功能": "主动安全", "安全带未系提醒": "安全带",
    # 舒适
    "空调温度控制方式": "空调", "后备厢容积(L)": "后备箱空间",
    "电池快充时间(小时)": None, "电池快充电量范围(%)": None,
}

# autohome 字段名 → 强制目标 dim_key（覆盖分类映射）
AH_FIELD_DIM_OVERRIDE = {
    "转弯半径": "chassis", "特殊通过能力": "chassis",
    "后备箱空间": "comfort", "后备厢容积(L)": "comfort",
    "驾驶模式切换": "chassis", "拖挂资质": "chassis",
    "轮胎规格": "size",
}

# 需要合并到字段值的映射（autohome用多行表示同一概念）
AH_MERGE_FIELDS = {
    "安全气囊数量", "一排座椅", "二排座椅", "三排座椅",
    "头灯", "前排屏", "后排娱乐屏", "音响系统",
    "智能驾驶能力", "智驾系统/芯片",
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

            # 应用字段名映射
            mapped_fn = AH_FIELD_MAP.get(field_name)
            if mapped_fn is None:
                continue  # 跳过不需要的字段
            if mapped_fn:
                field_name = mapped_fn

            # 目标维度覆盖（如后备箱空间→comfort，转弯半径→chassis）
            final_dim = AH_FIELD_DIM_OVERRIDE.get(field_name, dim_key)

            # 合并字段：同一目标字段拼接（如多个气囊合并）
            target = dims.setdefault(final_dim, {}).setdefault(vid, {})
            if field_name in AH_MERGE_FIELDS and field_name in target:
                existing = target[field_name]
                if val not in existing:
                    target[field_name] = f"{existing}；{val}"
            else:
                target[field_name] = val

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
    # 1. 优先 value 字段
    if param.get("value") and str(param["value"]).strip():
        return str(param["value"]).strip()
    # 2. sublist 数组
    if param.get("sublist"):
        parts = []
        for sub in param["sublist"]:
            if isinstance(sub, dict):
                v = sub.get("value") or sub.get("subvalue") or sub.get("name") or ""
                if v:
                    parts.append(str(v).strip())
            elif isinstance(sub, str):
                parts.append(sub.strip())
        return " / ".join(parts) if parts else ""
    # 3. itemname 即为值（autohome 常见模式）
    val = param.get("itemname", "")
    if val:
        val = str(val).strip()
        # 过滤掉明显是标签而非值的项（包含"万元""万"的价格项通常走value字段）
        if val not in ("●", "○", "—", "-", "/", "无", "暂无", "标配", "选配"):
            return val
    # 4. 其他可能的字段
    for k in ("configvalue", "paramvalue", "itemvalue"):
        if param.get(k) and str(param[k]).strip():
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
    if "yiche.com" in url or "bitauto.com" in url:
        return "yiche"
    return None


# ── 易车网提取 ────────────────────────────────────────────────────────


def extract_yiche(url: str) -> dict:
    """从易车网页面提取配置数据。

    策略：
    1. 从 URL 解析 series spell → 搜索 API 验证
    2. Playwright 加载配置页 → 提取表格
    3. 解析 spec 信息
    """
    # 从 URL 提取 series spell 和中文名
    m = re.search(r"car\.yiche\.com/([a-z0-9]+)", url)
    spell = m.group(1) if m else ""

    # 尝试从 URL 路径提取中文名（如果有）
    # e.g., /zeekrex1h/peizhi/ or /jike_9x/peizhi/
    chinese_hint = ""
    m2 = re.search(r"/([a-z]+)_?(\d+[a-z]?)", spell)
    if m2:
        chinese_hint = m2.group(2)  # "9x" from "zeekrex1h"

    # 搜索 API 获取 series ID
    series_info = {}
    search_keywords = [spell, chinese_hint] if chinese_hint else [spell]
    for keyword in search_keywords:
        if not keyword:
            continue
        try:
            param = json.dumps({"keyword": keyword})
            api_url = (
                f"https://mapi.yiche.com/web_app/api/v1/search/suggest"
                f"?t={int(time.time() * 1000)}&sign=&devid=&uid=&ver=guanwangPC&cid=508"
                f"&param={urllib.parse.quote(param)}"
            )
            data = _fetch_json(api_url, timeout=10)
            items = (data.get("data") or [])
            for item in items:
                if item.get("type") == 0:  # series type
                    show = item.get("showName", "")
                    series_info = {
                        "series_id": item.get("id"),
                        "name": item.get("name", ""),
                        "show_name": show,
                        "brand": show.split(" ")[0] if " " in show else "",
                    }
                    break
            if series_info:
                print(f"  → 搜索命中: {series_info.get('show_name', keyword)}", file=sys.stderr)
                break
        except Exception as e:
            continue

    # Playwright 加载配置页（易车用 domcontentloaded 避免超时）
    config = {"versions": [], "dims": {}}
    try:
        config = _extract_html_fallback(url, wait_strategy="domcontentloaded")
    except Exception as e:
        print(f"  ⚠ Playwright提取失败: {e}", file=sys.stderr)

    # 组装结果
    model_name = series_info.get("name") or spell or re.search(r"/([^/]+)/peizhi", url)
    model_name = model_name.group(1) if hasattr(model_name, "group") else str(model_name)

    return {
        "brand": series_info.get("brand", ""),
        "model_name": model_name,
        "series_id": str(series_info.get("series_id", "")),
        "versions": config.get("versions", []),
        "dims": config.get("dims", {}),
        "_source": "yiche",
        "_note": "易车配置页需浏览器渲染，数据可能不完整。建议用汽车之家URL获取完整配置。",
    }


# ── HTML 提取（非 autohome 站点兜底）──────────────────────────────────


def _extract_html_fallback(url: str, wait_strategy: str = "networkidle") -> dict:
    """Playwright 渲染 + HTML 解析兜底。

    Args:
        url: 目标 URL
        wait_strategy: 等待策略 — 'networkidle' (默认) 或 'domcontentloaded' (易车等SPA)
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until=wait_strategy, timeout=20000)
            page.wait_for_timeout(3000)
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

    if site == "yiche":
        print(f"  → 站点: 易车网", file=sys.stderr)
        return extract_yiche(url)

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
