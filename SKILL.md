---
name: 竞品benchmark
description: 飞书 Base「竞品benchmark」的全流程管理：车型数据录入/更新/迁移/校验 + 谱系图生成。适用于配置表写入（00/10-17/20-70）、谱系图刷新、缺失补充等场景。
---

# 竞品 Benchmark

## 范围

管理飞书多维表格 `竞品benchmark`（Base token `E571b0YbQa2MxysVn4RctXcDn7d`）中所有车型数据：

- **数据维护**：新增/刷新/迁移/校验车型配置到 `00/10-17/20-70` 表
- **谱系图**：从 Base 读取车型、价格、车长数据，生成长度-价格散点图

需要调用时自动加载配套 skill：`lark-base`（Base 操作）、`web-access`（联网查源）。

## 数据结构

Base 包含 16 张表，按数字前缀命名：

| 表 | ID 示例 | 用途 |
|---|--------|------|
| `00_车型` | `tbl92hQB5ngDEvRH` | 车型统一 ID、品牌、车系、年款 |
| `10_版本价格` | `tblWDFfm3M3uX9qx` | 版本、价格、能源、座位数 |
| `20_设计` | `tblUAEHLyihXdwXn` | 外观、内饰、车漆 |
| `21_尺寸` | `tblROhrR1M84SZrp` | 车身长度、宽度、高度、轴距 |
| `22_空间` | `tbll00EXYEc4S0hf` | 乘坐空间、后备箱 |
| `23_座椅` | `tblWUYBYTprgY55P` | 座椅布局、功能 |
| `24_NVH` | `tblyyiC7y6r21Ti5` | NVH、空调、健康座舱 |
| `25_灯光` | `tblFxRXeclZexjq6` | 头灯、尾灯、车门 |
| `30_AD` | `tblFLQjKa91NiFKz` | 智能驾驶硬件和功能 |
| `40_座舱` | `tblZv13LhbwJ4l6e` | 座舱系统、屏幕、音响 |
| `50_底盘` | `tblVhYbXA8WQDSkS` | 悬架、转向、制动 |
| `60_三电` | `tbllgpvch11HVnqq` | 电池、续航、充电、动力 |
| `70_安全` | `tblTjuDT2NHD3xGR` | 车身结构、安全气囊、主动安全 |

## 工作流

### 1. 数据维护

1. **确定车型范围**：品牌、车系、年款、版本配置
2. **收集数据**：优先官方页面（hima.auto）、汽车之家、懂车帝
3. **标准化 ID 和拆行**：
   - `00_车型` 一行一个车型/代际
   - `10_版本价格` 按价格/能源/座位数拆行
   - 配置表按参数差异合并，不按营销版本拆分
4. **写入 Base**：使用 `lark-cli base +record-upsert`，串行写入，每条间隔 0.5s
5. **校验**：跑 `verify_vehicle_records.sh` 检查覆盖，配置表超过 3 行需人工对比
6. **数据卫生**：
   - 每项信息只写入最具体的字段，不重复写入
   - 未知字段留空
   - 纯参数值，不加评论或来源标注

### 2. 生成谱系图

首选 HTML 交互版（支持按品牌显隐、悬停查看详情）：

```bash
python3 /Users/hantianyu/.claude/skills/竞品benchmark/chart_html.py
```

输出：`~/Desktop/car_model_chart.html`

选项：
- `--exclude` 指定排除的车型排序码，默认排除 `0901`（尊界S800）
- `--no-exclude` 不排除任何车型
- `--out` 指定输出路径

如需生成 PNG：

```bash
python3 /Users/hantianyu/.claude/skills/竞品benchmark/chart.py
```

输出：`~/Desktop/car_model_chart7.png`

谱系图需数据完整（车型、版本价格、车长、价格均齐全），缺失时按数据维护流程补充。

## 配置表行数规范

20_设计 ~ 70_安全 中，同一 `关联车型` 超过 3 行时必须人工逐行对比合并。超过 3 行本身不是差异的证据。

## 数据源优先级

1. 官方页面（hima.auto 等）
2. 汽车之家 / 懂车帝
3. 工信部公告批次数据
4. 权威媒体原创报道（标注来源）

## 脚本

- `verify_vehicle_records.sh` — 写入后校验车型关联记录覆盖
- `check_model_row_counts.sh` — 检查各表行数
- `chart.py` / `chart_html.py` / `spectrum_data.py` — 谱系图生成（HTML 交互版 / PNG 版）
- `test_spectrum_data.py` — 谱系图数据层验证
