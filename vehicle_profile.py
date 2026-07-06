#!/usr/bin/env python3
"""车型档案页 — 聚合展示单个车型的全维度配置信息。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from spectrum_data import (
    display_brand,
    fetch_table_records,
    first_value,
    link_ids,
    load_live_dataset,
    version_label,
)

LAUNCHED = {"正式上市", "已上市"}
EXCLUDED_STATUS = {"版本取消", "退市", "停售"}
BASE_TOKEN = "E571b0YbQa2MxysVn4RctXcDn7d"

# 品牌排序（与型谱图保持一致）
BRAND_ORDER = [
    "理想", "问界", "智界", "尚界", "启境", "华境",
    "小米", "蔚来", "乐道", "小鹏", "极氪", "智己",
    "岚图", "零跑", "腾势", "方程豹", "比亚迪", "魏牌", "上汽大众",
]

# ── 所有维度的表 ID ──────────────────────────────────────────────────
TABLES = {
    "models": "tbl92hQB5ngDEvRH",
    "prices": "tblWDFfm3M3uX9qx",
    "design": "tblUAEHLyihXdwXn",
    "size": "tblROhrR1M84SZrp",
    "space": "tbll00EXYEc4S0hf",
    "seat": "tblWUYBYTprgY55P",
    "nvh": "tblyyiC7y6r21Ti5",
    "light": "tblFxRXeclZexjq6",
    "ad": "tblFLQjKa91NiFKz",
    "cockpit": "tblZv13LhbwJ4l6e",
    "chassis": "tblVhYbXA8WQDSkS",
    "ev": "tbllgpvch11HVnqq",
    "safety": "tblTjuDT2NHD3xGR",
}

# 每个维度：显示标题、数据表、要展示的字段列表
DIMENSION_DEFS = [
    {
        "key": "size",
        "title": "尺寸",
        "table": "size",
        "fields": ["长(mm)", "宽(mm)", "高(mm)", "轴距(mm)", "风阻系数Cd", "轮胎规格"],
    },
    {
        "key": "ev",
        "title": "三电",
        "table": "ev",
        "fields": [
            "能源形式", "电池容量(kWh)", "CLTC纯电续航(km)", "WLTC纯电续航(km)",
            "综合续航(km)", "最大功率(kW)", "最大扭矩(Nm)",
            "零百加速(s)", "平台架构", "驱动形式", "电池体系", "动力系统",
        ],
    },
    {
        "key": "chassis",
        "title": "底盘",
        "table": "chassis",
        "fields": [
            "前悬架", "后悬架", "空气悬架", "CDC", "主动悬架/主动稳定杆",
            "后轮转向", "后轮转向角度()", "转向", "线控转向", "制动",
            "百零制动距离(m)", "转弯半径", "涉水深度(mm)",
            "底盘材质", "拖挂资质", "特殊通过能力",
        ],
    },
    {
        "key": "ad",
        "title": "智能驾驶",
        "table": "ad",
        "fields": [
            "智驾系统/芯片", "激光雷达数量/位置", "摄像头数量/位置",
            "毫米波雷达数量/位置", "超声波雷达数量/位置",
            "智能驾驶能力", "主动安全能力",
        ],
    },
    {
        "key": "cockpit",
        "title": "智能座舱",
        "table": "cockpit",
        "fields": [
            "座舱系统/芯片", "前排屏", "HUD", "后排控制屏", "后排娱乐屏",
            "音响系统", "音响技术", "音响材质", "扬声器数量",
            "功放功率(W)", "杜比认证", "头枕音响", "车外麦克风/扬声器",
        ],
    },
    {
        "key": "seat",
        "title": "座椅 & 内饰",
        "table": "seat",
        "fields": [
            "座椅布局", "一排座椅", "二排座椅", "三排座椅",
            "一排其它配置", "二排其它配置", "三排其它配置",
            "二排中岛", "座椅卖点", "方向盘",
            "遮阳帘/玻璃", "阅读灯/氛围灯",
        ],
    },
    {
        "key": "comfort",
        "title": "空间 & 舒适",
        "table": None,  # 从 space + nvh 两张表合并
        "fields": [
            "一排空间", "二排空间", "三排空间", "乘坐空间(mm)",
            "车内面积(m)", "前备箱容积(L)", "前备箱开关方式", "后备箱空间",
            "NVH", "空调", "冰箱", "健康座舱",
        ],
        "source_tables": ["space", "nvh"],
    },
    {
        "key": "light",
        "title": "灯光 & 车门",
        "table": "light",
        "fields": [
            "头灯", "尾灯", "ADB/DLP大灯", "迎宾光毯",
            "车门", "电吸/防夹", "电动开关",
        ],
    },
    {
        "key": "design_ext",
        "title": "颜色 & 轮毂",
        "table": "design",
        "fields": ["外观特征", "车漆颜色", "内饰颜色", "内饰材质", "轮毂/轮胎"],
    },
    {
        "key": "safety",
        "title": "安全",
        "table": "safety",
        "fields": [
            "车身结构", "安全气囊数量", "重点气囊", "安全带",
            "主动安全", "主动安全增强", "AI防护系统",
            "车门解锁冗余", "关键材料/工艺",
        ],
    },
]

# ── 数据加载 ──────────────────────────────────────────────────────────


def load_all_tables():
    """按序加载所有表。"""
    result = {}
    for name, table_id in TABLES.items():
        print(f"  → 加载 {name}...", file=sys.stderr)
        result[name] = fetch_table_records(table_id)
    print(f"  ✓ 共加载 {len(result)} 张表", file=sys.stderr)
    return result


def fmt_value(val):
    """将字段值转为字符串，None/空返回空字符串。"""
    if val is None or val == "" or val == []:
        return ""
    if isinstance(val, list):
        parts = [str(v) for v in val if v is not None and str(v).strip()]
        s = "、".join(parts) if parts else ""
    elif isinstance(val, float):
        s = f"{val:.1f}" if val == int(val) else str(val)
        s = s.rstrip("0").rstrip(".") if "." in s else s
    else:
        s = str(val)
    return s.strip()


# ── 数据聚合 ──────────────────────────────────────────────────────────


def build_model_data(raw):
    """将原始表记录聚合成按模型索引的结构。"""
    models = raw["models"]
    prices = raw["prices"]
    models_by_id = {m["_record_id"]: m for m in models if m.get("_record_id")}

    # 按 model_record_id 索引版本
    versions_by_model = defaultdict(list)
    for p in prices:
        for rid in link_ids(p.get("关联车型")):
            if rid in models_by_id:
                versions_by_model[rid].append(p)

    # 按 model_record_id 索引维度表（按表名索引，支持多表合并维度）
    dim_data = {}
    for table_key, table_id in TABLES.items():
        if table_key in ("models", "prices"):
            continue
        by_model = defaultdict(list)
        for rec in raw.get(table_key, []):
            for rid in link_ids(rec.get("关联车型")):
                if rid in models_by_id:
                    by_model[rid].append(rec)
        dim_data[table_key] = by_model

    output = []
    for model_id, m in models_by_id.items():
        model_name = str(m.get("车系") or m.get("车型统一ID", ""))
        brand = display_brand(m.get("品牌"))
        statuses = m.get("上市状态", [])
        status_str = first_value(statuses) if isinstance(statuses, list) else str(statuses or "")
        is_launched = status_str in LAUNCHED
        is_excluded = status_str in EXCLUDED_STATUS
        if is_excluded:
            continue

        display_suffix = "" if is_launched else "（预售）"
        display_name = f"{model_name}{display_suffix}"

        # 版本数据
        model_unified_id = str(m.get("车型统一ID", ""))
        version_rows = []
        for p in versions_by_model[model_id]:
            price_val = p.get("价格(万元)")
            if not isinstance(price_val, (int, float)):
                continue
            cleaned_version = version_label(
                p.get("版本统一ID"),
                model_unified_id,
                p.get("能源"),
                p.get("版本等级"),
            )
            version_rows.append({
                "id": p.get("_record_id"),
                "version": cleaned_version,
                "grade": fmt_value(p.get("版本等级")),
                "energy": first_value(p.get("能源", [])),
                "drive": fmt_value(p.get("驱动")),
                "seats": fmt_value(p.get("座位数")),
                "battery": fmt_value(p.get("电池电量")),
                "price": price_val,
                "baas_price": p.get("BaaS购车价(万元)"),
                "baas_rent": p.get("BaaS月租(元/月)"),
                "summary": fmt_value(p.get("核心配置摘要")),
            })
        version_rows.sort(key=lambda r: r["price"])

        # 维度数据（按版本 rec_id 索引）
        dims = {}
        model_version_ids = {v["id"] for v in version_rows if v.get("id")}
        try:
            import db as _db
            _dim_cfg = _db.get_all_dim_configs()
        except Exception:
            _dim_cfg = {}
        for dim_def in DIMENSION_DEFS:
            dk = dim_def["key"]
            fields_to_use = _dim_cfg.get(dk, dim_def["fields"])
            # 支持多表合并（如 comfort = space + nvh）
            source_tables = dim_def.get("source_tables", [dim_def["table"]]) if dim_def.get("table") is None else [dim_def["table"]]
            by_version = {}
            for src_tbl in source_tables:
                if not src_tbl:
                    continue
                records = dim_data[src_tbl].get(model_id, [])
                for rec in records:
                    # 适用版本 → 关联具体版本；为空则应用到所有版本
                    target_vids = link_ids(rec.get("适用版本"))
                    if not target_vids:
                        target_vids = list(model_version_ids) if model_version_ids else []
                    for vid in target_vids:
                        if vid not in model_version_ids:
                            continue
                        existing = by_version.get(vid, {})
                        for f in fields_to_use:
                            s = fmt_value(rec.get(f))
                            if s:
                                prev = existing.get(f)
                                existing[f] = s if not prev else (prev if prev == s else f"{prev} / {s}")
                        by_version[vid] = existing
            dims[dk] = by_version

        # 合并 field_overrides 到版本数据和维度数据
        try:
            import db as _db
            _VERSION_FIELD_LABEL_MAP = {
                "核心配置": "summary", "能源": "energy",
                "座位": "seats", "驱动": "drive", "电池容量": "battery",
            }
            vr_by_id = {v["id"]: v for v in version_rows if v.get("id")}
            for ov in _db.get_overrides_for_model(model_id):
                vid, dk, fn, fv = ov["version_id"], ov["dim_key"], ov["field_name"], ov["field_value"]
                if not fv:
                    continue
                if dk:
                    # 维度字段覆盖
                    if dk not in dims:
                        dims[dk] = {}
                    dims[dk].setdefault(vid, {})[fn] = fv
                elif vid in vr_by_id and fn in _VERSION_FIELD_LABEL_MAP:
                    # 版本级字段覆盖
                    vr_by_id[vid][_VERSION_FIELD_LABEL_MAP[fn]] = fv
        except Exception:
            pass

        output.append({
            "id": model_id,
            "name": display_name,
            "model_name": model_name,
            "brand": brand,
            "model_type": fmt_value(m.get("类型")),
            "status": status_str,
            "generation": fmt_value(m.get("年款/代际")),
            "price_range": fmt_value(m.get("价格区间")),
            "sort_code": fmt_value(m.get("车型排序码")),
            "versions": version_rows,
            "dims": dims,
            "scraped_fields": {},  # 前端运行时填充
        })

    # ── 合并本地车型（不在飞书中的车型）─────────────────────────────────
    try:
        import db as _db
        for lm in _db.get_all_local_models():
            # 合并 field_overrides 到本地车型维度数据
            try:
                for ov in _db.get_overrides_for_model(lm["id"]):
                    vid, dk, fn, fv = ov["version_id"], ov["dim_key"], ov["field_name"], ov["field_value"]
                    if dk and fn and fv:
                        lm.setdefault("dims", {}).setdefault(dk, {}).setdefault(vid, {})[fn] = fv
                    elif not dk and fn and fv:
                        # 版本级字段：直接覆盖 version 对象
                        for v in lm.get("versions", []):
                            if v.get("id") == vid:
                                if fn == "核心配置":
                                    v["summary"] = fv
                                elif fn == "能源":
                                    v["energy"] = fv
                                elif fn == "座位":
                                    v["seats"] = fv
                                elif fn == "驱动":
                                    v["drive"] = fv
                                elif fn == "电池容量":
                                    v["battery"] = fv
            except Exception:
                pass
            output.append(lm)
    except Exception:
        pass

    # 品牌排序与型谱图一致：BRAND_ORDER → sort_code → name
    def _brand_rank(b: str) -> int:
        try:
            return BRAND_ORDER.index(b)
        except ValueError:
            return len(BRAND_ORDER)

    output.sort(key=lambda x: (_brand_rank(x["brand"] or ""), x["sort_code"] or "", x["name"] or ""))
    return output


# ── HTML 生成 ─────────────────────────────────────────────────────────

_PROFILE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#F0F0F0;color:#333;min-height:100vh}
header{background:#FFF;border-bottom:1px solid #E0E0E0;padding:14px 32px;display:flex;align-items:center;gap:24px;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.06)}
header h1{font-size:17px;font-weight:700;color:#222;white-space:nowrap}
#brandSelect,#modelSelect{font-size:14px;padding:7px 12px;border:1px solid #D0D0D0;border-radius:8px;background:#F9F9F9;cursor:pointer;font-family:inherit}
#brandSelect{{min-width:120px}}#modelSelect{{min-width:200px}}
#brandSelect:focus,#modelSelect:focus{{outline:none;border-color:#888}}
.header-count{font-size:13px;color:#999;margin-left:auto}
.main{max-width:1200px;margin:0 auto;padding:28px 24px 60px}
.model-header{background:#FFF;border-radius:12px;padding:28px 32px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.model-header h2{font-size:26px;font-weight:700;color:#111}
.model-tags{display:flex;gap:10px;margin-top:10px;flex-wrap:wrap}
.tag{font-size:12px;padding:3px 12px;border-radius:20px;background:#F0F0F0;color:#555;font-weight:500}
.tag.brand{background:#E8EDF5;color:#1A3C6E}
.tag.launched{background:#E8F5E9;color:#2E7D32}
.tag.presale{background:#FFF3E0;color:#E65100}
.model-meta{margin-top:12px;font-size:14px;color:#666;display:flex;gap:20px;flex-wrap:wrap}
.model-meta span{display:inline-flex;align-items:center;gap:4px}
.model-meta .label{color:#999}
.section-title{font-size:17px;font-weight:600;color:#222;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section-title .count{font-size:13px;font-weight:400;color:#999}
.table-wrap{background:#FFF;border-radius:12px;padding:4px;overflow-x:auto;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:28px}
.table-wrap table{width:100%;border-collapse:collapse;font-size:13px}
.table-wrap th{background:#F7F7F7;color:#666;font-weight:600;padding:10px 14px;text-align:left;border-bottom:1px solid #E8E8E8;font-size:12px;white-space:nowrap}
.table-wrap td{padding:9px 14px;border-bottom:1px solid #F0F0F0;color:#444;word-break:break-all}
.table-wrap tr:last-child td{border-bottom:none}
.table-wrap tr:hover td{background:#F8FAFF}
.table-wrap .row-label{color:#888;font-size:12px;white-space:nowrap;background:#F7F7F7;font-weight:500;min-width:80px}
.price-col{font-weight:600;color:#D32F2F}
.baas-col{color:#888;font-size:12px}
.summary-col{white-space:normal;word-break:break-all;color:#666;font-size:12px}
.dim-section{margin-bottom:28px}
.dim-section-title{font-size:15px;font-weight:600;color:#1A3C6E;margin-bottom:10px;padding-left:8px;border-left:3px solid #1A3C6E}
.dim-compare-wrap{background:#FFF;border-radius:12px;padding:4px;overflow-x:auto;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.dim-compare-table{width:100%;border-collapse:collapse;font-size:13px}
.dim-compare-table thead th{background:#F7F7F7;color:#555;font-weight:600;padding:10px 14px;text-align:left;border-bottom:2px solid #E8E8E8;white-space:nowrap;font-size:12px}
.dim-compare-table td{padding:8px 14px;border-bottom:1px solid #F4F4F4;color:#444;vertical-align:top;word-break:break-all}
.dim-compare-table tr:last-child td{border-bottom:none}
.dim-compare-table th.field-col,.dim-compare-table td.field-col{position:sticky;left:0;z-index:2;background:#F0F3FA;min-width:110px;color:#555;font-weight:500;white-space:nowrap}
.dim-compare-table thead th.field-col{background:#EAF0FA;z-index:3}
.diff-val{background:#FFF9C4 !important}
.scraped-val{background:#E3F2FD !important}
.diff-val.scraped-val{background:#FFF9C4 !important}
.save-error{background:#FFEBEE !important}
[data-edit]{cursor:pointer;white-space:pre-wrap}
[data-edit]:hover:not(.editing){background:rgba(26,60,110,.05) !important}
.dim-kv-wrap{background:#FFF;border-radius:12px;padding:18px 22px;box-shadow:0 1px 4px rgba(0,0,0,.06);display:grid;grid-template-columns:auto 1fr;gap:4px 20px}
.kv-k{font-size:13px;color:#888;white-space:nowrap;padding:3px 0}
.kv-v{font-size:13px;color:#333;word-break:break-all;padding:3px 0}
.empty-state{text-align:center;padding:60px 20px;color:#999}
.empty-state p{font-size:15px;margin-top:8px}
/* ── 配置分类侧栏 ── */
.profile-layout{display:flex;gap:20px;align-items:flex-start}
.profile-sidebar{position:sticky;top:80px;width:120px;flex-shrink:0;display:flex;flex-direction:column;gap:6px;z-index:10}
.sidebar-pill{display:block;padding:8px 10px;font-size:12px;color:#666;background:#FFF;border-radius:8px;cursor:pointer;text-decoration:none;border:1px solid #EEE;transition:all .15s;user-select:none;white-space:nowrap;text-align:center}
.sidebar-pill:hover{border-color:#1A3C6E;color:#1A3C6E;background:#F0F4FF}
.sidebar-pill.active{background:#1A3C6E;color:#FFF;border-color:#1A3C6E;font-weight:600}
.sidebar-pill .pill-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:#CCC;margin-right:4px;vertical-align:middle}
.sidebar-pill.active .pill-dot{background:#FFF}
.profile-content{flex:1;min-width:0}
"""

