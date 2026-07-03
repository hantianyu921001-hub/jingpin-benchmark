#!/usr/bin/env python3
"""将本地车型 field_overrides 同步到飞书 Base。

用法：
    python3 sync_to_lark.py <model_id>           # 预览模式：显示将要同步的内容
    python3 sync_to_lark.py <model_id> --commit  # 实际写入飞书
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import db

BASE_TOKEN = "E571b0YbQa2MxysVn4RctXcDn7d"

# 飞书表 ID
TABLE_IDS = {
    "models":  "tbl92hQB5ngDEvRH",
    "prices":  "tblWDFfm3M3uX9qx",
    "design":  "tblUAEHLyihXdwXn",
    "size":    "tblROhrR1M84SZrp",
    "space":   "tbll00EXYEc4S0hf",
    "seat":    "tblWUYBYTprgY55P",
    "nvh":     "tblyyiC7y6r21Ti5",
    "light":   "tblFxRXeclZexjq6",
    "ad":      "tblFLQjKa91NiFKz",
    "cockpit": "tblZv13LhbwJ4l6e",
    "chassis": "tblVhYbXA8WQDSkS",
    "ev":      "tbllgpvch11HVnqq",
    "safety":  "tblTjuDT2NHD3xGR",
}

# dim_key → 飞书表名映射
DIM_TO_TABLE = {
    "design_ext": "design",
    "size":       "size",
    "space":      "space",
    "seat":       "seat",
    "nvh":        "nvh",
    "light":      "light",
    "ad":         "ad",
    "cockpit":    "cockpit",
    "chassis":    "chassis",
    "ev":         "ev",
    "safety":     "safety",
}

# 版本级 field label → prices 表字段名
VERSION_LABEL_TO_FIELD = {
    "核心配置": "核心配置摘要",
    "能源":     "能源",
    "座位":     "座位数",
    "驱动":     "驱动",
    "电池容量": "电池电量",
}


def preview(model_id: str):
    """预览将要同步的数据。"""
    model = db.get_local_model(model_id)
    if not model:
        print(f"错误：未找到本地车型 {model_id}")
        sys.exit(1)

    overrides = db.get_overrides_for_model(model_id)

    print(f"车型: {model.get('name', model_id)}")
    print(f"品牌: {model.get('brand', '')}")
    print(f"版本: {len(model.get('versions', []))} 个")
    print(f"override 条数: {len(overrides)}")
    print()

    # 分组
    by_version = {}  # label → {version_id: value}
    by_dim = {}      # dim_key → {version_id: {field: value}}
    for ov in overrides:
        dk = ov["dim_key"]
        vid, fn, fv = ov["version_id"], ov["field_name"], ov["field_value"]
        if dk:
            by_dim.setdefault(dk, {}).setdefault(vid, {})[fn] = fv
        else:
            by_version.setdefault(fn, {}).setdefault(vid, fv)

    # 版本级字段 → prices 表
    print("── 版本价格表 (10_版本价格) ──")
    for label, field in VERSION_LABEL_TO_FIELD.items():
        if label in by_version:
            for vid, val in by_version[label].items():
                vname = next((v["version"] for v in model["versions"] if v["id"] == vid), vid[:8])
                print(f"  [{vname}] {field} = {val[:40]}")

    # 维度字段 → 各维度表
    for dk, table_name in DIM_TO_TABLE.items():
        if dk not in by_dim:
            continue
        print(f"\n── {table_name} ({TABLE_IDS[table_name][:8]}...) ──")
        for vid, fields in by_dim[dk].items():
            vname = next((v["version"] for v in model["versions"] if v["id"] == vid), vid[:8])
            for fn, fv in fields.items():
                print(f"  [{vname}] {fn} = {fv[:60]}")


def commit(model_id: str):
    """实际写入飞书 Base。"""
    import subprocess

    model = db.get_local_model(model_id)
    if not model:
        print(f"错误：未找到本地车型 {model_id}")
        sys.exit(1)

    overrides = db.get_overrides_for_model(model_id)

    # 1. 创建/查找车型记录
    model_name = model.get("model_name", model.get("name", ""))
    brand = model.get("brand", "")
    print(f"车型: {model_name} ({brand})")

    # 查找现有车型记录
    result = subprocess.run(
        ["lark-cli", "base", "+record-list", "--base-token", BASE_TOKEN,
         "--table-id", TABLE_IDS["models"], "--limit", "200"],
        capture_output=True, text=True,
    )
    # 解析现有记录找匹配...
    # TODO: 完整实现需要解析 JSON 匹配车型

    print("⚠ 同步到飞书功能开发中。请先通过网页预览确认数据。")
    print("  预览模式：python3 sync_to_lark.py", model_id)


if __name__ == "__main__":
    model_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not model_id:
        print("用法: python3 sync_to_lark.py <model_id> [--commit]")
        sys.exit(1)

    if "--commit" in sys.argv:
        commit(model_id)
    else:
        preview(model_id)
