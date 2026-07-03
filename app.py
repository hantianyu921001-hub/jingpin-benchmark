"""竞品Benchmark Flask 服务器。

用法：
    python3 app.py          # 启动，访问 http://localhost:5000
    python3 app.py --etl    # 先强制刷新数据再启动
"""
import json
import sys
import time
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request

import db
from etl import run_etl

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 最大上传 32MB

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── 刷新按钮 HTML（注入到 </nav> 前）────────────────────────────────────
_REFRESH_UI = """
<style>
.refresh-btn{margin-left:12px;padding:6px 14px;font-size:12px;font-family:inherit;
  background:#1A3C6E;color:#FFF;border:none;border-radius:6px;cursor:pointer;white-space:nowrap}
.refresh-btn:disabled{background:#AAA;cursor:not-allowed}
.refresh-btn:hover:not(:disabled){background:#14305A}
.refresh-tip{margin-left:8px;font-size:11px;color:#AAA}
</style>
<a class="refresh-btn" href="/extract" style="text-decoration:none;display:inline-block;background:#2E7D32">数据录入</a>
<a class="refresh-btn" href="/config" style="text-decoration:none;display:inline-block">配置结构</a>
<button class="refresh-btn" id="refresh-btn" onclick="doRefresh()">刷新数据</button>
<span class="refresh-tip" id="refresh-tip">上次更新：__UPDATED_AT__</span>
<script>
function doRefresh(){
  var btn=document.getElementById('refresh-btn');
  var tip=document.getElementById('refresh-tip');
  btn.disabled=true; btn.textContent='拉取中…';
  tip.textContent='';
  fetch('/api/refresh',{method:'POST'})
    .then(function(r){return r.json()})
    .then(function(d){
      btn.textContent='刷新成功，重载中…';
      setTimeout(function(){location.reload()},800);
    })
    .catch(function(){
      btn.disabled=false; btn.textContent='刷新失败，重试';
    });
}
</script>
"""


def _get_html() -> str:
    """从缓存读 HTML；缓存为空则先跑 ETL。"""
    html, _ = db.get_cache("html")
    if html is None:
        print("缓存为空，首次拉取数据...", file=sys.stderr)
        html = run_etl()
    return html


def _inject_refresh_ui(html: str) -> str:
    """把刷新按钮注入到导航栏末尾。"""
    updated_at = db.cache_updated_at("html") or "未知"
    ui = _REFRESH_UI.replace("__UPDATED_AT__", updated_at)
    return html.replace("</nav>", ui + "</nav>", 1)


# ── 路由 ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    html = _inject_refresh_ui(_get_html())
    return Response(html, mimetype="text/html; charset=utf-8")


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    t0 = time.time()
    run_etl()
    elapsed = round(time.time() - t0, 1)
    models_count, _ = db.get_cache("models_count")
    versions_count, _ = db.get_cache("versions_count")
    return jsonify({
        "ok": True,
        "elapsed_s": elapsed,
        "models": models_count,
        "versions": versions_count,
        "updated_at": db.cache_updated_at("html"),
    })


@app.route("/api/status")
def api_status():
    models_count, _ = db.get_cache("models_count")
    return jsonify({
        "cached": models_count is not None,
        "models": models_count,
        "versions": db.get_cache("versions_count")[0],
        "updated_at": db.cache_updated_at("html"),
        "db_path": str(db.DB_PATH),
    })


@app.route("/api/overrides/<model_id>")
def api_get_overrides(model_id):
    overrides = db.get_overrides_for_model(model_id)
    return jsonify(overrides)


@app.route("/api/save", methods=["PATCH"])
def api_save():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "missing body"}), 400
    model_id = data.get("model_id", "")
    version_id = data.get("version_id", "")
    field_name = data.get("field", "")
    field_value = data.get("value", "")
    dim_key = data.get("dim_key")  # None for version-level fields
    if not version_id or not field_name:
        return jsonify({"error": "missing version_id or field"}), 400
    db.save_override(model_id, version_id, dim_key, field_name, field_value)
    return jsonify({"ok": True})


# ── 维度配置编辑 ──────────────────────────────────────────────────────────

@app.route("/api/config/dims")
def api_config_dims():
    from vehicle_profile import DIMENSION_DEFS
    custom = db.get_all_dim_configs()
    result = [
        {
            "key": d["key"],
            "title": d["title"],
            "default_fields": d["fields"],
            "fields": custom.get(d["key"], d["fields"]),
            "customized": d["key"] in custom,
        }
        for d in DIMENSION_DEFS
    ]
    return jsonify(result)


@app.route("/api/config/dim/<dim_key>", methods=["PUT"])
def api_config_dim_save(dim_key):
    data = request.get_json(force=True)
    fields = data.get("fields")
    if not isinstance(fields, list):
        return jsonify({"error": "fields must be a list"}), 400
    db.set_dim_fields(dim_key, fields)
    return jsonify({"ok": True})