_PROFILE_JS = """
function escapeHtml(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
function fmtPrice(p){return p!=null&&p!==undefined?p.toFixed(2)+" 万":""}
function fmtBaas(p,r){var s="";if(p!=null)s+=p.toFixed(2)+" 万";if(r!=null){if(s)s+=" / ";s+=r+" 元/月"}return s||"-"}
function fmtEnergy(e){if(!e)return"";if(e.includes("纯电")&&(e.includes("增程")||e.includes("插混")))return"增程/纯电";if(e.includes("纯电"))return"纯电";if(e.includes("插混"))return"插混";if(e.includes("增程"))return"增程";return e}

var _editModelId=""
function _initEditing(modelId){
  _editModelId=modelId
  var main=document.getElementById("profile-main")
  main.querySelectorAll("[data-edit]").forEach(function(cell){
    cell.addEventListener("click",function(){
      if(cell.querySelector("textarea")) return
      var old=cell.textContent
      var cellH=Math.max(cell.offsetHeight-2, 28)
      cell.classList.add("editing")
      var ta=document.createElement("textarea")
      ta.value=old
      ta.style.cssText="display:block;width:100%;min-height:"+cellH+"px;border:none;outline:2px solid #1A3C6E;background:#FFFDE7;font:inherit;padding:0;margin:0;box-sizing:border-box;resize:vertical;white-space:pre-wrap;word-break:break-all;overflow:hidden"
      cell.textContent=""
      cell.appendChild(ta)
      ta.style.height="auto"
      ta.style.height=Math.max(ta.scrollHeight,cellH)+"px"
      ta.focus()
      ta.setSelectionRange(ta.value.length,ta.value.length)
      ta.addEventListener("input",function(){
        ta.style.height="auto"
        ta.style.height=ta.scrollHeight+"px"
      })
      var cancelled=false
      function commit(){
        if(cancelled) return
        var val=ta.value
        cell.textContent=val
        cell.classList.remove("editing")
        if(val!==old) _saveField(cell,val)
      }
      ta.addEventListener("blur",commit)
      ta.addEventListener("keydown",function(e){
        if(e.key==="Escape"){
          cancelled=true
          cell.textContent=old
          cell.classList.remove("editing")
        }
      })
    })
  })
}
function _saveField(cell,value){
  var body={model_id:_editModelId,version_id:cell.dataset.vid,field:cell.dataset.field,value:value}
  if(cell.dataset.dim) body.dim_key=cell.dataset.dim
  fetch("/api/save",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(function(r){
      cell.classList.remove("save-error")
      if(r.ok){cell.classList.add("edited-val")}else{cell.classList.add("save-error")}
    })
    .catch(function(){cell.classList.add("save-error")})
}
function _loadOverrides(modelId){
  fetch("/api/overrides/"+encodeURIComponent(modelId))
    .then(function(r){return r.json()})
    .then(function(ovs){
      var cells=document.querySelectorAll("[data-edit]")
      ovs.forEach(function(ov){
        cells.forEach(function(cell){
          if(cell.dataset.vid===ov.version_id&&cell.dataset.field===ov.field_name&&(cell.dataset.dim||"")===(ov.dim_key||"")){
            if(!cell.querySelector("textarea")){cell.textContent=ov.field_value;cell.classList.add("edited-val")}
          }
        })
      })
    })
    .catch(function(){})
}

function buildVersionTable(versions){
  if(!versions||!versions.length) return ""
  var ROW_DEFS=[
    {label:"指导价",get:function(v){return fmtPrice(v.price)},cls:"price-col",noDiff:true},
    {label:"能源",get:function(v){return fmtEnergy(v.energy)}},
    {label:"座位",get:function(v){return v.seats||""}},
    {label:"驱动",get:function(v){return v.drive||""}},
    {label:"电池容量",get:function(v){return v.battery||""}},
    {label:"核心配置",get:function(v){return v.summary||""},cls:"summary-col"},
  ]
  var h='<div class="section-title">版本配置 <span class="count">('+versions.length+')</span></div>'
  h+='<div class="table-wrap"><table style="table-layout:fixed;width:100%"><colgroup><col style="width:120px">'
  versions.forEach(function(){h+='<col>'})
  h+='</colgroup><thead><tr><th>配置项</th>'
  versions.forEach(function(v){h+='<th>'+escapeHtml(v.version)+'</th>'})
  h+='</tr></thead><tbody>'
  ROW_DEFS.forEach(function(row){
    var vals=versions.map(row.get)
    var hasAny=vals.some(function(v){return v&&v!=="-"})
    if(!hasAny) return
    var allSame=vals.every(function(v){return v===vals[0]})
    h+='<tr><td class="row-label">'+escapeHtml(row.label)+'</td>'
    vals.forEach(function(v,i){
      var isDiff=!row.noDiff&&!allSame&&v!==vals[0]
      var cls=[row.cls||"",isDiff?"diff-val":""].filter(Boolean).join(" ")
      h+='<td'+(cls?' class="'+cls+'"':'')+' data-edit="version" data-vid="'+escapeHtml(versions[i].id||"")+'" data-field="'+escapeHtml(row.label)+'">'+escapeHtml(v)+'</td>'
    })
    h+='</tr>'
  })
  h+='</tbody></table></div>'
  return h
}

function buildDimSection(dimKey,title,fields,versions,dimByVersion){
  var h='<div class="dim-section" id="dim-'+escapeHtml(dimKey)+'"><div class="dim-section-title">'+escapeHtml(title)+'</div>'
  if(!fields||!fields.length){
    h+='<div class="dim-kv-wrap" style="color:#BBB;font-size:12px;padding:12px 20px">暂无配置项</div></div>'
    return h
  }
  var baseId=versions[0].id
  var baseKv=dimByVersion[baseId]||{}
  h+='<div class="dim-compare-wrap"><table class="dim-compare-table" style="table-layout:fixed;width:100%"><colgroup><col style="width:120px">'
  versions.forEach(function(){h+='<col>'})
  h+='</colgroup><thead><tr>'
  h+='<th class="field-col">参数</th>'
  versions.forEach(function(v){h+='<th>'+escapeHtml(v.version)+'</th>'})
  h+='</tr></thead><tbody>'
  fields.forEach(function(f){
    var vals=versions.map(function(v){return(dimByVersion[v.id]||{})[f]||""})
    var allSame=vals.every(function(v){return v===vals[0]})
    var baseVal=baseKv[f]||""
    var isScraped=PROFILE_SCRAPED[dimKey]&&PROFILE_SCRAPED[dimKey].indexOf(f)>=0
    h+='<tr><td class="field-col">'+escapeHtml(f)+'</td>'
    vals.forEach(function(v,i){
      var isDiff=!allSame&&v!==baseVal&&versions[i].id!==baseId
      var cls=[isDiff?"diff-val":"",isScraped?"scraped-val":""].filter(Boolean).join(" ")
      h+='<td'+(cls?' class="'+cls+'"':'')+' data-edit="dim" data-vid="'+escapeHtml(versions[i].id||"")+'" data-dim="'+escapeHtml(dimKey)+'" data-field="'+escapeHtml(f)+'">'+escapeHtml(v)+'</td>'
    })
    h+='</tr>'
  })
  h+='</tbody></table></div>'
  h+='</div>'
  return h
}

function renderProfile(m){if(!m)return
  var main=document.getElementById("profile-main")
  // 侧栏
  var sidebar='<div class="profile-sidebar">'
  for(var i=0;i<PROFILE_DIM_DEFS.length;i++){
    sidebar+='<a class="sidebar-pill" href="#dim-'+escapeHtml(PROFILE_DIM_DEFS[i][0])+'" data-dim-key="'+escapeHtml(PROFILE_DIM_DEFS[i][0])+'">'+escapeHtml(PROFILE_DIM_DEFS[i][1])+'</a>'
  }
  sidebar+='</div>'
  // 主体
  var body='<div class="model-header">'
  body+='<h2>'+escapeHtml(m.name)+'</h2>'
  body+='<div class="model-tags">'
  body+='<span class="tag brand">'+escapeHtml(m.brand)+'</span>'
  if(m.model_type)body+='<span class="tag">'+escapeHtml(m.model_type)+'</span>'
  var statusClass=(m.status==="正式上市"||m.status==="已上市")?"launched":"presale"
  body+='<span class="tag '+statusClass+'">'+escapeHtml(m.status)+'</span>'
  body+='</div>'
  body+='<div class="model-meta">'
  if(m.generation)body+='<span><span class="label">年款</span>'+escapeHtml(m.generation)+'</span>'
  if(m.price_range)body+='<span><span class="label">价格区间</span>'+escapeHtml(m.price_range)+'</span>'
  body+='<span><span class="label">版本</span>'+m.versions.length+' 个</span>'
  body+='</div></div>'
  body+=buildVersionTable(m.versions)
  var dimData=m.dims||{}
  for(var i=0;i<PROFILE_DIM_DEFS.length;i++){
    var d=PROFILE_DIM_DEFS[i]
    body+=buildDimSection(d[0],d[1],d[2],m.versions,(dimData[d[0]]||{}))
  }
  main.innerHTML='<div class="profile-layout">'+sidebar+'<div class="profile-content">'+body+'</div></div>'
  _initEditing(m.id)
  _loadOverrides(m.id)
  // 滚动监听：更新侧栏激活项
  _initScrollSpy()
  if(history.replaceState) history.replaceState(null,"","#profile/"+encodeURIComponent(m.id))
}

function scrollToDim(dimKey, e){
  e&&e.preventDefault()
  var el=document.getElementById("dim-"+dimKey)
  if(el) el.scrollIntoView({behavior:"smooth",block:"start"})
}

function _initScrollSpy(){
  var sidebar=document.querySelector(".profile-sidebar")
  var pills=document.querySelectorAll(".sidebar-pill")
  // 点击事件委托
  if(sidebar){
    sidebar.addEventListener("click",function(e){
      var pill=e.target.closest(".sidebar-pill")
      if(!pill) return
      e.preventDefault()
      var dimKey=pill.getAttribute("data-dim-key")
      if(dimKey){
        var el=document.getElementById("dim-"+dimKey)
        if(el) el.scrollIntoView({behavior:"smooth",block:"start"})
      }
    })
  }
  var sections=[]
  pills.forEach(function(p){
    var dimKey=p.getAttribute("data-dim-key")
    if(dimKey){
      var el=document.getElementById("dim-"+dimKey)
      if(el) sections.push({el:el, pill:p})
    }
  })
  if(!sections.length) return
  function update(){
    var scrollY=window.scrollY+100
    var active=null
    for(var i=0;i<sections.length;i++){
      if(sections[i].el.offsetTop<=scrollY) active=sections[i]
    }
    pills.forEach(function(p){p.classList.remove("active")})
    if(active) active.pill.classList.add("active")
  }
  window.addEventListener("scroll",update,{passive:true})
  update()
}
"""


