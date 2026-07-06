#!/usr/bin/env python3
"""
拆解大段文本到正确字段。

问题：飞书中很多字段塞了一大坨文本，同一段话复制到3个字段里。
解决：基于已校验车型的字段关键词规范，智能拆分。
"""
import sys, json, re
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

import db
from vehicle_profile import DIMENSION_DEFS, load_all_tables, build_model_data, fmt_value


# 每个字段的关键词匹配规则（基于已校验车型）
FIELD_KEYWORDS = {
    # seat
    "座椅布局": ["座布局", "2+2+2", "2+3+2", "2+3", "六座", "七座", "五座", "四座"],
    "一排座椅": ["一排", "主驾", "副驾", "驾驶座", "零重力", "加热.*通风.*按摩", "Nappa.*座椅",
                "主座椅", "副座椅", "前排座椅", "头枕", "腿托"],
    "二排座椅": ["二排", "后排.*座椅", "后排.*零重力", "后排.*按摩", "后排.*加热", "伊姆斯",
                "后排.*通风", "后排.*腿托", "后排.*脚托"],
    "三排座椅": ["三排", "第三排"],
    "座椅卖点": ["舒适结构", "骶骨支撑", "全域加热", "零重力座椅.*系统"],
    "遮阳帘/玻璃": ["遮阳帘", "隐私.*玻璃", "调光.*窗", "天幕"],
    "二排其它配置": ["二排.*桌板", "二排.*通道", "后排.*桌板", "后排.*扶手", "行政桌板"],
    "一排其它配置": ["副驾.*屏", "副驾.*娱乐"],
    "二排中岛": ["中岛", "茶台", "磁吸.*茶杯"],
    "方向盘": ["方向盘", "麂皮.*方向", "Alcantara.*方向"],
    "阅读灯/氛围灯": ["氛围灯", "阅读灯"],
    "三排其它配置": ["三排.*杯托", "三排.*Type-C", "三排.*空调"],

    # cockpit
    "座舱系统/芯片": ["座舱.*芯片", "座舱系统", "雪松数字架构", "Sky.*OS", "NOMI", "8295", "8797",
                     "Thor.*芯片", "车机.*芯片"],
    "前排屏": ["中控屏", "仪表.*屏", "副驾.*屏", "OLED.*屏", "AMOLED", "主驾.*屏"],
    "HUD": ["HUD", "抬头显示", "AR-HUD"],
    "后排控制屏": ["后排.*控制屏", "后排.*操控屏"],
    "后排娱乐屏": ["后排.*娱乐屏", "顶棚屏", "天空屏", "mini-LED.*屏", "后排.*液晶"],
    "音响系统": ["音响系统", "沉浸声", "扬声器.*系统", "Naim", "九霄天琴", "天琴"],
    "扬声器数量": ["扬.*[0-9]+", "[0-9]+.*扬声器", "[0-9]+扬"],
    "流媒体后视镜": ["流媒体.*后视镜"],
    "功放功率(W)": ["功放.*[0-9]+W", "[0-9]+W.*功放"],
    "头枕音响": ["头枕.*音响"],
    "杜比认证": ["杜比", "Dolby"],
    "车外麦克风/扬声器": ["车外.*麦克风", "车外.*扬声器"],

    # ad
    "智驾系统/芯片": ["智驾.*芯片", "神玑", "Thor", "Orin", "智驾系统", "辅助驾驶.*芯片",
                     "智驾.*算力"],
    "激光雷达数量/位置": ["激光雷达", "LiDAR"],
    "摄像头数量/位置": ["摄像头", "MP.*摄像头", "环视"],
    "毫米波雷达数量/位置": ["毫米波雷达", "4D.*雷达", "成像雷达"],
    "超声波雷达数量/位置": ["超声波雷达"],
    "智能驾驶能力": ["智驾能力", "辅助驾驶.*功能", "NOA", "NOP", "NGP", "自动驾驶",
                   "城市.*领航", "高速.*领航", "世界模型"],
    "主动安全能力": ["主动安全.*能力", "防碰撞", "CAS", "AEB", "FCW", "LDW"],

    # safety
    "车身结构": ["高强钢", "热成型钢", "车身.*结构", "笼式.*车身", "CTB", "车身.*一体化",
                "防撞梁", "MPa"],
    "安全气囊数量": ["气囊", "气帘", "腔体"],
    "重点气囊": ["远端.*气囊", "中央.*气囊", "膝部.*气囊", "侧气帘"],
    "主动安全": ["防碰撞", "CAS", "AEB", "FCW", "LDW", "盲区", "开门预警", "BSD",
                "TSC", "爆胎.*辅助", "主动安全"],
    "安全带": ["安全带"],
    "AI防护系统": ["AI.*防护", "AI.*安全"],
    "车门解锁冗余": ["车门.*解锁", "冗余.*解锁"],
    "关键材料/工艺": ["高强钢", "热成型", "MPa", "B柱"],

    # chassis
    "前悬架": ["前.*悬架", "前.*连杆"],
    "后悬架": ["后.*悬架", "后.*连杆"],
    "空气悬架": ["空气悬架", "空悬", "双腔"],
    "CDC": ["CDC", "电磁.*减振", "阻尼.*控制"],
    "主动悬架/主动稳定杆": ["主动悬架", "主动稳定杆", "天行.*悬架", "48V.*稳定"],
    "后轮转向": ["后轮转向"],
    "后轮转向角度()": ["后轮.*转向.*度", "后轮.*转向.*°"],
    "转向": ["转向.*系统", "线控转向"],
    "制动": ["制动", "刹车", "定钳", "活塞", "百零.*制动"],
    "百零制动距离(m)": ["百.*零.*制动.*m", "制动.*距离.*[0-9]+m"],
    "转弯半径": ["转弯半径", "最小.*半径"],
    "涉水深度(mm)": ["涉水", "最大离地间隙"],
    "特殊通过能力": ["离地间隙", "接近角", "离去角", "通过.*能力"],
    "底盘材质": ["承载式", "非承载"],
    "拖挂资质": ["拖挂", "拖车钩"],

    # ev
    "能源形式": ["纯电", "增程", "插混", "燃料电池"],
    "电池容量(kWh)": ["电池容量", "kWh.*电池"],
    "CLTC纯电续航(km)": ["CLTC.*续航", "CLTC.*[0-9]+km"],
    "WLTC纯电续航(km)": ["WLTC.*续航", "WLTC.*[0-9]+km"],
    "综合续航(km)": ["综合续航"],
    "最大功率(kW)": ["最大功率", "系统.*功率.*kW"],
    "最大扭矩(Nm)": ["最大扭矩", "扭矩.*N"],
    "零百加速(s)": ["零百", "0-100", "百公里.*加速.*[0-9]" ,"加速.*[0-9]+\\.[0-9]+s"],
    "平台架构": ["平台", "架构", "高压.*平台", "V.*极充"],
    "驱动形式": ["驱动形式", "电机.*驱", "前驱", "后驱", "四驱"],
    "电池体系": ["电池.*体系", "三元锂", "磷酸铁锂", "固态", "骁遥"],
    "动力系统": ["动力系统", "发动机.*kW", "电机.*kW"],

    # comfort
    "一排空间": ["一排.*空间", "主驾.*空间", "副驾.*空间"],
    "二排空间": ["二排.*空间", "后排.*空间", "后排.*腿部", "后排.*头部"],
    "三排空间": ["三排.*空间", "第三排.*空间"],
    "后备箱空间": ["后备箱", "行李舱", "储物.*L"],
    "前备箱容积(L)": ["前备箱", "前备舱", "前行李"],
    "空调": ["空调", "热泵"],
    "冰箱": ["冰箱", "冷暖箱"],
    "NVH": ["NVH", "隔音", "静谧", "ANC"],
    "健康座舱": ["健康座舱", "空气净化"],

    # light
    "头灯": ["大灯", "头灯", "LED.*灯组", "矩阵.*灯", "日行灯", "晶钻"],
    "尾灯": ["尾灯", "贯穿.*尾灯", "光翎"],
    "ADB/DLP大灯": ["ADB", "DLP", "自适应.*远光", "矩阵大灯", "投影大灯"],
    "车门": ["车门.*开启", "开门.*角度", "隐藏.*门把手"],
    "电吸/防夹": ["电吸门", "防夹"],
    "电动开关": ["电动门", "自动门", "感应.*门"],
    "迎宾光毯": ["迎宾.*光毯", "迎宾.*光缦"],
    "电动踏板": ["电动.*踏板", "迎宾.*踏板"],

    # design_ext
    "外观特征": ["外观", "前脸", "格栅", "灯组.*设计", "腰线", "饰条", "X-Bar",
                "蚌式", "游艇", "光帆", "小蓝灯"],
    "车漆颜色": ["配色", "颜色", "极夜黑", "云白", "灰", "红", "蓝", "绿", "银", "金"],
    "内饰颜色": ["内饰.*颜色", "内饰.*配色", "曜夜", "烫金"],
    "内饰材质": ["内饰.*材质", "Nappa", "真皮", "枫影", "Microfiber", "仿麂皮", "Alcantara"],
    "轮毂/轮胎": ["轮毂", "轮圈", "锻造.*轮", "卡钳"],

    # size
    "长(mm)": None,  # 数字专用，不用正则
    "宽(mm)": None,
    "高(mm)": None,
    "轴距(mm)": None,
    "风阻系数Cd": ["风阻", "Cd"],
    "轮胎规格": None,  # 格式数字/数字 R数字
}


