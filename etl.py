"""ETL 流水线：从 Lark Base 拉取全部数据，处理后存入 SQLite 缓存。

用法：
    python3 etl.py          # 执行一次全量 ETL
"""
import sys
from pathlib import Path

import db
from benchmark_site import EXCLUDE_SORT_CODES, build_site
from spectrum_data import build_chart_rows, split_length_groups
from vehicle_profile import EXCLUDED_STATUS, build_model_data, load_all_tables


def run_etl() -> str:
    """拉取 Lark Base → 构建 HTML → 写入 SQLite。返回生成的 HTML 字符串。"""
    print("拉取 Lark Base 数据...", file=sys.stderr)
    raw = load_all_tables()

    print("聚合车型数据...", file=sys.stderr)
    models_data = build_model_data(raw)
    print(f"  ✓ {len(models_data)} 款车型", file=sys.stderr)

    print("生成 HTML...", file=sys.stderr)
    html = build_site(raw, models_data)

    db.set_cache("html", html)
    db.set_cache("models_count", len(models_data))
    versions_count = sum(len(m["versions"]) for m in models_data)
    db.set_cache("versions_count", versions_count)

    print(f"  ✓ 已写入 SQLite：{len(models_data)} 款车型 / {versions_count} 个版本", file=sys.stderr)
    return html


if __name__ == "__main__":
    db.init_db()
    run_etl()
    print(f"ETL 完成，数据已缓存至 {db.DB_PATH}", file=sys.stderr)