def render_profile_fragment(models_data):
    """Return dict with css, js, html for embedding in combined site."""
    # 读取 SQLite 中的维度字段覆盖配置
    try:
        import db as _db
        _dim_cfg = _db.get_all_dim_configs()
    except Exception:
        _dim_cfg = {}

    data_json = json.dumps(models_data, ensure_ascii=False, default=str)
    effective_defs = [
        [d["key"], d["title"], _dim_cfg.get(d["key"], d["fields"])]
        for d in DIMENSION_DEFS
    ]
    dim_defs_json = json.dumps(effective_defs, ensure_ascii=False)

    # 读取爬取字段清单
    scraped_json = "{}"
    sf_path = Path(__file__).parent / "scraped_fields.json"
    if sf_path.exists():
        scraped_json = sf_path.read_text(encoding="utf-8")

    html = f"""<div class="profile-toolbar">
  <select id="brandSelect"></select>
  <select id="modelSelect"></select>
  <span class="header-count" id="modelCount"></span>
</div>
<div id="profile-main"></div>
<script>
var PROFILE_SCRAPED = {scraped_json};
var PROFILE_DATA = {data_json};
var PROFILE_DIM_DEFS = {dim_defs_json};
{_PROFILE_JS}
(function(){{
  var brandSel=document.getElementById("brandSelect")
  var modelSel=document.getElementById("modelSelect")
  // 品牌→车型索引映射
  var brandList=[]
  var modelsByBrand={{}}
  PROFILE_DATA.forEach(function(m,i){{
    if(!modelsByBrand[m.brand]){{brandList.push(m.brand);modelsByBrand[m.brand]=[]}}
    modelsByBrand[m.brand].push({{idx:i,name:m.name,id:m.id}})
  }})
  // 填充品牌下拉
  brandList.forEach(function(b){{
    var opt=document.createElement("option");opt.value=b;opt.textContent=b+" ("+modelsByBrand[b].length+")"
    brandSel.appendChild(opt)
  }})
  // 品牌切换时刷新车型下拉
  function fillModels(brand){{
    modelSel.innerHTML=""
    var list=modelsByBrand[brand]||[]
    list.forEach(function(m){{
      var opt=document.createElement("option");opt.value=m.idx;opt.textContent=m.name
      modelSel.appendChild(opt)
    }})
  }}
  brandSel.addEventListener("change",function(){{
    fillModels(this.value)
    renderProfile(PROFILE_DATA[parseInt(modelSel.value)])
  }})
  modelSel.addEventListener("change",function(){{
    renderProfile(PROFILE_DATA[parseInt(this.value)])
  }})
  document.getElementById("modelCount").textContent="共 "+PROFILE_DATA.length+" 款车型"
  var _hashModelId=(function(){{var m=(location.hash||"").match(/^#profile\/(.+)$/);return m?decodeURIComponent(m[1]):null}})()
  var _initIdx=0
  var _initBrand=brandList[0]
  if(_hashModelId){{for(var _i=0;_i<PROFILE_DATA.length;_i++){{if(PROFILE_DATA[_i].id===_hashModelId){{_initIdx=_i;_initBrand=PROFILE_DATA[_i].brand;break}}}}}}
  brandSel.value=_initBrand
  fillModels(_initBrand)
  if(_initIdx) modelSel.value=_initIdx
  renderProfile(PROFILE_DATA[parseInt(modelSel.value)])
}})()
</script>"""

    return {"css": _PROFILE_CSS, "html": html}