def split_blob(text: str, dim_key: str) -> dict:
    """将一坨文本拆解到该维度的正确字段中。"""
    result = {}

    # 找该维度的所有字段
    dim_fields = None
    for d in DIMENSION_DEFS:
        if d["key"] == dim_key:
            dim_fields = d["fields"]
            break
    if not dim_fields:
        return result

    # 分句：按；;。，, 分割
    sentences = [s.strip() for s in re.split(r'[；;。，,]\s*', text) if s.strip()]
    # 过滤太短的
    sentences = [s for s in sentences if len(s) >= 3]

    # 去重（有些blob里重复写了同样的内容）
    seen_sents = set()
    unique_sents = []
    for s in sentences:
        key = s[:20]
        if key not in seen_sents:
            seen_sents.add(key)
            unique_sents.append(s)

    for fn in dim_fields:
        keywords = FIELD_KEYWORDS.get(fn)
        if keywords is None:
            continue

        matched_parts = []
        for sent in unique_sents:
            best_kw = None
            best_len = 0
            for kw in keywords:
                if re.search(kw, sent):
                    if len(kw) > best_len:  # 最长匹配优先
                        best_kw = kw
                        best_len = len(kw)
            if best_kw:
                # 不包含已分配给其他字段的关键词（除非更长匹配）
                assigned_to = None
                for other_fn, other_val in result.items():
                    if sent in other_val:
                        assigned_to = other_fn
                        break
                if not assigned_to:
                    matched_parts.append(sent)

        if matched_parts:
            result[fn] = "；".join(matched_parts)

    return result


