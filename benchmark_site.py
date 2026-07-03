#!/usr/bin/env python3
"""竞品Benchmark 一体化网站 — 型谱图 + 车型档案 + 多车对比，单 HTML 文件输出。"""
import json
import sys
from pathlib import Path

from spectrum_data import build_chart_rows, split_length_groups
from chart_html import CHART_CSS, build_chart_fragment, _brand_bar_js
from vehicle_profile import (
    DIMENSION_DEFS,
    EXCLUDED_STATUS,
    build_model_data,
    load_all_tables,
    render_profile_fragment,
)

OUT_PATH = Path.home() / "Desktop" / "benchmark_site.html"
EXCLUDE_SORT_CODES = ["0901"]


def build_compare_html(models_data):
    """Generate compare tab content HTML + JS."""
    models_for_compare = [
        {"id": m["id"], "name": m["name"], "brand": m["brand"], "dims": m["dims"]}
        for m in models_data
    ]
    data_json = json.dumps(models_for_compare, ensure_ascii=False, default=str)
    dim_defs_json = json.dumps(
        [[d["key"], d["title"], d["fields"]] for d in DIMENSION_DEFS],
        ensure_ascii=False,
    )
    return f"""<div class="compare-toolbar">
  <div class="compare-slots" id="compare-slots"></div>
  <div class="compare-search-wrap">
    <input type="text" id="compare-search" placeholder="搜索车型…" autocomplete="off">
    <div class="compare-dropdown" id="compare-dropdown"></div>
  </div>
  <label class="diff-toggle"><input type="checkbox" id="diff-only"> 只看差异</label>
</div>
<div class="compare-area" id="compare-area"></div>
<script>
(function(){{
var COMPARE_DATA = {data_json};
var DIM_DEFS = {dim_defs_json};
var MAX_SLOTS = 4;
var selected = [];

var searchEl = document.getElementById("compare-search");
var dropdownEl = document.getElementById("compare-dropdown");
var slotsEl = document.getElementById("compare-slots");
var areaEl = document.getElementById("compare-area");
var diffOnlyEl = document.getElementById("diff-only");

function escHtml(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}}

// ── search ──
searchEl.addEventListener("input", function(){{
  var q = this.value.trim().toLowerCase();
  if(!q){{dropdownEl.innerHTML="";dropdownEl.style.display="none";return}}
  var hits = COMPARE_DATA.filter(function(m){{
    return m.name.toLowerCase().includes(q)||m.brand.toLowerCase().includes(q);
  }}).slice(0,12);
  if(!hits.length){{dropdownEl.innerHTML="<div class='dd-empty'>无匹配</div>";dropdownEl.style.display="block";return}}
  dropdownEl.innerHTML = hits.map(function(m){{
    var already = selected.some(function(s){{return s.id===m.id}});
    return '<div class="dd-item'+(already?" dd-selected":"")+(selected.length>=MAX_SLOTS&&!already?" dd-disabled":"")+'" data-id="'+escHtml(m.id)+'">'
      +'<span class="dd-brand">'+escHtml(m.brand)+'</span>'
      +escHtml(m.name)+'</div>';
  }}).join("");
  dropdownEl.style.display = "block";
}});

dropdownEl.addEventListener("click", function(e){{
  var item = e.target.closest(".dd-item");
  if(!item||item.classList.contains("dd-disabled")) return;
  var id = item.dataset.id;
  if(item.classList.contains("dd-selected")){{
    selected = selected.filter(function(s){{return s.id!==id}});
  }} else if(selected.length < MAX_SLOTS) {{
    var m = COMPARE_DATA.find(function(x){{return x.id===id}});
    if(m) selected.push(m);
  }}
  searchEl.value="";
  dropdownEl.style.display="none";
  renderSlots();
  renderTable();
}});

document.addEventListener("click", function(e){{
  if(!searchEl.contains(e.target)&&!dropdownEl.contains(e.target)) dropdownEl.style.display="none";
}});

// ── slots ──
function renderSlots(){{
  if(!selected.length){{
    slotsEl.innerHTML='<span class="slots-hint">点击上方搜索框添加车型（最多4辆）</span>';
    return;
  }}
  slotsEl.innerHTML = selected.map(function(m,i){{
    return '<div class="slot"><span class="slot-name">'+escHtml(m.name)+'</span>'
      +'<button class="slot-remove" data-idx="'+i+'">×</button></div>';
  }}).join("");
}}

slotsEl.addEventListener("click", function(e){{
  var btn = e.target.closest(".slot-remove");
  if(!btn) return;
  selected.splice(parseInt(btn.dataset.idx),1);
  renderSlots();
  renderTable();
}});

// ── table ──
function getBaseConfig(m, dimKey){{
  var byVersion = (m.dims||{{}})[dimKey]||{{}};
  var firstVersionId = (m.versions&&m.versions[0]) ? m.versions[0].id : null;
  return (firstVersionId&&byVersion[firstVersionId]) || Object.values(byVersion)[0] || {{}};
}}

function renderTable(){{
  if(!selected.length){{
    areaEl.innerHTML='<div class="compare-empty">从上方搜索框选择车型开始对比</div>';
    return;
  }}
  var diffOnly = diffOnlyEl.checked;
  var h = '<table class="compare-table"><thead><tr><th class="field-col">参数</th>';
  selected.forEach(function(m){{
    h += '<th>'+escHtml(m.name)+'</th>';
  }});
  h += '</tr></thead><tbody>';

  DIM_DEFS.forEach(function(dim){{
    var dk=dim[0], dtitle=dim[1], fields=dim[2];
    var configs = selected.map(function(m){{return getBaseConfig(m,dk)}});
    var dimRows = fields.map(function(f){{
      var vals = configs.map(function(c){{return c[f]||""}});
      var allSame = vals.every(function(v){{return v===vals[0]}});
      return {{f:f, vals:vals, allSame:allSame}};
    }}).filter(function(r){{return r.vals.some(function(v){{return v}})}});

    if(!dimRows.length) return;
    if(diffOnly&&dimRows.every(function(r){{return r.allSame}})) return;

    h += '<tr class="dim-header"><td colspan="'+(selected.length+1)+'">'+escHtml(dtitle)+'</td></tr>';
    dimRows.forEach(function(row){{
      if(diffOnly&&row.allSame) return;
      h += '<tr'+(row.allSame?'':' class="diff-row"')+'>';
      h += '<td class="field-col">'+escHtml(row.f)+'</td>';
      row.vals.forEach(function(v){{
        h += '<td'+(row.allSame?'':' class="diff-cell"')+'>'+escHtml(v)+'</td>';
      }});
      h += '</tr>';
    }});
  }});

  h += '</tbody></table>';
  areaEl.innerHTML = h;
}}

diffOnlyEl.addEventListener("change", renderTable);
renderSlots();
renderTable();
}})();
</script>"""