def gen_html(models_data, model_count, price_count):
    frag = render_profile_fragment(models_data)
    system_info = f"数据来源：竞品Benchmark 飞书多维表格 · {model_count} 款车型 / {price_count} 个版本"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>竞品Benchmark · 车型档案</title>
<style>
{frag["css"]}
.page-wrap{{max-width:1200px;margin:0 auto;padding:24px 24px 60px}}
.page-title{{font-size:17px;font-weight:700;color:#222;margin-bottom:16px}}
.profile-toolbar{{display:flex;align-items:center;gap:16px;margin-bottom:24px}}
footer{{text-align:center;padding:20px;font-size:12px;color:#BBB;margin-top:40px}}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="page-title">📋 车型档案</div>
  {frag["html"]}
</div>
<footer>{system_info}</footer>
</body>
</html>"""


# ── 主入口 ────────────────────────────────────────────────────────────


def main():
    out_path = Path.home() / "Desktop" / "vehicle_profile.html"

    print("加载全部数据表...", file=sys.stderr)
    raw = load_all_tables()

    print("聚合车型数据...", file=sys.stderr)
    models_data = build_model_data(raw)
    print(f"  ✓ {len(models_data)} 款车型", file=sys.stderr)

    print("生成 HTML...", file=sys.stderr)
    html = gen_html(models_data, len(raw["models"]), len(raw["prices"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"输出: {out_path}", file=sys.stderr)

    # 统计
    total_versions = sum(len(m["versions"]) for m in models_data)
    total_dim = sum(
        1 for m in models_data for dk in m["dims"] if m["dims"][dk]
    )
    print(f"合计: {len(models_data)} 款车型, {total_versions} 个版本, {total_dim} 个维度卡片", file=sys.stderr)


if __name__ == "__main__":
    main()
