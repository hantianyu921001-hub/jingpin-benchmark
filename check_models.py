#!/usr/bin/env python3
"""批量校核所有车型数据，基于 9X/8X 的修改模式。"""
import sys, json, re
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

import db
from vehicle_profile import DIMENSION_DEFS, BRAND_ORDER


def load_all_models():
    """从 Flask 页面加载 PROFILE_DATA。"""
    import urllib.request
    html = urllib.request.urlopen("http://localhost:5000/").read().decode()
    m = re.search(r'var PROFILE_DATA = (\[.+?\]);', html, re.DOTALL)
    return json.loads(m.group(1))


def check_model(m, issues):
    """检查单个车型的问题。"""
    mid = m["id"]
    name = f"{m['brand']} {m['model_name']}"
    dims = m.get("dims", {})
    versions = m.get("versions", [])
    overrides = db.get_overrides_for_model(mid)

    # ── 规则1: 旧维度key残留 ──
    for old_key in ["space", "nvh"]:
        if old_key in dims:
            data = dims[old_key]
            if data:
                cnt = sum(len(v) for v in data.values())
                issues.append({
                    "model": name, "mid": mid,
                    "rule": "旧维度key残留",
                    "detail": f"'{old_key}' 应迁移到 'comfort'，{cnt} 个值",
                    "severity": "high",
                })

    # ── 规则2: override 中包含空值 ──
    empty_ovs = [ov for ov in overrides if not ov["field_value"].strip()]
    if empty_ovs:
        by_dim = defaultdict(list)
        for ov in empty_ovs:
            by_dim[ov["dim_key"] or "(ver)"].append(ov["field_name"])
        for dk, fns in sorted(by_dim.items()):
            issues.append({
                "model": name, "mid": mid,
                "rule": "override空值",
                "detail": f"维度'{dk}'中 {len(fns)} 个字段值为空: {fns[:5]}",
                "severity": "medium",
            })

    # ── 规则3: override 中仍有符号值(未转实际值) ──
    symbol_ovs = [ov for ov in overrides if ov["field_value"].strip() in ("●", "○", "—", "● / ○", "●/○")]
    if symbol_ovs:
        issues.append({
            "model": name, "mid": mid,
            "rule": "override符号值",
            "detail": f"{len(symbol_ovs)} 个字段仍是符号(●/○)而非实际值",
            "severity": "high",
        })

    # ── 规则4: 维度数据极度稀疏 (< 3 fields且系统定义了更多) ──
    dim_defs = {d["key"]: d["fields"] for d in DIMENSION_DEFS}
    for dk, bv in dims.items():
        all_fns = set()
        for vf in bv.values():
            all_fns.update(vf.keys())
        expected = len(dim_defs.get(dk, []))
        actual = len(all_fns)
        if expected >= 6 and actual <= 2 and actual > 0:
            issues.append({
                "model": name, "mid": mid,
                "rule": "维度数据稀疏",
                "detail": f"'{dk}': 仅 {actual}/{expected} 字段有数据",
                "severity": "medium",
            })

    # ── 规则5: 版本数据缺失（常见字段为空） ──
    missing_ver_fields = []
    for v in versions:
        for key, label in [("energy", "能源"), ("drive", "驱动"), ("seats", "座位"), ("battery", "电池容量")]:
            if not v.get(key):
                if label not in missing_ver_fields:
                    missing_ver_fields.append(label)
    if missing_ver_fields:
        issues.append({
            "model": name, "mid": mid,
            "rule": "版本信息缺失",
            "detail": f"缺少: {missing_ver_fields}",
            "severity": "high",
        })

    # ── 规则6: 完全缺失的维度（定义了但无任何数据） ──
    for d in DIMENSION_DEFS:
        dk = d["key"]
        if dk not in dims or not dims[dk]:
            issues.append({
                "model": name, "mid": mid,
                "rule": "维度完全缺失",
                "detail": f"'{d['title']}' 维度无任何数据",
                "severity": "high",
            })
            continue
        # check if all versions have no data
        all_empty = all(not vf for vf in dims[dk].values())
        if all_empty:
            issues.append({
                "model": name, "mid": mid,
                "rule": "维度完全缺失",
                "detail": f"'{d['title']}' 维度无任何数据",
                "severity": "high",
            })

    # ── 规则7: override 重复（同一字段多条记录） ──
    dup_check = defaultdict(list)
    for ov in overrides:
        key = (ov["version_id"], ov["dim_key"], ov["field_name"])
        dup_check[key].append(ov["field_value"])
    dups = {k: v for k, v in dup_check.items() if len(v) > 1}
    if dups:
        issues.append({
            "model": name, "mid": mid,
            "rule": "override重复",
            "detail": f"{len(dups)} 组重复 (同vid+dim+field多条记录)",
            "severity": "low",
        })


def main():
    print("加载数据...")
    models = load_all_models()
    issues = []

    for m in models:
        if m.get("status") != "正式上市":
            continue
        if not m.get("versions"):
            continue
        check_model(m, issues)

    # 排序：severity > brand > model
    sev_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (sev_order.get(i["severity"], 9), i["model"]))

    # 输出
    print(f"\n{'='*70}")
    print(f"共检查 {len(models)} 个车型，发现 {len(issues)} 个问题\n")

    if not issues:
        print("✅ 未发现问题！")
        return

    # 按规则分组统计
    by_rule = defaultdict(list)
    for i in issues:
        by_rule[i["rule"]].append(i)

    print("── 问题汇总 ──")
    for rule, items in sorted(by_rule.items(), key=lambda x: -len(x[1])):
        models_affected = len(set(i["model"] for i in items))
        sevs = set(i["severity"] for i in items)
        sev_str = "/".join(sorted(sevs))
        print(f"  [{sev_str}] {rule}: {len(items)} 处 ({models_affected} 车型)")

    print(f"\n── 详细列表 ──")
    for i in issues:
        sev_mark = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(i["severity"], "  ")
        print(f"  {sev_mark} [{i['rule']}] {i['model']}")
        print(f"      {i['detail']}")


if __name__ == "__main__":
    main()