def normalize_model(model, dry_run=True):
    """标准化一个车型的数据：拆解blob到正确字段。"""
    name = f"{model['brand']} {model['model_name']}"
    mid = model["id"]
    dims = model.get("dims", {})
    versions = model.get("versions", [])

    changes = []

    for dim_key, by_version in dims.items():
        if not by_version:
            continue

        for vid, fields in by_version.items():
            # 检查是否有同内容重复的字段（表明是复制粘贴的blob）
            field_values = defaultdict(list)
            for fn, fv in fields.items():
                if len(fv) > 80:
                    field_values[fv].append(fn)

            # 找到被复制到多个字段的blob
            blobs = {fv: fns for fv, fns in field_values.items() if len(fns) >= 2}

            for blob_text, source_fns in blobs.items():
                split = split_blob(blob_text, dim_key)
                if not split:
                    continue

                # 只看新拆出的字段
                new_fns = set(split.keys()) - set(source_fns)
                if not new_fns:
                    continue

                for fn, val in split.items():
                    if fn not in new_fns:
                        continue
                    changes.append({
                        "model": name, "mid": mid,
                        "dim": dim_key, "version": vid,
                        "field": fn, "value": val,
                        "source_fields": source_fns,
                        "source_len": len(blob_text),
                    })

    return changes


def main():
    print("加载数据...", file=sys.stderr)
    raw = load_all_tables()
    models = build_model_data(raw)

    all_changes = []
    for m in models:
        if m.get("status") != "正式上市":
            continue
        ov_count = len(db.get_overrides_for_model(m["id"]))
        if ov_count > 50:  # 跳过已大量修改的
            continue
        changes = normalize_model(m)
        all_changes.extend(changes)

    # 去重
    seen = set()
    unique = []
    for c in all_changes:
        key = (c["mid"], c["dim"], c["field"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    print(f"\n发现 {len(unique)} 个可拆解字段 (来自 {len(all_changes)} 个blob)\n")

    if not unique:
        print("未发现需要拆解的blob。")
        return

    # 预览
    for c in unique:
        print(f"  [{c['model']}] {c['dim']}/{c['field']}")
        print(f"    来源: {c['source_fields']} (共{c['source_len']}字)")
        print(f"    拆出: {c['value'][:100]}")
        print()

    # 询问是否写入
    if "--apply" in sys.argv:
        db.init_db()
        written = 0
        for c in unique:
            db.save_override(c["mid"], c["version"], c["dim"], c["field"], c["value"])
            written += 1
        print(f"✓ 已写入 {written} 条新override")
    else:
        print("预览模式。加 --apply 写入。")


if __name__ == "__main__":
    main()
