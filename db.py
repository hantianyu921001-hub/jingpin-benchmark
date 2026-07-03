"""SQLite 缓存层 — 存储 ETL 结果，避免每次都重新拉取 Lark Base。"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "benchmark.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field_overrides (
            version_id  TEXT NOT NULL,
            dim_key     TEXT NOT NULL DEFAULT '',
            field_name  TEXT NOT NULL,
            model_id    TEXT NOT NULL,
            field_value TEXT NOT NULL,
            updated_at  INTEGER NOT NULL,
            PRIMARY KEY (version_id, dim_key, field_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_config (
            dim_key     TEXT PRIMARY KEY,
            fields_json TEXT NOT NULL,
            updated_at  INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS local_models (
            model_id    TEXT PRIMARY KEY,
            data_json   TEXT NOT NULL,
            updated_at  INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_override(model_id: str, version_id: str, dim_key, field_name: str, field_value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO field_overrides VALUES (?,?,?,?,?,?)",
        (version_id, dim_key or "", field_name, model_id, field_value, int(time.time())),
    )
    conn.commit()
    conn.close()


def get_overrides_for_model(model_id: str):
    """返回该车型所有字段覆盖，list of dicts。"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT version_id, dim_key, field_name, field_value FROM field_overrides WHERE model_id=?",
        (model_id,),
    ).fetchall()
    conn.close()
    return [
        {"version_id": r[0], "dim_key": r[1] or None, "field_name": r[2], "field_value": r[3]}
        for r in rows
    ]


def get_dim_fields(dim_key: str, default_fields: list) -> list:
    """返回维度字段列表；SQLite有配置则用SQLite，否则用默认值。"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT fields_json FROM dim_config WHERE dim_key=?", (dim_key,)
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else list(default_fields)


def set_dim_fields(dim_key: str, fields: list):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO dim_config VALUES (?,?,?)",
        (dim_key, json.dumps(fields, ensure_ascii=False), int(time.time())),
    )
    conn.commit()
    conn.close()


def get_all_dim_configs() -> dict:
    """返回所有自定义维度配置 {dim_key: [fields]}。"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT dim_key, fields_json FROM dim_config").fetchall()
    conn.close()
    return {r[0]: json.loads(r[1]) for r in rows}


def get_cache(key: str):
    """返回 (value, updated_at)，不存在则返回 (None, None)。"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT value, updated_at FROM cache WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None, None
    return json.loads(row[0]), row[1]


def set_cache(key: str, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, updated_at) VALUES (?,?,?)",
        (key, json.dumps(value, ensure_ascii=False, default=str), int(time.time())),
    )
    conn.commit()
    conn.close()


def cache_updated_at(key: str) -> str:
    """返回可读的更新时间字符串，未缓存则返回空字符串。"""
    _, ts = get_cache(key)
    if ts is None:
        return ""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


# ── 本地车型（不在飞书中的车型，纯本地维护）────────────────────────────

def save_local_model(model_id: str, data: dict):
    """保存/更新一个本地车型的完整 JSON 数据。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO local_models VALUES (?,?,?)",
        (model_id, json.dumps(data, ensure_ascii=False, default=str), int(time.time())),
    )
    conn.commit()
    conn.close()


def get_local_model(model_id: str):
    """读取单个本地车型 JSON，不存在返回 None。"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT data_json FROM local_models WHERE model_id=?", (model_id,)
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def get_all_local_models() -> list:
    """返回所有本地车型 dict 列表。"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT model_id, data_json FROM local_models ORDER BY model_id").fetchall()
    conn.close()
    result = []
    for model_id, data_json in rows:
        d = json.loads(data_json)
        d["id"] = model_id  # 确保 id 一致
        result.append(d)
    return result


def delete_local_model(model_id: str):
    """删除一个本地车型。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM local_models WHERE model_id=?", (model_id,))
    conn.commit()
    conn.close()
