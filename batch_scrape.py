#!/usr/bin/env python3
"""批量爬取补充所有车型的缺失配置数据。"""
import sys, json, time, urllib.request, urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

import db
from dom_extractor import extract_autohome, _parse_autohome_url, _fetch_json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def find_autohome_spec(keyword: str) -> str | None:
    """通过 autohome suggest API 查找车型的 spec_id。"""
    try:
        param = json.dumps({"keyword": keyword})
        url = (
            f"https://mapi.yiche.com/web_app/api/v1/search/suggest"
            f"?t={int(time.time() * 1000)}&sign=&devid=&uid=&ver=guanwangPC&cid=508"
            f"&param={urllib.parse.quote(param)}"
        )
        data = _fetch_json(url, timeout=8)
        items = data.get("data", [])
        for item in items:
            if item.get("type") == 0:
                return item.get("id")  # yiche series ID
    except:
        pass
    return None


def find_autohome_spec_via_playwright(model_name: str, model_id: str) -> str | None:
    """使用 Playwright 在 autohome 搜索车型并返回第一个 spec_id。"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()

            specs_found = []
            page.on("response", lambda r: specs_found.append(r)
                    if "getSpecList" in r.url else None)

            # 访问 autohome 搜索
            page.goto(f"https://www.autohome.com.cn/beijing/",
                      wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(2000)

            # 在搜索框输入
            try:
                page.fill('input[type="text"]:visible', model_name)
                page.wait_for_timeout(1500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
            except:
                pass

            # 从 getSpecList 响应中提取 spec_id
            for resp in specs_found:
                try:
                    data = resp.json()
                    specs = data.get("result", {}).get("specList", [])
                    if specs:
                        first = specs[0].get("specList", [{}])[0] if isinstance(specs[0], dict) else specs[0]
                        sp_id = first.get("specId", "")
                        if sp_id:
                            ctx.close(); browser.close()
                            return str(sp_id)
                except:
                    pass

            ctx.close(); browser.close()
    except:
        pass
    return None


def scrape_and_supplement(model_name: str, model_id: str) -> int:
    """爬取一个车型的 autohome 数据并补充到 overrides。返回新增条数。"""
    print(f"  {model_name} ({model_id[:12]}...)", end=" ")

    # 尝试从 autohome URL 爬取
    # 方法1: 用易车 ID 去 autohome 反查
    spec_id = None

    # 方法2: Playwright 搜索
    spec_id = find_autohome_spec_via_playwright(model_name, model_id)

    if not spec_id:
        print("→ 未找到 autohome spec")
        return 0

    print(f"→ spec={spec_id}", end=" ")

    try:
        data = extract_autohome(spec_id)
    except Exception as e:
        print(f"→ 爬取失败: {e}")
        return 0

    versions = len(data.get("versions", []))
    if versions == 0:
        print("→ 无版本数据")
        return 0

    # 记录已有字段
    existing_overrides = db.get_overrides_for_model(model_id)
    existing_fields = set()
    for r in existing_overrides:
        existing_fields.add((r["dim_key"], r["field_name"]))

    # 只保存新字段
    count = 0
    for dim_key, by_version in data.get("dims", {}).items():
        if dim_key == "other":
            continue
        for ah_vid, fields in by_version.items():
            for field_name, value in fields.items():
                value = str(value).strip()
                if not value or value in ("-", "●", "○", "—", "无", "暂无"):
                    continue
                if (dim_key, field_name) in existing_fields:
                    continue
                # 使用第一个可用的 version_id
                db.save_override(model_id, list(by_version.keys())[0] if by_version else ah_vid,
                                 dim_key, field_name, value)
                count += 1

    print(f"→ +{count} 条")
    return count


def main():
    # 从 Flask 页面获取所有车型数据
    from vehicle_profile import build_model_data
    from etl import load_all_tables

    raw = load_all_tables()
    models = build_model_data(raw)

    # 按字段数排序，优先补充数据少的
    models.sort(key=lambda m: sum(
        len(set().union(*[set(vf.keys()) for vf in bv.values()]))
        for bv in m.get("dims", {}).values() if bv
    ))

    print(f"共 {len(models)} 个车型，按数据完整度排序:\n")

    total_added = 0
    for m in models:
        dims = m.get("dims", {})
        total_fields = sum(
            len(set().union(*[set(vf.keys()) for vf in bv.values()]))
            for bv in dims.values() if bv
        )
        if total_fields >= 50:  # 数据已足够
            continue
        if m.get("status") != "正式上市":
            continue

        added = scrape_and_supplement(m.get("model_name", m.get("name", "")), m["id"])
        total_added += added

    print(f"\n总计新增 {total_added} 条 override")


if __name__ == "__main__":
    main()
