#!/usr/bin/env python3
"""
Canonical Schema — 车型配置的统一数据结构定义。

设计原则：
  1. 每个字段 = 一个可独立对比的配置点
  2. 维度 = 消费者看车的自然分组
  3. 字段标注类型，便于跨源匹配和单位转换
"""
from dataclasses import dataclass, field
from typing import Optional

# ── 字段类型 ──────────────────────────────────────────────────────────

@dataclass
class FieldDef:
    key: str                # 规范化字段名 (e.g., "length_mm")
    label: str              # 显示名 (e.g., "长(mm)")
    type: str = "string"    # string | number | enum
    unit: str = ""          # 单位 (e.g., "mm", "kWh", "km")
    description: str = ""   # 字段说明
    examples: list = field(default_factory=list)

# ── 维度定义 ──────────────────────────────────────────────────────────

@dataclass
class DimDef:
    key: str
    title: str
    description: str = ""
    fields: list = field(default_factory=list)


# ── 完整 Schema ───────────────────────────────────────────────────────

CANONICAL_SCHEMA = [
    DimDef("basic", "基础参数", "品牌、车系、年款等基础信息", [
        FieldDef("brand", "品牌", "string"),
        FieldDef("series_name", "车系", "string"),
        FieldDef("generation", "年款", "string"),
        FieldDef("model_type", "车型级别", "string", examples=["大型SUV", "中大型轿车"]),
        FieldDef("status", "上市状态", "string", examples=["正式上市", "预售"]),
        FieldDef("price_range", "价格区间", "string", examples=["46.59-59.99万"]),
    ]),

    DimDef("size", "尺寸与重量", "车身尺寸、重量、风阻", [
        FieldDef("length_mm", "长(mm)", "number", "mm"),
        FieldDef("width_mm", "宽(mm)", "number", "mm"),
        FieldDef("height_mm", "高(mm)", "number", "mm"),
        FieldDef("wheelbase_mm", "轴距(mm)", "number", "mm"),
        FieldDef("curb_weight_kg", "整备质量(kg)", "number", "kg"),
        FieldDef("drag_coefficient", "风阻系数", "number", "Cd"),
        FieldDef("front_track_mm", "前轮距(mm)", "number", "mm"),
        FieldDef("rear_track_mm", "后轮距(mm)", "number", "mm"),
        FieldDef("ground_clearance_mm", "离地间隙(mm)", "number", "mm"),
    ]),

    DimDef("powertrain", "动力与续航", "能源、电池、电机、续航", [
        FieldDef("energy_type", "能源类型", "string", examples=["纯电", "增程", "插混"]),
        FieldDef("battery_capacity_kwh", "电池容量(kWh)", "number", "kWh"),
        FieldDef("battery_type", "电池类型", "string", examples=["三元锂", "磷酸铁锂", "固态"]),
        FieldDef("cltc_range_km", "CLTC续航(km)", "number", "km"),
        FieldDef("wltc_range_km", "WLTC续航(km)", "number", "km"),
        FieldDef("combined_range_km", "综合续航(km)", "number", "km"),
        FieldDef("max_power_kw", "最大功率(kW)", "number", "kW"),
        FieldDef("max_torque_nm", "最大扭矩(Nm)", "number", "Nm"),
        FieldDef("accel_0_100_s", "零百加速(s)", "number", "s"),
        FieldDef("top_speed_kmh", "最高车速(km/h)", "number", "km/h"),
        FieldDef("drive_type", "驱动形式", "string", examples=["双电机四驱", "三电机四驱"]),
        FieldDef("platform", "平台架构", "string"),
        FieldDef("motor_count", "电机数量", "number"),
    ]),

    DimDef("chassis", "底盘与操控", "悬架、制动、转向、轮胎", [
        FieldDef("front_suspension", "前悬架", "string"),
        FieldDef("rear_suspension", "后悬架", "string"),
        FieldDef("air_suspension", "空气悬架", "string"),
        FieldDef("cdc_damper", "CDC可变阻尼", "string"),
        FieldDef("active_stabilizer", "主动稳定杆", "string"),
        FieldDef("rear_wheel_steer_deg", "后轮转向(°)", "number", "°"),
        FieldDef("turning_radius_m", "转弯半径(m)", "number", "m"),
        FieldDef("brake_system", "制动系统", "string"),
        FieldDef("tire_spec", "轮胎规格", "string"),
        FieldDef("wading_depth_mm", "涉水深度(mm)", "number", "mm"),
        FieldDef("chassis_material", "底盘材质", "string"),
        FieldDef("drive_mode_selector", "驾驶模式", "string"),
    ]),

    DimDef("ad", "智能驾驶", "智驾芯片、传感器、智驾能力", [
        FieldDef("ad_chip", "智驾芯片/算力", "string"),
        FieldDef("lidar", "激光雷达", "string"),
        FieldDef("radar_mmwave", "毫米波雷达", "string"),
        FieldDef("radar_ultrasonic", "超声波雷达", "string"),
        FieldDef("cameras", "摄像头", "string"),
        FieldDef("ad_system", "智驾系统", "string"),
        FieldDef("ad_capability", "智驾能力", "string"),
        FieldDef("active_safety", "主动安全", "string"),
    ]),

    DimDef("cockpit", "智能座舱", "座舱芯片、屏幕、音响", [
        FieldDef("cockpit_chip", "座舱芯片", "string"),
        FieldDef("center_screen", "中控屏", "string"),
        FieldDef("instrument_screen", "仪表屏", "string"),
        FieldDef("hud", "HUD", "string"),
        FieldDef("passenger_screen", "副驾屏", "string"),
        FieldDef("rear_screen", "后排屏", "string"),
        FieldDef("rear_control_screen", "后排控制屏", "string"),
        FieldDef("audio_system", "音响系统", "string"),
        FieldDef("speaker_count", "扬声器数量", "number"),
        FieldDef("audio_power_w", "功放功率(W)", "number", "W"),
        FieldDef("dolby_cert", "杜比认证", "string"),
        FieldDef("headrest_speaker", "头枕音响", "string"),
    ]),

    DimDef("seat", "座椅与内饰", "座椅功能、材质、方向盘、遮阳帘", [
        FieldDef("seat_layout", "座椅布局", "string", examples=["2+2+2", "2+3"]),
        FieldDef("row1_seat_material", "一排座椅材质", "string"),
        FieldDef("row1_seat_function", "一排座椅功能", "string"),
        FieldDef("row1_seat_adjust", "一排座椅调节", "string"),
        FieldDef("row2_seat_material", "二排座椅材质", "string"),
        FieldDef("row2_seat_function", "二排座椅功能", "string"),
        FieldDef("row2_seat_adjust", "二排座椅调节", "string"),
        FieldDef("row3_seat_function", "三排座椅功能", "string"),
        FieldDef("steering_wheel", "方向盘", "string"),
        FieldDef("sunshade", "遮阳帘", "string"),
        FieldDef("ambient_light", "氛围灯", "string"),
        FieldDef("seat_highlight", "座椅卖点", "string"),
        FieldDef("row2_console", "二排中岛", "string"),
        FieldDef("row2_table", "二排桌板", "string"),
    ]),

    DimDef("comfort", "空间与舒适", "后备箱、冰箱、空调、NVH", [
        FieldDef("trunk_volume_l", "后备箱容积(L)", "number", "L"),
        FieldDef("frunk_volume_l", "前备箱容积(L)", "number", "L"),
        FieldDef("row1_space", "一排空间", "string"),
        FieldDef("row2_space", "二排空间", "string"),
        FieldDef("row3_space", "三排空间", "string"),
        FieldDef("fridge", "冰箱", "string"),
        FieldDef("ac_system", "空调", "string"),
        FieldDef("nvh", "NVH静谧性", "string"),
        FieldDef("healthy_cabin", "健康座舱", "string"),
    ]),

    DimDef("light", "灯光与车门", "头灯、尾灯、车门形式", [
        FieldDef("headlight", "头灯", "string"),
        FieldDef("taillight", "尾灯", "string"),
        FieldDef("matrix_light", "矩阵/投影大灯", "string"),
        FieldDef("door_type", "车门形式", "string"),
        FieldDef("soft_close", "电吸/电动门", "string"),
        FieldDef("welcome_light", "迎宾光毯", "string"),
        FieldDef("side_step", "电动踏板", "string"),
    ]),

    DimDef("exterior", "外观与颜色", "外观特征、车漆、轮毂", [
        FieldDef("exterior_feature", "外观特征", "string"),
        FieldDef("paint_colors", "车漆颜色", "string"),
        FieldDef("interior_colors", "内饰颜色", "string"),
        FieldDef("interior_material", "内饰材质", "string"),
        FieldDef("wheels", "轮毂", "string"),
    ]),

    DimDef("safety", "安全", "车身结构、气囊、主动安全", [
        FieldDef("body_structure", "车身结构", "string"),
        FieldDef("airbag_count", "气囊数量", "number"),
        FieldDef("airbag_detail", "气囊详情", "string"),
        FieldDef("seatbelt", "安全带", "string"),
        FieldDef("aeb", "AEB/主动安全", "string"),
        FieldDef("door_unlock_redundancy", "车门解锁冗余", "string"),
        FieldDef("battery_safety", "电池安全", "string"),
        FieldDef("key_material", "关键材料/工艺", "string"),
    ]),
]


# ── 辅助函数 ──────────────────────────────────────────────────────────

def get_dim_keys() -> list:
    return [d.key for d in CANONICAL_SCHEMA]

def get_dim_by_key(key: str) -> Optional[DimDef]:
    for d in CANONICAL_SCHEMA:
        if d.key == key:
            return d
    return None

def get_field_keys(dim_key: str) -> list:
    dim = get_dim_by_key(dim_key)
    return [f.key for f in dim.fields] if dim else []

def get_all_field_keys() -> list:
    """返回所有字段的规范化 key 列表。"""
    keys = []
    for d in CANONICAL_SCHEMA:
        for f in d.fields:
            keys.append(f.key)
    return keys

def dims_to_dict() -> dict:
    """{dim_key: [field_keys]}"""
    return {d.key: [f.key for f in d.fields] for d in CANONICAL_SCHEMA}

def dim_labels() -> dict:
    """{dim_key: title}"""
    return {d.key: d.title for d in CANONICAL_SCHEMA}

def field_labels() -> dict:
    """{field_key: label}"""
    result = {}
    for d in CANONICAL_SCHEMA:
        for f in d.fields:
            result[f.key] = f.label
    return result