def build_site(raw, models_data):
    """Build the full 3-tab HTML, return the HTML string."""
    # ── Chart tab ──
    rows, warnings = build_chart_rows(raw["models"], raw["prices"], raw["size"])
    rows = split_length_groups(rows)
    rows = [r for r in rows if r["status"] not in EXCLUDED_STATUS]
    rows = [r for r in rows if r.get("sort_code") not in EXCLUDE_SORT_CODES]
    chart_frag = build_chart_fragment(rows, warnings)

    # ── Profile tab ──
    profile_frag = render_profile_fragment(models_data)

    # ── Compare tab ──
    compare_html = build_compare_html(models_data)

    stats = chart_frag["stats"]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>竞品Benchmark</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:#F0F0F0;color:#333;min-height:100vh}}
/* ── nav ── */
.site-nav{{background:#FFF;border-bottom:1px solid #E0E0E0;padding:0 28px;display:flex;align-items:center;gap:0;position:sticky;top:0;z-index:200;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.site-logo{{font-size:15px;font-weight:700;color:#222;padding:14px 20px 14px 0;white-space:nowrap;border-right:1px solid #EEE;margin-right:4px}}
.nav-tab{{padding:14px 20px;font-size:14px;color:#666;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;user-select:none;white-space:nowrap}}
.nav-tab:hover{{color:#333}}
.nav-tab.active{{color:#1A3C6E;border-bottom-color:#1A3C6E;font-weight:600}}
.nav-stats{{margin-left:auto;font-size:12px;color:#AAA}}
/* ── tabs ── */
.tab-panel{{display:none}}.tab-panel.active{{display:block}}
/* ── spectrum tab ── */
.spectrum-wrap{{max-width:1400px;margin:0 auto;padding:20px 20px 40px}}
.spectrum-header{{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px}}
.spectrum-header h2{{font-size:15px;font-weight:bold;color:#333}}
.spectrum-stats{{font-size:12px;color:#888}}.spectrum-stats strong{{color:#555}}
{CHART_CSS}
.chart-footer{{text-align:center;padding:14px 0 4px;font-size:11px;color:#AAA}}
/* ── profile tab ── */
.profile-wrap{{max-width:1200px;margin:0 auto;padding:24px 24px 60px}}
.profile-toolbar{{display:flex;align-items:center;gap:16px;margin-bottom:24px}}
{profile_frag["css"]}
/* ── compare tab ── */
.compare-wrap{{max-width:1400px;margin:0 auto;padding:24px 24px 60px}}
.compare-toolbar{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}}
.compare-slots{{display:flex;gap:8px;flex-wrap:wrap;flex:1;min-width:200px}}
.slot{{display:inline-flex;align-items:center;gap:6px;background:#E8EDF5;border-radius:16px;padding:5px 10px;font-size:13px}}
.slot-name{{color:#1A3C6E;font-weight:500}}
.slot-remove{{background:none;border:none;color:#888;cursor:pointer;font-size:14px;line-height:1;padding:0 2px}}
.slot-remove:hover{{color:#D32F2F}}
.slots-hint{{font-size:13px;color:#AAA}}
.compare-search-wrap{{position:relative}}
#compare-search{{font-size:13px;padding:7px 12px;border:1px solid #D0D0D0;border-radius:8px;background:#F9F9F9;width:200px;font-family:inherit}}
#compare-search:focus{{outline:none;border-color:#888}}
.compare-dropdown{{position:absolute;top:calc(100% + 4px);left:0;width:260px;background:#FFF;border:1px solid #DDD;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.12);z-index:300;max-height:320px;overflow-y:auto;display:none}}
.dd-item{{padding:8px 14px;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:8px}}
.dd-item:hover{{background:#F5F7FA}}
.dd-selected{{background:#F0F4FF}}
.dd-disabled{{opacity:.45;cursor:not-allowed;pointer-events:none}}
.dd-brand{{font-size:11px;color:#888;min-width:36px}}
.dd-empty{{padding:12px 14px;color:#999;font-size:13px}}
.diff-toggle{{display:flex;align-items:center;gap:6px;font-size:13px;color:#555;cursor:pointer;white-space:nowrap}}
.diff-toggle input{{cursor:pointer}}
.compare-area{{overflow-x:auto}}
.compare-table{{width:100%;border-collapse:collapse;font-size:13px;background:#FFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.compare-table th{{background:#F7F7F7;color:#444;font-weight:600;padding:10px 16px;text-align:left;border-bottom:1px solid #E8E8E8;white-space:nowrap}}
.compare-table td{{padding:8px 16px;border-bottom:1px solid #F4F4F4;vertical-align:top;word-break:break-all}}
.compare-table tr:last-child td{{border-bottom:none}}
.dim-header td{{background:#F0F3FA;color:#1A3C6E;font-weight:600;font-size:12px;padding:6px 16px;letter-spacing:.5px}}
.field-col{{color:#888;white-space:nowrap;min-width:120px;font-size:12px}}
.diff-cell{{background:#FFF9C4}}
.compare-empty{{text-align:center;padding:60px 20px;color:#999;font-size:14px}}
/* ── footer ── */
.site-footer{{text-align:center;padding:16px;font-size:11px;color:#CCC}}
</style>
</head>
<body>
<nav class="site-nav">
  <div class="site-logo">竞品Benchmark</div>
  <div class="nav-tab active" data-tab="spectrum">型谱图</div>
  <div class="nav-tab" data-tab="profile">车型档案</div>
  <div class="nav-tab" data-tab="compare">多车对比</div>
  <div class="nav-stats">{stats["models"]} 车型 · {stats["versions"]} 版本 · {stats["brands"]} 品牌</div>
</nav>

<!-- Tab: 型谱图 -->
<div class="tab-panel active" id="tab-spectrum">
  <div class="spectrum-wrap">
    <header class="spectrum-header">
      <h2>竞品品牌型谱对比（含预售车系）</h2>
      <div class="spectrum-stats"><strong>{stats["models"]}</strong> 车型 · <strong>{stats["versions"]}</strong> 版本 · <strong>{stats["brands"]}</strong> 品牌</div>
    </header>
    <div class="brand-bar" id="brand-bar"></div>
    <div class="chart-card">{chart_frag["chart_div"]}</div>
    <div class="chart-footer">点击品牌标签筛选 · 悬停查看版本详情</div>
  </div>
</div>

<!-- Tab: 车型档案 -->
<div class="tab-panel" id="tab-profile">
  <div class="profile-wrap">
    {profile_frag["html"]}
  </div>
</div>

<!-- Tab: 多车对比 -->
<div class="tab-panel" id="tab-compare">
  <div class="compare-wrap">
    {compare_html}
  </div>
</div>

<div class="site-footer">数据来源：竞品Benchmark 飞书多维表格</div>

<script>
// ── Tab navigation ──
var _tabPanels = document.querySelectorAll(".tab-panel");
var _navTabs = document.querySelectorAll(".nav-tab");
function showTab(name){{
  _tabPanels.forEach(function(p){{p.classList.toggle("active", p.id==="tab-"+name)}});
  _navTabs.forEach(function(t){{t.classList.toggle("active", t.dataset.tab===name)}});
  if(history.replaceState) history.replaceState(null,"","#"+name);
}}
_navTabs.forEach(function(t){{t.addEventListener("click",function(){{showTab(t.dataset.tab)}})}});
var _initHash=(location.hash||"").replace("#","");
var _initTab=_initHash.split("/")[0];
if(["spectrum","profile","compare"].includes(_initTab)) showTab(_initTab);

// ── Brand filter (spectrum tab) ──
{_brand_bar_js("brand-bar", "car-chart", chart_frag["brand_data_json"], chart_frag["brand_ann_json"])}

// ── 点击车型名 → 跳转车型档案 ──
(function(){{
  var chartEl = document.getElementById("car-chart");
  if(!chartEl) return;
  chartEl.on("plotly_clickannotation", function(data){{
    var text = (data.annotation.text||"").replace(/<[^>]+>/g,"").replace("（预售）","").trim();
    var sel = document.getElementById("modelSelect");
    for(var i=0; i<PROFILE_DATA.length; i++){{
      if(PROFILE_DATA[i].model_name === text){{
        showTab("profile");
        for(var j=0; j<sel.options.length; j++){{
          var v = sel.options[j].value;
          if(v!=="" && !isNaN(v) && PROFILE_DATA[parseInt(v)].model_name===text){{
            sel.value = v;
            renderProfile(PROFILE_DATA[parseInt(v)]);
            document.getElementById("tab-profile").scrollIntoView({{block:"start"}});
            break;
          }}
        }}
        break;
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""


def main():
    print("加载全部数据表...", file=sys.stderr)
    raw = load_all_tables()

    print("聚合车型数据...", file=sys.stderr)
    models_data = build_model_data(raw)
    print(f"  ✓ {len(models_data)} 款车型", file=sys.stderr)

    print("生成 HTML...", file=sys.stderr)
    html = build_site(raw, models_data)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"输出: {OUT_PATH}", file=sys.stderr)
    total_versions = sum(len(m["versions"]) for m in models_data)
    print(f"合计: {len(models_data)} 款车型, {total_versions} 个版本", file=sys.stderr)


if __name__ == "__main__":
    main()
