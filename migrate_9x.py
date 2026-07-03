#!/usr/bin/env python3
"""将 zeekr9x_page.py 中的本地数据写入 SQLite field_overrides（使用 Lark 记录 ID）。"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import db
from zeekr9x_page import versions, dims

MODEL_ID = "recvkZaU9T7fuB"

# 本地 fake ID → Lark 记录 ID
VID_MAP = {
    "v_max":       "recvkZaULutysp",
    "v_ultra55":   "recvkZaVnSTBFk",
    "v_ultra70":   "recvkZaWc08HQk",
    "v_hyper":     "recvkZaWPOxI6c",
    "v_yaoheiban": "recvkZaXwcaEK9",
}

db.init_db()

# 1. 清理旧 override
conn = sqlite3.connect(db.DB_PATH)
conn.execute("DELETE FROM field_overrides WHERE model_id IN (?,?)",
             (MODEL_ID, "zeekr_9x_2025"))
conn.commit()
conn.close()
print("✓ 已清理旧 override")

count = 0

# 2. 版本级字段
VERSION_LABEL_MAP = {
    "核心配置": "summary",
    "能源":     "energy",
    "座位":     "seats",
    "驱动":     "drive",
    "电池容量": "battery",
}
for v in versions:
    lark_vid = VID_MAP.get(v["id"])
    if not lark_vid:
        continue
    for label, key in VERSION_LABEL_MAP.items():
        val = str(v.get(key, "") or "").strip()
        if not val:
            continue
        db.save_override(MODEL_ID, lark_vid, "", label, val)
        count += 1

# 3. 维度字段
for dim_key, by_version in dims.items():
    for local_vid, field_dict in by_version.items():
        lark_vid = VID_MAP.get(local_vid)
        if not lark_vid:
            continue
        for field_name, val in field_dict.items():
            val = str(val).strip()
            if not val:
                continue
            db.save_override(MODEL_ID, lark_vid, dim_key, field_name, val)
            count += 1

print(f"✓ 写入 {count} 条 override → model_id={MODEL_ID}")