@app.route("/config")
def config_page():
    from vehicle_profile import DIMENSION_DEFS
    dims_json = json.dumps(
        [{"key": d["key"], "title": d["title"], "default_fields": d["fields"]} for d in DIMENSION_DEFS],
        ensure_ascii=False,
    )
    custom_json = json.dumps(db.get_all_dim_configs(), ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>配置结构编辑</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:#F0F0F0;color:#333;min-height:100vh}}
.topbar{{background:#1A3C6E;color:#FFF;padding:0 28px;display:flex;align-items:center;gap:16px;height:52px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.topbar h1{{font-size:15px;font-weight:700;flex:1}}
.btn{{padding:7px 16px;font-size:13px;font-family:inherit;border:none;border-radius:6px;cursor:pointer;white-space:nowrap;transition:all .15s}}
.btn-primary{{background:#FFF;color:#1A3C6E;font-weight:600}}
.btn-primary:hover{{background:#E8EDF5}}
.btn-primary:disabled{{background:#AAA;color:#FFF;cursor:not-allowed}}
.btn-ghost{{background:rgba(255,255,255,.15);color:#FFF}}
.btn-ghost:hover{{background:rgba(255,255,255,.25)}}
.status-msg{{font-size:12px;color:rgba(255,255,255,.7);min-width:120px;text-align:right}}
.wrap{{max-width:1100px;margin:0 auto;padding:28px 24px 60px}}
.page-desc{{font-size:13px;color:#888;margin-bottom:24px;line-height:1.6}}
.dims-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
.dim-card{{background:#FFF;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.dim-card-header{{display:flex;align-items:center;gap:8px;margin-bottom:14px}}
.dim-card-title{{font-size:15px;font-weight:600;color:#1A3C6E}}
.dim-card-key{{font-size:11px;color:#AAA;background:#F0F0F0;padding:2px 8px;border-radius:10px;font-family:monospace}}
.dim-card-badge{{font-size:11px;color:#4CAF50;background:#E8F5E9;padding:2px 8px;border-radius:10px;display:none}}
.dim-card-badge.visible{{display:inline-block}}
.fields-wrap{{display:flex;flex-direction:column;gap:3px;min-height:28px;margin-bottom:12px}}
.field-row{{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;background:#F8F9FC;border:1.5px solid transparent;transition:background .1s}}
.field-row:hover{{background:#EEF1F8}}
.field-row.new-row .field-name{{color:#2E7D32}}
.drag-handle{{cursor:grab;color:#CCC;font-size:16px;line-height:1;user-select:none;flex-shrink:0}}
.drag-handle:active{{cursor:grabbing}}
.field-row.dragging{{opacity:.35;background:#E8EDF5}}
.field-row.drag-over-top{{border-top-color:#1A3C6E}}
.field-row.drag-over-bottom{{border-bottom-color:#1A3C6E}}
.field-name{{flex:1;font-size:13px;color:#333}}
.row-del{{background:none;border:none;color:#CCC;cursor:pointer;font-size:16px;flex-shrink:0;padding:0 2px;line-height:1}}
.row-del:hover{{color:#D32F2F}}
.add-row{{display:flex;gap:8px;margin-top:8px}}
.add-input{{flex:1;font-size:13px;padding:6px 10px;border:1px solid #D8D8D8;border-radius:6px;font-family:inherit;background:#FAFAFA}}
.add-input:focus{{outline:none;border-color:#1A3C6E;background:#FFF}}
.add-btn{{padding:6px 14px;font-size:13px;background:#1A3C6E;color:#FFF;border:none;border-radius:6px;cursor:pointer;white-space:nowrap}}
.add-btn:hover{{background:#14305A}}
.reset-link{{font-size:11px;color:#AAA;cursor:pointer;margin-top:6px;display:inline-block}}
.reset-link:hover{{color:#D32F2F}}
.empty-tip{{font-size:12px;color:#BBB;font-style:italic}}
</style>
</head>
<body>
<div class="topbar">
  <h1>配置结构编辑</h1>
  <span class="status-msg" id="status-msg"></span>
  <a href="/" class="btn btn-ghost" style="text-decoration:none">← 返回档案</a>
  <button class="btn btn-primary" id="apply-btn" onclick="applyChanges()">应用更改并刷新数据</button>
</div>
<div class="wrap">
  <p class="page-desc">管理各维度在车型档案中显示的配置项字段。增删字段后点击「应用更改」重新生成档案数据。<br>
  新增的字段若在飞书表格中存在对应字段名，将自动从数据源拉取；否则可通过档案页内联编辑手动录入。</p>
  <div class="dims-grid" id="dims-grid"></div>
</div>
<script>
var DIM_DEFS = {dims_json};
var CUSTOM = {custom_json};

function setStatus(msg, ok){{
  var el = document.getElementById("status-msg");
  el.textContent = msg;
  el.style.color = ok === false ? "#FFAB40" : "rgba(255,255,255,.7)";
  if(ok === true) setTimeout(function(){{el.textContent=""}}, 2000);
}}

function getFields(key, defaultFields){{
  return CUSTOM[key] ? CUSTOM[key].slice() : defaultFields.slice();
}}

function saveFields(key, fields){{
  return fetch("/api/config/dim/"+encodeURIComponent(key), {{
    method:"PUT", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{fields: fields}})
  }}).then(function(r){{return r.json()}});
}}

function renderCard(dim){{
  var fields = getFields(dim.key, dim.default_fields);
  var isCustom = !!CUSTOM[dim.key];
  var rowsHtml = fields.map(function(f, i){{
    var isNew = !dim.default_fields.includes(f);
    return '<div class="field-row'+(isNew?' new-row':'')+'" draggable="true"'
      +' data-dim-key="'+escAttr(dim.key)+'" data-field="'+escAttr(f)+'" data-drag-idx="'+i+'">'
      +'<span class="drag-handle">⠿</span>'
      +'<span class="field-name">'+escHtml(f)+'</span>'
      +'<button class="row-del" data-dim-key="'+escAttr(dim.key)+'" data-field="'+escAttr(f)+'" title="删除">×</button>'
      +'</div>';
  }}).join('');
  if(!fields.length) rowsHtml = '<div class="empty-tip">暂无字段</div>';
  var resetHtml = isCustom
    ? '<span class="reset-link" data-dim-key="'+escAttr(dim.key)+'" onclick="resetDim(this.dataset.dimKey)">恢复默认</span>'
    : '';
  return '<div class="dim-card" id="card-'+dim.key+'">'
    +'<div class="dim-card-header">'
    +'<span class="dim-card-title">'+escHtml(dim.title)+'</span>'
    +'<span class="dim-card-key">'+escHtml(dim.key)+'</span>'
    +'<span class="dim-card-badge'+(isCustom?' visible':'')+'" id="badge-'+dim.key+'">已自定义</span>'
    +'</div>'
    +'<div class="fields-wrap" id="fields-'+dim.key+'">'+rowsHtml+'</div>'
    +'<div class="add-row">'
    +'<input class="add-input" id="input-'+dim.key+'" data-dim-key="'+escAttr(dim.key)+'" placeholder="输入字段名后按 Enter 或点击添加"'
    +' onkeydown="if(event.keyCode===13)addField(this.dataset.dimKey)">'
    +'<button class="add-btn" data-dim-key="'+escAttr(dim.key)+'" onclick="addField(this.dataset.dimKey)">+ 添加</button>'
    +'</div>'
    +resetHtml
    +'</div>';
}}

function escHtml(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
function escAttr(s){{return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}

function refreshCard(key){{
  var dim = DIM_DEFS.find(function(d){{return d.key===key}});
  var el = document.getElementById("card-"+key);
  el.outerHTML = renderCard(dim);
}}

function addField(key){{
  var inp = document.getElementById("input-"+key);
  var val = inp.value.trim();
  if(!val) return;
  var dim = DIM_DEFS.find(function(d){{return d.key===key}});
  var fields = getFields(key, dim.default_fields);
  if(fields.includes(val)){{ inp.value=""; return; }}
  fields.push(val);
  CUSTOM[key] = fields;
  inp.value = "";
  saveFields(key, fields).then(function(r){{
    if(r.ok){{ setStatus("已保存", true); refreshCard(key); }}
    else setStatus("保存失败", false);
  }});
}}

function removeField(key, field){{
  var dim = DIM_DEFS.find(function(d){{return d.key===key}});
  var fields = getFields(key, dim.default_fields).filter(function(f){{return f!==field}});
  CUSTOM[key] = fields;
  saveFields(key, fields).then(function(r){{
    if(r.ok){{ setStatus("已保存", true); refreshCard(key); }}
    else setStatus("保存失败", false);
  }});
}}

function resetDim(key){{
  if(!confirm("恢复默认后将删除该维度的自定义配置，确定吗？")) return;
  var dim = DIM_DEFS.find(function(d){{return d.key===key}});
  delete CUSTOM[key];
  saveFields(key, dim.default_fields).then(function(r){{
    if(r.ok){{ setStatus("已重置", true); refreshCard(key); }}
  }});
}}

function applyChanges(){{
  var btn = document.getElementById("apply-btn");
  btn.disabled = true; btn.textContent = "刷新中…";
  setStatus("正在重新生成档案数据…");
  fetch("/api/refresh", {{method:"POST"}})
    .then(function(r){{return r.json()}})
    .then(function(d){{
      btn.textContent = "完成，跳转档案页…";
      setStatus("已更新 "+d.models+" 款车型", true);
      setTimeout(function(){{window.location.href="/"}}, 1200);
    }})
    .catch(function(){{
      btn.disabled=false; btn.textContent="应用更改并刷新数据";
      setStatus("刷新失败", false);
    }});
}}

// 初始渲染
var grid = document.getElementById("dims-grid");
DIM_DEFS.forEach(function(dim){{
  var wrapper = document.createElement("div");
  wrapper.innerHTML = renderCard(dim);
  grid.appendChild(wrapper.firstChild);
}});

// ── 事件委托：删除 + 拖拽排序 ────────────────────────────────────────────
// 删除
grid.addEventListener("click",function(e){{
  var btn=e.target.closest(".row-del");
  if(btn) removeField(btn.dataset.dimKey, btn.dataset.field);
}});

// 拖拽状态
var _dKey=null, _dIdx=-1, _dOver=null;

grid.addEventListener("dragstart",function(e){{
  var row=e.target.closest(".field-row[draggable]");
  if(!row) return;
  _dKey=row.dataset.dimKey; _dIdx=parseInt(row.dataset.dragIdx);
  row.classList.add("dragging");
  e.dataTransfer.effectAllowed="move";
}});
grid.addEventListener("dragend",function(e){{
  var row=e.target.closest(".field-row");
  if(row) row.classList.remove("dragging");
  if(_dOver){{_dOver.classList.remove("drag-over-top","drag-over-bottom");_dOver=null;}}
}});
grid.addEventListener("dragover",function(e){{
  var row=e.target.closest(".field-row[draggable]");
  if(!row||row.dataset.dimKey!==_dKey) return;
  e.preventDefault();
  if(_dOver&&_dOver!==row){{_dOver.classList.remove("drag-over-top","drag-over-bottom");}}
  _dOver=row;
  var mid=row.getBoundingClientRect().top+row.getBoundingClientRect().height/2;
  row.classList.toggle("drag-over-top",e.clientY<mid);
  row.classList.toggle("drag-over-bottom",e.clientY>=mid);
}});
grid.addEventListener("drop",function(e){{
  var row=e.target.closest(".field-row[draggable]");
  if(!row||row.dataset.dimKey!==_dKey) return;
  e.preventDefault();
  if(_dOver){{_dOver.classList.remove("drag-over-top","drag-over-bottom");_dOver=null;}}
  var tIdx=parseInt(row.dataset.dragIdx);
  if(tIdx===_dIdx) return;
  var insertAfter=e.clientY>=row.getBoundingClientRect().top+row.getBoundingClientRect().height/2;
  var dim=DIM_DEFS.find(function(d){{return d.key===_dKey}});
  var fields=getFields(_dKey,dim.default_fields);
  var moved=fields.splice(_dIdx,1)[0];
  var adj=tIdx>_dIdx?tIdx-1:tIdx;
  fields.splice(insertAfter?adj+1:adj,0,moved);
  CUSTOM[_dKey]=fields;
  saveFields(_dKey,fields).then(function(r){{
    if(r.ok){{setStatus("已保存",true);refreshCard(_dKey);}}
    else setStatus("保存失败",false);
  }});
}});
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html; charset=utf-8")


# ── 数据提取 API ───────────────────────────────────────────────────────────

@app.route("/api/extract/image", methods=["POST"])
def api_extract_image():
    """上传图片，提取结构化车型数据。"""
    import os

    if "file" not in request.files:
        return jsonify({"error": "请上传图片文件", "field": "file"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    # 保存上传文件
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        return jsonify({"error": f"不支持的图片格式: {ext}"}), 400

    save_path = UPLOAD_DIR / f"upload_{int(time.time())}_{file.filename}"
    file.save(str(save_path))

    try:
        from extractor import extract_from_image, validate_extraction
        result = extract_from_image(str(save_path))
        issues = validate_extraction(result)
        return jsonify({
            "ok": True,
            "data": result,
            "issues": issues,
            "screenshot": str(save_path),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract/url", methods=["POST"])
def api_extract_url():
    """输入 URL，抓取网页截图并提取数据。"""
    data = request.get_json(force=True)
    if not data or not data.get("url"):
        return jsonify({"error": "请提供 URL"}), 400

    url = data["url"].strip()

    try:
        from scraper import scrape_and_extract
        from extractor import validate_extraction
        result = scrape_and_extract(url, cleanup=True)
        issues = validate_extraction(result)
        return jsonify({
            "ok": True,
            "data": result,
            "issues": issues,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract/save", methods=["POST"])
def api_extract_save():
    """将提取并编辑后的数据保存到 SQLite field_overrides。"""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "missing body"}), 400

    extracted = data.get("extracted", {})
    model_id = data.get("model_id", "")

    if not model_id:
        return jsonify({"error": "缺少 model_id"}), 400
    if not extracted:
        return jsonify({"error": "缺少提取数据"}), 400

    count = 0
    VERSION_LABEL_MAP = {
        "核心配置": "summary", "能源": "energy",
        "座位": "seats", "驱动": "drive", "电池容量": "battery",
    }

    # 保存版本级字段
    for v in extracted.get("versions", []):
        version_id = v.get("id", "")
        if not version_id:
            continue
        for label, key in VERSION_LABEL_MAP.items():
            val = str(v.get(key, "") or "").strip()
            if val:
                db.save_override(model_id, version_id, "", label, val)
                count += 1

    # 保存维度字段
    for dim_key, by_version in extracted.get("dims", {}).items():
        for version_id, fields in (by_version or {}).items():
            for field_name, val in fields.items():
                val = str(val).strip()
                if val:
                    db.save_override(model_id, version_id, dim_key, field_name, val)
                    count += 1

    return jsonify({"ok": True, "saved": count})


# ── 数据录入页面 ──────────────────────────────────────────────────────────

@app.route("/extract")
def extract_page():
    from vehicle_profile import DIMENSION_DEFS
    dims_json = json.dumps(
        [{"key": d["key"], "title": d["title"], "fields": d["fields"]} for d in DIMENSION_DEFS],
        ensure_ascii=False,
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据录入 · 竞品Benchmark</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:#F0F0F0;color:#333;min-height:100vh}}
.topbar{{background:#1A3C6E;color:#FFF;padding:0 28px;display:flex;align-items:center;gap:16px;height:52px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.topbar h1{{font-size:15px;font-weight:700;flex:1}}
.btn{{padding:7px 16px;font-size:13px;font-family:inherit;border:none;border-radius:6px;cursor:pointer;white-space:nowrap;transition:all .15s}}
.btn-primary{{background:#FFF;color:#1A3C6E;font-weight:600}}
.btn-primary:hover{{background:#E8EDF5}}
.btn-primary:disabled{{background:#AAA;color:#FFF;cursor:not-allowed}}
.btn-ghost{{background:rgba(255,255,255,.15);color:#FFF}}
.btn-ghost:hover{{background:rgba(255,255,255,.25)}}
.status-msg{{font-size:12px;color:rgba(255,255,255,.7);min-width:200px;text-align:right}}
.wrap{{max-width:1200px;margin:0 auto;padding:28px 24px 60px}}
/* ── 输入区 ── */
.input-section{{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}}
.input-card{{flex:1;min-width:360px;background:#FFF;border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.input-card h2{{font-size:14px;font-weight:600;margin-bottom:16px;color:#1A3C6E}}
.upload-zone{{border:2px dashed #D0D0D0;border-radius:10px;padding:40px 20px;text-align:center;cursor:pointer;transition:border-color .2s;background:#FAFAFA}}
.upload-zone:hover,.upload-zone.drag-over{{border-color:#1A3C6E;background:#F0F4FF}}
.upload-zone p{{font-size:13px;color:#888;margin-bottom:6px}}
.upload-zone .icon{{font-size:40px;color:#CCC;margin-bottom:8px}}
.upload-zone input{{display:none}}
.url-input-wrap{{display:flex;gap:8px}}
.url-input{{flex:1;font-size:13px;padding:10px 14px;border:1px solid #D0D0D0;border-radius:8px;font-family:inherit;background:#FAFAFA}}
.url-input:focus{{outline:none;border-color:#1A3C6E;background:#FFF}}
/* ── 进度 ── */
.progress-wrap{{display:none;margin-bottom:20px;background:#FFF;border-radius:12px;padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.progress-wrap.visible{{display:block}}
.progress-bar{{height:4px;border-radius:2px;background:#E0E0E0;overflow:hidden;margin:12px 0}}
.progress-fill{{height:100%;background:#1A3C6E;transition:width .3s;width:0%}}
.progress-text{{font-size:13px;color:#555}}
/* ── 预览区 ── */
.preview-wrap{{display:none}}
.preview-wrap.visible{{display:block}}
.preview-header{{display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap}}
.preview-header h2{{font-size:14px;font-weight:600;color:#1A3C6E}}
.issues-badge{{font-size:12px;padding:2px 8px;border-radius:10px;background:#FFF3E0;color:#E65100}}
.issues-badge.clean{{background:#E8F5E9;color:#2E7D32}}
.model-input-row{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
.model-input-row input{{font-size:12px;padding:4px 8px;border:1px solid #DDD;border-radius:6px;width:220px;font-family:monospace}}
.model-input-row label{{font-size:12px;color:#888;white-space:nowrap}}
/* ── 版本选择 ── */
.version-tabs{{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid #E8E8E8;padding-bottom:8px}}
.version-tab{{padding:6px 16px;font-size:13px;border:1px solid #E0E0E0;border-radius:8px 8px 0 0;cursor:pointer;background:#F8F8F8;border-bottom:none;transition:all .15s}}
.version-tab:hover{{background:#EEE}}
.version-tab.active{{background:#1A3C6E;color:#FFF;border-color:#1A3C6E}}
/* ── 维度卡片 ── */
.dim-section{{margin-bottom:8px;border:1px solid #E8E8E8;border-radius:10px;overflow:hidden;background:#FFF}}
.dim-toggle{{width:100%;display:flex;align-items:center;gap:8px;padding:12px 16px;background:#FAFBFC;border:none;cursor:pointer;font-family:inherit;font-size:13px;font-weight:600;color:#1A3C6E;text-align:left}}
.dim-toggle:hover{{background:#F0F3FA}}
.dim-toggle .arrow{{transition:transform .2s;font-size:10px}}
.dim-toggle.collapsed .arrow{{transform:rotate(-90deg)}}
.dim-count{{font-size:11px;color:#AAA;font-weight:400;margin-left:4px}}
.dim-body{{padding:4px 16px 16px}}
.dim-toggle.collapsed + .dim-body{{display:none}}
/* ── 字段编辑 ── */
.field-edit-row{{display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid #F8F8F8}}
.field-edit-row:last-child{{border-bottom:none}}
.field-label{{font-size:12px;color:#888;min-width:140px;max-width:160px;padding-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.field-input{{flex:1;font-size:12px;padding:5px 8px;border:1px solid #E0E0E0;border-radius:6px;font-family:inherit;resize:none;min-height:28px;background:#FAFAFA}}
.field-input:focus{{outline:none;border-color:#1A3C6E;background:#FFF}}
.field-input.changed{{background:#FFFDE7;border-color:#FDD835}}
/* ── 确认区 ── */
.confirm-bar{{position:sticky;bottom:0;background:#FFF;border-top:2px solid #1A3C6E;padding:16px 24px;display:flex;align-items:center;gap:16px;margin-top:32px;border-radius:12px 12px 0 0;box-shadow:0 -2px 12px rgba(0,0,0,.1)}}
.confirm-count{{font-size:13px;color:#666;flex:1}}
</style>
</head>
<body>
<div class="topbar">
  <h1>📥 数据录入 · 竞品Benchmark</h1>
  <span class="status-msg" id="status-msg"></span>
  <a href="/" class="btn btn-ghost" style="text-decoration:none">← 返回首页</a>
</div>
<div class="wrap">
  <div class="input-section">
    <div class="input-card">
      <h2>📸 上传参数页截图</h2>
      <div class="upload-zone" id="upload-zone" onclick="document.getElementById('file-input').click()">
        <div class="icon">🖼️</div>
        <p><strong>点击上传</strong> 或拖拽图片到此处</p>
        <p style="font-size:11px;color:#BBB">支持 PNG / JPG / WebP，≤ 32MB</p>
        <input type="file" id="file-input" accept="image/*" onchange="handleFile(this.files[0])">
      </div>
    </div>
    <div class="input-card">
      <h2>🌐 输入参数页 URL</h2>
      <div class="url-input-wrap">
        <input type="text" class="url-input" id="url-input" placeholder="粘贴汽车之家/懂车帝/官网参数页链接...">
        <button class="btn btn-primary" id="url-btn" onclick="handleUrl()">抓取</button>
      </div>
      <p style="font-size:11px;color:#AAA;margin-top:10px">支持: 汽车之家 autohome.com.cn / 懂车帝 dongchedi.com / 鸿蒙智行 hima.auto / 理想官网 lixiang.com</p>
    </div>
  </div>

  <!-- 进度条 -->
  <div class="progress-wrap" id="progress-wrap">
    <div class="progress-text" id="progress-text">处理中...</div>
    <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
  </div>

  <!-- 提取预览 -->
  <div class="preview-wrap" id="preview-wrap">
    <div class="preview-header">
      <h2>📋 提取结果预览</h2>
      <span class="issues-badge" id="issues-badge"></span>
      <div class="model-input-row">
        <label>Model ID:</label>
        <input type="text" id="model-id-input" placeholder="reczkZaU9T7fuB" title="飞书记录 ID，保存时使用">
      </div>
    </div>
    <div class="version-tabs" id="version-tabs"></div>
    <div id="dims-preview"></div>

    <!-- 确认保存 -->
    <div class="confirm-bar" id="confirm-bar">
      <div class="confirm-count" id="confirm-count">共 0 个字段待保存</div>
      <button class="btn btn-primary" id="save-btn" onclick="handleSave()">💾 确认写入 SQLite</button>
      <button class="btn" style="background:#EEE;color:#555" onclick="resetPreview()">清空</button>
    </div>
  </div>
</div>

<script>
var DIM_DEFS = {dims_json};
var extractedData = null;
var currentVersionIdx = 0;

function escHtml(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}

// ── 文件上传 ──
var uploadZone = document.getElementById('upload-zone');
uploadZone.addEventListener('dragover', function(e){{e.preventDefault();uploadZone.classList.add('drag-over')}});
uploadZone.addEventListener('dragleave', function(){{uploadZone.classList.remove('drag-over')}});
uploadZone.addEventListener('drop', function(e){{
  e.preventDefault();uploadZone.classList.remove('drag-over');
  var file = e.dataTransfer.files[0];
  if(file) handleFile(file);
}});

function handleFile(file){{
  if(!file) return;
  showProgress('上传并分析中...');
  var form = new FormData();
  form.append('file', file);
  fetch('/api/extract/image', {{method:'POST', body: form}})
    .then(function(r){{return r.json()}})
    .then(handleExtractResult)
    .catch(function(e){{hideProgress();alert('处理失败: '+e.message)}});
}}

function handleUrl(){{
  var url = document.getElementById('url-input').value.trim();
  if(!url) return;
  var btn = document.getElementById('url-btn');
  btn.disabled = true; btn.textContent = '抓取中...';
  showProgress('正在抓取网页并分析（约20-40秒）...');
  fetch('/api/extract/url', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{url: url}})
  }})
    .then(function(r){{return r.json()}})
    .then(function(d){{
      btn.disabled = false; btn.textContent = '抓取';
      handleExtractResult(d);
    }})
    .catch(function(e){{
      btn.disabled = false; btn.textContent = '抓取';
      hideProgress();alert('抓取失败: '+e.message);
    }});
}}

function showProgress(msg){{
  var wrap = document.getElementById('progress-wrap');
  var text = document.getElementById('progress-text');
  var fill = document.getElementById('progress-fill');
  wrap.classList.add('visible');
  text.textContent = msg;
  fill.style.width = '60%';
}}

function hideProgress(){{
  document.getElementById('progress-wrap').classList.remove('visible');
}}

function handleExtractResult(d){{
  hideProgress();
  if(d.error){{
    alert('提取失败: '+d.error);return;
  }}
  extractedData = d.data;
  currentVersionIdx = 0;

  // 显示问题
  var badge = document.getElementById('issues-badge');
  if(d.issues && d.issues.length){{
    badge.textContent = '⚠ '+d.issues.join(' | ');
    badge.className = 'issues-badge';
  }}else{{
    badge.textContent = '✓ 校验通过';
    badge.className = 'issues-badge clean';
  }}

  // 尝试自动填充 model_id
  var midInput = document.getElementById('model-id-input');
  if(!midInput.value && extractedData.model_name){{
    // 从现有数据查找 model_id
    if(window.PROFILE_DATA){{
      var found = PROFILE_DATA.find(function(m){{
        return m.model_name === extractedData.model_name;
      }});
      if(found) midInput.value = found.id;
    }}
  }}

  renderVersionTabs();
  renderCurrentVersion();

  document.getElementById('preview-wrap').classList.add('visible');
  updateConfirmCount();
}}

// ── 版本 tab ──
function renderVersionTabs(){{
  var versions = extractedData.versions || [];
  var tabsEl = document.getElementById('version-tabs');
  tabsEl.innerHTML = versions.map(function(v,i){{
    return '<div class="version-tab'+(i===currentVersionIdx?' active':'')
      +'" onclick="switchVersion('+i+')">'
      +escHtml(v.version||v.id||'版本'+(i+1))
      +(v.price!==undefined?' · ¥'+v.price+'万':'')
      +'</div>';
  }}).join('');
}}

function switchVersion(idx){{
  currentVersionIdx = idx;
  renderVersionTabs();
  renderCurrentVersion();
}}

// ── 维度字段编辑 ──
function renderCurrentVersion(){{
  var versions = extractedData.versions || [];
  var v = versions[currentVersionIdx];
  if(!v) return;
  var dims = extractedData.dims || {{}};
  var dimsEl = document.getElementById('dims-preview');
  var html = '';

  // 版本基础信息
  html += '<div class="dim-section"><button class="dim-toggle">📌 版本基本信息 <span class="dim-count">('
    +Object.keys(v).filter(function(k){{return k!=='id'&&k!=='summary'&&v[k]}}).length+' 字段)</span>'
    +'<span class="arrow">▼</span></button><div class="dim-body">';
  ['version','grade','energy','drive','seats','battery','price','summary'].forEach(function(key){{
    if(v[key] !== undefined && v[key] !== ''){{
      html += '<div class="field-edit-row">'
        +'<span class="field-label">'+escHtml(key)+'</span>'
        +(key==='summary'
          ? '<textarea class="field-input" data-vid="'+escHtml(v.id)+'" data-dim="" data-field="'+key+'" rows="3">'+escHtml(v[key])+'</textarea>'
          : '<input class="field-input" data-vid="'+escHtml(v.id)+'" data-dim="" data-field="'+key+'" value="'+escHtml(String(v[key]))+'">')
        +'</div>';
    }}
  }});
  html += '</div></div>';

  // 各维度
  DIM_DEFS.forEach(function(dim){{
    var dk = dim.key;
    var byVersion = dims[dk] || {{}};
    var fields = byVersion[v.id] || {{}};
    var fieldKeys = Object.keys(fields).filter(function(k){{return fields[k]!==''}});
    if(!fieldKeys.length) return;

    html += '<div class="dim-section">'
      +'<button class="dim-toggle" onclick="this.classList.toggle('collapsed')">'
      +escHtml(dim.title)+' <span class="dim-count">('+fieldKeys.length+' 字段)</span>'
      +'<span class="arrow">▼</span></button>'
      +'<div class="dim-body">';
    fieldKeys.forEach(function(fk){{
      html += '<div class="field-edit-row">'
        +'<span class="field-label" title="'+escHtml(fk)+'">'+escHtml(fk)+'</span>'
        +'<input class="field-input" data-vid="'+escHtml(v.id)+'" data-dim="'+escHtml(dk)+'" data-field="'+escHtml(fk)+'" value="'+escHtml(String(fields[fk]))+'">'
        +'</div>';
    }});
    html += '</div></div>';
  }});

  dimsEl.innerHTML = html || '<p style="padding:20px;color:#999">未提取到维度配置数据</p>';

  // 监听字段修改
  dimsEl.querySelectorAll('.field-input').forEach(function(el){{
    el.addEventListener('input', function(){{
      this.classList.add('changed');
      updateConfirmCount();
    }});
  }});
}}

function updateConfirmCount(){{
  var count = document.querySelectorAll('.field-input.changed').length;
  document.getElementById('confirm-count').textContent = count
    ? '共 '+count+' 个字段已修改，待保存'
    : '数据无修改';
}}

// ── 保存 ──
function handleSave(){{
  var modelId = document.getElementById('model-id-input').value.trim();
  if(!modelId){{
    alert('请先输入 Model ID（飞书车型记录ID）');
    return;
  }}

  // 收集所有编辑后的值
  var dims = extractedData.dims || {{}};
  document.querySelectorAll('.field-input.changed').forEach(function(el){{
    var vid = el.dataset.vid;
    var dim = el.dataset.dim;
    var field = el.dataset.field;
    var val = el.value;

    if(!dim){{
      // 版本级字段
      var v = (extractedData.versions||[]).find(function(x){{return x.id===vid}});
      if(v) v[field] = val;
    }}else{{
      // 维度字段
      if(!dims[dim]) dims[dim] = {{}};
      if(!dims[dim][vid]) dims[dim][vid] = {{}};
      dims[dim][vid][field] = val;
    }}
  }});

  var btn = document.getElementById('save-btn');
  btn.disabled = true; btn.textContent = '保存中...';
  setStatus('正在写入 SQLite...');

  fetch('/api/extract/save', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{extracted: extractedData, model_id: modelId}})
  }})
    .then(function(r){{return r.json()}})
    .then(function(d){{
      btn.disabled = false; btn.textContent = '💾 确认写入 SQLite';
      if(d.ok){{
        setStatus('✓ 已保存 '+d.saved+' 条字段覆盖', true);
        document.querySelectorAll('.field-input.changed').forEach(function(el){{el.classList.remove('changed')}});
        updateConfirmCount();
        alert('已写入 '+d.saved+' 条配置到 SQLite！

请返回首页点击"刷新数据"查看。');
      }}else{{
        setStatus('保存失败', false);
      }}
    }})
    .catch(function(e){{
      btn.disabled = false; btn.textContent = '💾 确认写入 SQLite';
      setStatus('保存失败: '+e.message, false);
    }});
}}

function resetPreview(){{
  extractedData = null;
  document.getElementById('preview-wrap').classList.remove('visible');
  document.getElementById('issues-badge').textContent = '';
  document.getElementById('version-tabs').innerHTML = '';
  document.getElementById('dims-preview').innerHTML = '';
  document.getElementById('model-id-input').value = '';
}}

function setStatus(msg, ok){{
  var el = document.getElementById('status-msg');
  el.textContent = msg;
  el.style.color = ok===false?'#FFAB40':ok===true?'#A5D6A7':'rgba(255,255,255,.7)';
  if(ok===true) setTimeout(function(){{el.textContent=''}}, 3000);
}}
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html; charset=utf-8")


# ── 本地车型 API ───────────────────────────────────────────────────────

@app.route("/api/local-models")
def api_local_models():
    """列出所有本地车型。"""
    local = db.get_all_local_models()
    return jsonify([{
        "id": m["id"], "name": m.get("name",""), "brand": m.get("brand",""),
        "versions": len(m.get("versions",[])),
    } for m in local])


@app.route("/api/local-model/<model_id>", methods=["GET", "DELETE"])
def api_local_model(model_id):
    if request.method == "GET":
        m = db.get_local_model(model_id)
        return jsonify(m) if m else (jsonify({"error": "not found"}), 404)
    db.delete_local_model(model_id)
    return jsonify({"ok": True})


# ── 同步到飞书 ──────────────────────────────────────────────────────────

@app.route("/api/sync-to-lark/<model_id>", methods=["POST"])
def api_sync_to_lark(model_id):
    """将本地车型的 field_overrides 同步到飞书 Base。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "sync_to_lark.py"), model_id],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return jsonify({"ok": False, "error": result.stderr.strip() or result.stdout.strip()}), 500
    return jsonify({"ok": True, "output": result.stdout.strip()})


# ── 爬取接口 ────────────────────────────────────────────────────────────

@app.route("/api/scrape-car", methods=["POST"])
def api_scrape_car():
    """爬取汽车参数页并提取结构化数据。

    POST body:
        url: 目标网页 URL（汽车之家/懂车帝/鸿蒙智行/理想）
        save_as_local: 是否自动保存为本地车型（默认 false）
        model_id: 保存时的 model_id（可选，默认自动生成）
    """
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()

    import re
    if not url or not re.match(r"^https?://", url):
        return jsonify({"ok": False, "error": "缺少有效的 url 参数"}), 400

    save_as_local = data.get("save_as_local", False)
    model_id = data.get("model_id", "")

    import tempfile, os, traceback
    try:
        # Step 1: 截图
        from scraper import capture_screenshot as _capture
        fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="scrape_")
        os.close(fd)

        cap_path = _capture(url, output_path=screenshot_path)
        if not cap_path or not os.path.exists(cap_path):
            return jsonify({"ok": False, "error": "截图失败"}), 500

        # Step 2: AI 提取
        from extractor import extract_from_image, validate_extraction
        result = extract_from_image(cap_path)

        # 清理截图
        try:
            os.unlink(cap_path)
        except Exception:
            pass

        issues = validate_extraction(result)
        if not result.get("versions"):
            return jsonify({
                "ok": False,
                "error": "未能提取到版本/配置数据",
                "warnings": issues,
                "raw": result,
            }), 422

        # Step 3: 生成本地 model_id → 统一前缀
        brand = (result.get("brand") or "").strip()
        model_name = (result.get("model_name") or "").strip()
        gen = (result.get("generation") or "").strip()

        if not model_id:
            # 生成稳定 ID: local_{brand}_{model_name}_{generation}
            parts = [brand, model_name, gen] if gen else [brand, model_name]
            slug = "_".join(re.sub(r"[^\w一-鿿]", "_", p) for p in parts if p)
            model_id = f"local_{slug}" if slug else f"local_car_{int(time.time())}"

        # 组装完整 model_data
        model_data = {
            "id": model_id,
            "name": f"{brand} {model_name}",
            "model_name": f"{brand} {model_name}",
            "brand": brand,
            "model_type": result.get("model_type", ""),
            "status": "正式上市",
            "generation": gen,
            "price_range": result.get("price_range", ""),
            "sort_code": "",
            "versions": result.get("versions", []),
            "dims": result.get("dims", {}),
        }

        # 补版本 id
        for i, v in enumerate(model_data["versions"]):
            if not v.get("id"):
                v["id"] = f"{model_id}_v{i+1}"

        # Step 4: 保存
        if save_as_local:
            db.save_local_model(model_id, model_data)
            return jsonify({
                "ok": True,
                "model_id": model_id,
                "saved": True,
                "warnings": issues,
                "data": model_data,
            })

        return jsonify({
            "ok": True,
            "model_id": model_id,
            "saved": False,
            "warnings": issues,
            "data": model_data,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 主入口 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()

    if "--etl" in sys.argv:
        print("强制刷新数据...", file=sys.stderr)
        run_etl()

    # 预热缓存（首次启动时）
    html, ts = db.get_cache("html")
    if html is None:
        print("首次启动，拉取数据（约 30-60 秒）...", file=sys.stderr)
        run_etl()
    else:
        updated = db.cache_updated_at("html")
        print(f"已有缓存数据（{updated}），直接启动", file=sys.stderr)

    print("启动服务器：http://localhost:5000", file=sys.stderr)
    app.run(debug=False, port=5000, host="127.0.0.1")
