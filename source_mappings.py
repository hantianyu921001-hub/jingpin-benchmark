#!/usr/bin/env python3
"""
各数据源字段名 → Canonical Schema 映射规则。

每源一个 dict，key 为源字段名，value 为 canonical field key。
value 为 None 表示跳过不映射。
"""
from canonical_schema import get_all_field_keys

# ── autohome 映射 ─────────────────────────────────────────────────────

AUTOHOME_MAP = {
    # size
    "长度(mm)": "length_mm",
    "宽度(mm)": "width_mm",
    "高度(mm)": "height_mm",
    "轴距(mm)": "wheelbase_mm",
    "前轮距(mm)": "front_track_mm",
    "后轮距(mm)": "rear_track_mm",
    "最小离地间隙(mm)": "ground_clearance_mm",
    "整备质量(kg)": "curb_weight_kg",
    "风阻系数": "drag_coefficient",

    # powertrain
    "能源类型": "energy_type",
    "电池能量(kWh)": "battery_capacity_kwh",
    "电池类型": "battery_type",
    "CLTC纯电续航里程(km)": "cltc_range_km",
    "WLTC纯电续航里程(km)": "wltc_range_km",
    "WLTC综合油耗(L/100km)": None,  # skip
    "综合续航(km)": "combined_range_km",
    "最大功率(kW)": "max_power_kw",
    "最大扭矩(N·m)": "max_torque_nm",
    "最大马力(Ps)": None,
    "官方0-100km/h加速(s)": "accel_0_100_s",
    "最高车速(km/h)": "top_speed_kmh",
    "驱动方式": "drive_type",
    "电动机总功率(kW)": "max_power_kw",
    "电动机总扭矩(N·m)": "max_torque_nm",
    "电动机总马力(Ps)": None,
    "电机布局": None,
    "电机类型": None,
    "驱动电机数": "motor_count",
    "发动机型号": None,
    "发动机": None,
    "变速箱": None,
    "变速箱类型": None,
    "挡位个数": None,
    "排量(L)": None,
    "排量(mL)": None,
    "进气形式": None,
    "气缸排列形式": None,
    "气缸数(个)": None,
    "每缸气门数(个)": None,
    "配气机构": None,
    "最大净功率(kW)": None,
    "供油方式": None,
    "燃油标号": None,
    "缸体材料": None,
    "缸盖材料": None,
    "环保标准": None,
    "简称": None,

    # chassis
    "前悬架类型": "front_suspension",
    "后悬架类型": "rear_suspension",
    "空气悬挂类型": "air_suspension",
    "可变悬架功能": "cdc_damper",
    "前制动器类型": "brake_system",
    "后制动器类型": None,
    "驻车制动类型": None,
    "前轮胎规格": "tire_spec",
    "后轮胎规格": None,
    "驾驶模式切换": "drive_mode_selector",
    "助力类型": None,
    "车体结构": "chassis_material",
    "四驱形式": None,
    "驱动方式": "drive_type",

    # ad
    "辅助驾驶系统": "ad_system",
    "辅助驾驶等级": "ad_capability",
    "辅助驾驶芯片": "ad_chip",
    "辅助驾驶路段": None,
    "巡航系统": "ad_capability",
    "激光雷达数量": "lidar",
    "激光雷达线数": None,
    "毫米波雷达数量": "radar_mmwave",
    "超声波雷达数量": "radar_ultrasonic",
    "摄像头数量": "cameras",
    "前方感知摄像头": None,
    "车内摄像头数量": None,
    "驾驶辅助影像": None,
    "前/后驻车雷达": None,
    "地图品牌": None,

    # cockpit
    "中控彩色屏幕": "center_screen",
    "中控屏幕尺寸": "center_screen",
    "中控屏幕类型": None,
    "中控屏幕分辨率": None,
    "副驾娱乐屏尺寸": "passenger_screen",
    "副驾屏幕类型": None,
    "后排液晶屏幕": "rear_screen",
    "后排液晶屏幕尺寸": "rear_screen",
    "后排液晶屏幕类型": None,
    "后排多媒体屏幕数量": None,
    "扬声器品牌名称": "audio_system",
    "扬声器数量": "speaker_count",
    "手机互联/映射": None,
    "语音识别控制系统": None,
    "4G/5G网络": None,
    "车机智能芯片": "cockpit_chip",
    "车载智能系统": "cockpit_chip",
    "手机APP远程功能": None,
    "手机无线充电功能": None,
    "手机无线充电功率": None,
    "USB/Type-C接口数量": None,
    "USB/Type-C最大充电功率": None,
    "多媒体/充电接口": None,
    "语音分区域唤醒识别": None,
    "语音助手唤醒词": None,
    "车内环境氛围灯": "ambient_light",
    "HUD抬头数字显示": "hud",

    # seat
    "座椅材质": "row1_seat_material",
    "座椅布局": "seat_layout",
    "主座椅调节方式": "row1_seat_adjust",
    "副座椅调节方式": "row1_seat_adjust",
    "前排座椅功能": "row1_seat_function",
    "第二排座椅调节": "row2_seat_adjust",
    "第二排座椅功能": "row2_seat_function",
    "第三排座椅调节": "row3_seat_function",
    "第三排座椅功能": "row3_seat_function",
    "零重力座椅": "seat_highlight",
    "后排座椅放倒形式": None,
    "方向盘材质": "steering_wheel",
    "方向盘位置调节": "steering_wheel",
    "HUD抬头尺寸": "hud",
    "内后视镜功能": None,
    "电动座椅记忆功能": None,
    "换挡形式": None,
    "主/副驾驶座电动调节": None,
    "前/后中央扶手": None,
    "液晶仪表尺寸": "instrument_screen",
    "行车电脑显示屏幕": "instrument_screen",

    # comfort
    "后备厢容积(L)": "trunk_volume_l",
    "空调温度控制方式": "ac_system",
    "后排独立空调": None,
    "后座出风口": None,

    # light
    "近光灯光源": "headlight",
    "远光灯光源": "headlight",
    "灯光特色功能": "matrix_light",
    "天窗类型": "door_type",
    "电动吸合车门": "soft_close",
    "感应雨刷功能": None,
    "前/后电动车窗": None,
    "车窗一键升降功能": None,
    "侧窗多层隔音玻璃": None,
    "车内化妆镜": None,
    "外后视镜功能": None,

    # exterior
    "轮圈材质": "wheels",
    "钥匙类型": None,
    "无钥匙进入功能": None,
    "远程启动功能": None,
    "车侧脚踏板": "side_step",
    "车门开启方式": "door_type",
    "车门数(个)": None,
    "座位数(个)": None,

    # safety
    "主/副驾驶座安全气囊": "airbag_detail",
    "前/后排侧气囊": "airbag_detail",
    "前/后排头部气囊(气帘)": "airbag_detail",
    "胎压监测功能": "aeb",
    "安全带未系提醒": "seatbelt",
    "ABS防抱死": None,
    "制动力分配(EBD/CBC等)": None,
    "刹车辅助(EBA/BAS/BA等)": None,
    "牵引力控制(ASR/TCS/TRC等)": None,
    "车身稳定控制(ESC/ESP/DSC等)": None,
    "主动刹车/主动安全系统": "aeb",
    "车道偏离预警系统": None,
    "疲劳驾驶提示": None,
    "前方碰撞预警": None,

    # extra (autohome specific, not in canonical)
    "电池快充时间(小时)": None,
    "电池快充电量范围(%)": None,
    "快充功能": None,
    "快充接口位置": None,
    "慢充接口位置": None,
    "高压平台（V）": "platform",
    "高压快充": None,
    "百公里耗电量(kWh/100km)": None,
    "电池冷却方式": None,
    "电池特有技术": None,
    "电芯品牌": None,
    "前电动机型号": None,
    "后电动机型号": None,
    "前电动机最大功率(kW)": None,
    "后电动机最大功率(kW)": None,
    "对外交流放电功率(kW)": None,
    "对外直流放电功率(kW)": None,
    "CLTC综合续航(km)": "combined_range_km",
    "三电首任车主质保政策": None,
    "拖挂钩": None,
    "48V主动稳定杆": "active_stabilizer",
    "整车质保": None,
    "上市时间": None,
    "最大满载质量(kg)": None,
    "准拖挂车总质量(kg)": None,
    "最小转弯半径(m)": "turning_radius_m",
    "车身结构": "body_structure",
    "油箱容积(L)": None,
    "接近角(°)": None,
    "离去角(°)": None,
    "油电综合燃料消耗量(L/100km)": None,
    "最低荷电状态油耗(L/100km)WLTC": None,
}

# ── 验证 ──────────────────────────────────────────────────────────────

def validate_mapping():
    """验证所有映射目标都存在于 canonical schema 中。"""
    valid_keys = set(get_all_field_keys())
    issues = []
    for src, target in AUTOHOME_MAP.items():
        if target is not None and target not in valid_keys:
            issues.append(f"  ❌ '{src}' → '{target}' (not in canonical schema)")
    return issues

if __name__ == "__main__":
    issues = validate_mapping()
    if issues:
        print("Mapping issues:")
        for i in issues:
            print(i)
    else:
        mapped = sum(1 for v in AUTOHOME_MAP.values() if v is not None)
        skipped = sum(1 for v in AUTOHOME_MAP.values() if v is None)
        print(f"✓ {len(AUTOHOME_MAP)} entries: {mapped} mapped, {skipped} skipped")
