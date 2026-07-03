#!/usr/bin/env python3
"""视觉提取引擎 — 从参数页截图提取结构化车型配置数据。

支持两种视觉后端：
  1. chat 模式：直接将 base64 图片发给 OpenAI 兼容的视觉模型（如 gpt-4o / qwen-vl-max）
  2. fallback 模式：将图片编码为 data URL，请求任意兼容 API

默认使用环境变量 VISION_API_KEY / VISION_BASE_URL / VISION_MODEL 配置。
如果不配置视觉模型，则直接用 DeepSeek V4 尝试（DeepSeek API 暂不原生支持图片，
但它的 web 端有识图能力 —— 这里我们走 CodeBuddy / 本地桥接）。

输出格式：与 vehicle_profile.DIMENSION_DEFS 对齐的 JSON。
"""
import base64
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

from vehicle_profile import DIMENSION_DEFS

# ── 视觉模型配置 ──────────────────────────────────────────────────────
# 支持以下视觉模型（设置对应的环境变量）：
#   VISION_API_KEY + VISION_BASE_URL + VISION_MODEL（通用配置）
#   OPENAI_API_KEY → gpt-4o / gpt-4o-mini
#   DASHSCOPE_API_KEY → qwen-vl-max / qwen-vl-plus（通义千问）
#   DEEPSEEK_API_KEY → deepseek-v4-pro（需视觉代理或 bridge）


def _load_env_file():
    """尝试从项目根目录 .env 文件加载环境变量。"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env_file()

VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "https://api.deepseek.com")
VISION_MODEL = os.getenv("VISION_MODEL", "")

# 自动检测可用的视觉模型
if not VISION_API_KEY and not VISION_MODEL:
    # 尝试 OpenAI
    if os.getenv("OPENAI_API_KEY"):
        VISION_API_KEY = os.getenv("OPENAI_API_KEY")
        VISION_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
    # 尝试 DashScope（通义千问）
    elif os.getenv("DASHSCOPE_API_KEY"):
        VISION_API_KEY = os.getenv("DASHSCOPE_API_KEY")
        VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        VISION_MODEL = "qwen-vl-max"
    # 尝试 DeepSeek
    elif os.getenv("DEEPSEEK_API_KEY"):
        VISION_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        VISION_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        VISION_MODEL = "deepseek-v4-pro"

if VISION_API_KEY:
    _client = OpenAI(api_key=VISION_API_KEY, base_url=VISION_BASE_URL)
else:
    _client = None

# ── 提取 prompt ──────────────────────────────────────────────────────

def _build_dimension_schema() -> str:
    """生成维度字段 schema 描述，作为 prompt 的一部分。"""
    lines = []
    for dim in DIMENSION_DEFS:
        fields_str = "、".join(dim["fields"])
        lines.append(f"- **{dim['title']}**（key: {dim['key']}）: {fields_str}")
    return "\n".join(lines)


EXTRACTION_SYSTEM_PROMPT = f"""你是一个汽车参数数据提取专家。用户会提供一张汽车参数配置页的截图，你需要从中提取所有可见的配置信息。

## 输出格式
请严格输出以下 JSON 结构（只输出 JSON，不要任何 markdown 标记或解释）：

```json
{{
  "brand": "品牌名（如 理想、问界、极氪）",
  "model_name": "车系名（如 L9、M9、9X）",
  "generation": "年款/代际（如 2026款全新）",
  "price_range": "价格区间（如 40.98-45.98万）",
  "model_type": "车型类型（如 SUV、轿车、MPV）",
  "versions": [
    {{
      "id": "v1",
      "version": "版本名（如 Ultra、Max）",
      "grade": "版本等级",
      "energy": "能源形式（纯电/增程/插混）",
      "drive": "驱动形式（如 双电机四驱）",
      "seats": "座位数",
      "battery": "电池信息",
      "price": 数字价格（万元）,
      "summary": "核心配置摘要"
    }}
  ],
  "dims": {{
    "design_ext": {{ "v1": {{ "外观特征": "...", "车漆颜色": "...", ... }} }},
    "size": {{ "v1": {{ "长(mm)": 数字, "宽(mm)": 数字, "高(mm)": 数字, "轴距(mm)": 数字 }} }},
    "space": {{ "v1": {{ "后备箱空间": "...", ... }} }},
    "seat": {{ "v1": {{ "座椅布局": "...", "一排座椅": "...", ... }} }},
    "nvh": {{ "v1": {{ "冰箱": "...", "空调": "...", ... }} }},
    "light": {{ "v1": {{ "头灯": "...", "车门": "...", ... }} }},
    "ad": {{ "v1": {{ "智驾系统/芯片": "...", "激光雷达数量/位置": "...", ... }} }},
    "cockpit": {{ "v1": {{ "座舱系统/芯片": "...", "前排屏": "...", "音响系统": "...", ... }} }},
    "chassis": {{ "v1": {{ "前悬架": "...", "后悬架": "...", "空气悬架": "...", ... }} }},
    "ev": {{ "v1": {{ "能源形式": "...", "电池容量(kWh)": 数字, "CLTC纯电续航(km)": 数字, ... }} }},
    "safety": {{ "v1": {{ "安全气囊数量": "...", "主动安全": "...", ... }} }}
  }}
}}
```

## 字段提取规则

以下是每个维度的字段列表，请对照截图提取。截图中没有的信息留空字符串或不包含该字段。

{_build_dimension_schema()}

## 重要规则
1. **只提取截图中明确可见的信息**，不要编造或推测
2. 数字字段保持原始格式（如 "5239" 而非 "5239mm"），除非原始数据包含单位
3. 多版本情况下，每个版本一个对象，版本 id 用 v1/v2/v3...
4. 如果某个字段所有版本相同，仍要在每个版本中分别列出
5. 价格单位统一为"万元"
6. 只输出 JSON，前后不要有任何其他文字
"""


# ── 提取函数 ─────────────────────────────────────────────────────────

def encode_image(image_path: str) -> str:
    """将图片文件编码为 base64 data URL。"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    ext = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime = mime_map.get(ext, "image/png")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def extract_from_image(image_path: str) -> dict:
    """从图片文件提取结构化车型数据。

    Args:
        image_path: 图片文件路径

    Returns:
        与 vehicle_profile.build_model_data 输出兼容的 dict，
        包含 brand, model_name, versions, dims 等字段。

    Raises:
        RuntimeError: API 调用失败或解析失败
    """
    print(f"  → 编码图片: {image_path}", file=sys.stderr)
    data_url = encode_image(image_path)

    if _client is None:
        raise RuntimeError(
            "未配置视觉模型 API Key。请设置以下任一环境变量：\n"
            "  - 创建 .env 文件，写入: VISION_API_KEY=你的key\n"
            "  - 或 export OPENAI_API_KEY=sk-xxx（使用 GPT-4V）\n"
            "  - 或 export DASHSCOPE_API_KEY=sk-xxx（使用通义千问 VL）\n"
            "  - 或 export DEEPSEEK_API_KEY=sk-xxx（使用 DeepSeek V4）"
        )

    print(f"  → 调用视觉模型: {VISION_MODEL} @ {VISION_BASE_URL}", file=sys.stderr)
    try:
        response = _client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": "请从这张汽车参数配置截图中提取所有可见的配置信息，严格按照系统提示的 JSON 格式输出。",
                        },
                    ],
                },
            ],
            max_tokens=16384,
            temperature=0.1,
        )
    except Exception as e:
        raise RuntimeError(f"视觉模型 API 调用失败: {e}") from e

    content = response.choices[0].message.content
    print(f"  ✓ 模型返回 {len(content)} 字符", file=sys.stderr)

    # 清理可能的 markdown 包裹
    return _parse_response(content)


def extract_from_images(image_paths: list, merge: bool = True) -> dict:
    """从多张图片提取并合并结果。

    用于参数配置分多页截图的情况（如基础参数页 + 智能驾驶页 + 座舱页）。

    Args:
        image_paths: 图片路径列表
        merge: 是否合并为单一结果（True）还是返回列表（False）

    Returns:
        合并后的 dict 或 dict 列表
    """
    if not merge:
        return [extract_from_image(p) for p in image_paths]

    # 逐张提取，然后合并
    results = []
    for p in image_paths:
        try:
            results.append(extract_from_image(p))
        except Exception as e:
            print(f"  ⚠ 图片 {p} 提取失败: {e}", file=sys.stderr)

    if not results:
        raise RuntimeError("所有图片提取均失败")

    return _merge_extractions(results)


def _parse_response(content: str) -> dict:
    """从模型返回的文本中解析 JSON。"""
    content = content.strip()

    # 移除 markdown 代码块包裹
    if content.startswith("```"):
        # 找到第一个换行，移除 ```json 或 ```
        first_newline = content.find("\n")
        if first_newline > 0:
            content = content[first_newline + 1:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取 JSON 对象
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"无法解析模型返回的 JSON。原始内容前 500 字符:\n{content[:500]}")


def _merge_extractions(results: list[dict]) -> dict:
    """合并多次提取的结果，后者覆盖前者。"""
    if len(results) == 1:
        return results[0]

    merged = dict(results[0])
    for r in results[1:]:
        # 合并基础字段（后者优先）
        for key in ("brand", "model_name", "generation", "price_range", "model_type"):
            if r.get(key) and not merged.get(key):
                merged[key] = r[key]

        # 合并版本
        existing_versions = {v["id"]: v for v in merged.get("versions", [])}
        for v in r.get("versions", []):
            vid = v["id"]
            if vid in existing_versions:
                for k, val in v.items():
                    if val and not existing_versions[vid].get(k):
                        existing_versions[vid][k] = val
            else:
                existing_versions[vid] = v
        merged["versions"] = list(existing_versions.values())

        # 合并维度
        merged_dims = merged.setdefault("dims", {})
        for dk, by_version in r.get("dims", {}).items():
            if dk not in merged_dims:
                merged_dims[dk] = {}
            for vid, fields in by_version.items():
                if vid not in merged_dims[dk]:
                    merged_dims[dk][vid] = {}
                for fk, fv in fields.items():
                    if fv and not merged_dims[dk][vid].get(fk):
                        merged_dims[dk][vid][fk] = fv

    return merged


# ── 结果校验 ─────────────────────────────────────────────────────────

def validate_extraction(data: dict) -> list:
    """校验提取结果，返回问题列表。"""
    issues = []

    if not data.get("brand"):
        issues.append("缺少品牌")
    if not data.get("model_name"):
        issues.append("缺少车系名")
    if not data.get("versions"):
        issues.append("缺少版本信息")
    else:
        for v in data["versions"]:
            if not v.get("version"):
                issues.append(f"版本 {v.get('id', '?')} 缺少版本名")
            if not isinstance(v.get("price"), (int, float)):
                issues.append(f"版本 {v.get('version', v.get('id', '?'))} 缺少价格")

    if not data.get("dims"):
        issues.append("缺少维度配置数据")

    return issues


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <图片路径> [图片路径...]", file=sys.stderr)
        sys.exit(1)

    image_paths = sys.argv[1:]
    try:
        if len(image_paths) == 1:
            result = extract_from_image(image_paths[0])
        else:
            result = extract_from_images(image_paths, merge=True)

        issues = validate_extraction(result)
        if issues:
            print(f"\n⚠ 校验发现 {len(issues)} 个问题:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
