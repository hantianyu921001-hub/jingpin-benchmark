#!/usr/bin/env python3
import unittest

from chart import (
    header_key_for_name,
    model_axis_positions,
    model_name_pairs,
    shifted_header_x,
    spine_points_by_axis,
)
from spectrum_data import (
    build_chart_rows,
    chart_positions,
    offset_transformed_length,
    payload_to_records,
    split_length_groups,
    length_ticks,
    transform_length,
    version_label,
)


class SpectrumDataTest(unittest.TestCase):
    def test_payload_to_records_uses_field_names_not_positions(self):
        payload = {
            "data": {
                "fields": ["品牌", "车型统一ID"],
                "record_id_list": ["model-1"],
                "data": [[["理想"], "理想_L9_2026款全新"]],
            }
        }

        self.assertEqual(
            payload_to_records(payload),
            [{
                "_record_id": "model-1",
                "品牌": ["理想"],
                "车型统一ID": "理想_L9_2026款全新",
            }],
        )

    def test_build_chart_rows_uses_version_specific_length(self):
        models = [{
            "_record_id": "model-1",
            "车型统一ID": "鸿蒙智行-问界_M9_2026款全新",
            "车系": "问界M9",
            "品牌": ["鸿蒙智行-问界"],
            "上市状态": ["正式上市"],
            "年款/代际": "2026款全新",
            "车型排序码": "1001",
        }]
        prices = [
            {
                "_record_id": "version-standard",
                "版本统一ID": "鸿蒙智行-问界_M9_2026款全新_Max+_增程_阔五座",
                "关联车型": [{"id": "model-1"}],
                "价格(万元)": 47.98,
                "能源": ["增程"],
            },
            {
                "_record_id": "version-long",
                "版本统一ID": "鸿蒙智行-问界_M9_2026款全新_Ultimate领世加长版_增程_阔五座",
                "关联车型": [{"id": "model-1"}],
                "价格(万元)": 64.98,
                "能源": ["增程"],
            },
        ]
        designs = [
            {
                "关联车型": [{"id": "model-1"}],
                "适用版本": [{"id": "version-standard"}],
                "长(mm)": 5285,
            },
            {
                "关联车型": [{"id": "model-1"}],
                "适用版本": [{"id": "version-long"}],
                "长(mm)": 5402,
            },
        ]

        rows, warnings = build_chart_rows(models, prices, designs)

        self.assertEqual([], warnings)
        self.assertEqual(
            [("Max+ 阔五座", 5285),
             ("Ultimate领世加长版 阔五座", 5402)],
            [(row["version"], row["length"]) for row in rows],
        )

    def test_build_chart_rows_falls_back_to_common_model_length(self):
        models = [{
            "_record_id": "model-1",
            "车型统一ID": "理想_MEGA_2025款",
            "车系": "理想MEGA",
            "品牌": ["理想"],
            "上市状态": ["正式上市"],
            "年款/代际": "2025款",
        }]
        prices = [{
            "_record_id": "version-1",
            "版本统一ID": "理想_MEGA_2025款_Ultra",
            "关联车型": [{"id": "model-1"}],
            "价格(万元)": 52.98,
            "能源": ["纯电"],
        }]
        designs = [{
            "关联车型": [{"id": "model-1"}],
            "适用版本": [],
            "长(mm)": 5350,
        }]

        rows, warnings = build_chart_rows(models, prices, designs)

        self.assertEqual([], warnings)
        self.assertEqual(5350, rows[0]["length"])

    def test_split_length_groups_separates_same_model_with_two_lengths(self):
        rows = [
            {
                "model_key": "鸿蒙智行-问界_M9_2026款全新",
                "model_name": "问界M9",
                "length": 5285,
            },
            {
                "model_key": "鸿蒙智行-问界_M9_2026款全新",
                "model_name": "问界M9",
                "length": 5402,
            },
        ]

        groups = split_length_groups(rows)

        self.assertEqual(
            [
                ("鸿蒙智行-问界_M9_2026款全新::5285", "问界M9"),
                ("鸿蒙智行-问界_M9_2026款全新::5402", "问界M9"),
            ],
            [(row["model_key"], row["model_name"]) for row in groups],
        )

    def test_split_length_groups_keeps_single_length_model_key(self):
        rows = [{
            "model_key": "理想_MEGA_2025款",
            "model_name": "理想MEGA",
            "length": 5350,
        }]

        groups = split_length_groups(rows)

        self.assertEqual("理想_MEGA_2025款", groups[0]["model_key"])
        self.assertEqual("理想MEGA", groups[0]["model_name"])

    def test_transform_length_expands_dense_large_vehicle_range(self):
        self.assertEqual(5200, transform_length(5200))
        self.assertEqual(5400, transform_length(5300))
        self.assertEqual(5600, transform_length(5400))
        self.assertEqual(5000, transform_length(5000))

    def test_offset_transformed_length_uses_real_millimeters(self):
        self.assertEqual(4996, offset_transformed_length(transform_length(4999), -3))
        self.assertEqual(5494, offset_transformed_length(transform_length(5350), -3))

    def test_length_ticks_include_left_boundary_before_5000(self):
        self.assertEqual(
            [4950, 5000, 5100, 5200, 5250, 5300, 5350, 5400],
            length_ticks(4960, 5402),
        )

    def test_chart_positions_do_not_shift_adjacent_models(self):
        rows = [
            {"model_key": "m6", "length": 4960},
            {"model_key": "su7", "length": 4997},
            {"model_key": "m9", "length": 5285},
        ]

        self.assertEqual(
            {"m6": 4960, "su7": 4997, "m9": 5370},
            chart_positions(rows),
        )

    def test_version_label_uses_version_id_without_model_or_energy(self):
        self.assertEqual(
            "Max 5座",
            version_label(
                "鸿蒙智行-问界_M7_2025款换代_Max_增程_5座",
                "鸿蒙智行-问界_M7_2025款换代",
                ["增程"],
                ["Ultra"],
            ),
        )

    def test_version_label_keeps_seat_layout_and_battery_disambiguators(self):
        self.assertEqual(
            "行政豪华版 6座通道",
            version_label(
                "蔚来_ES9_2026款_行政豪华版_6座通道",
                "蔚来_ES9_2026款",
                ["纯电"],
                ["行政豪华版"],
            ),
        )
        self.assertEqual(
            "Ultra 70kWh",
            version_label(
                "极氪_8X_2026款_Ultra_70kWh",
                "极氪_8X_2026款",
                ["插混"],
                ["Ultra"],
            ),
        )

    def test_version_label_falls_back_to_version_level(self):
        self.assertEqual(
            "Ultra",
            version_label("", "理想_L9_2026款全新", ["增程"], ["Ultra"]),
        )

    def test_model_name_pairs_choose_latest_nearest_main(self):
        rows = [
            {
                "model_key": "su7",
                "model_name": "小米 SU7",
                "generation": "2026款/改款",
                "length": 4997,
            },
            {
                "model_key": "yu7-2025",
                "model_name": "小米 YU7",
                "generation": "2025款",
                "length": 4999,
            },
            {
                "model_key": "yu7-2026-short",
                "model_name": "小米 YU7",
                "generation": "2026款",
                "length": 4999,
            },
            {
                "model_key": "yu7-2026-long",
                "model_name": "小米 YU7",
                "generation": "2026款",
                "length": 5015,
            },
        ]
        names = {row["model_key"]: row["model_name"] for row in rows}

        pairs = model_name_pairs(names, rows, chart_positions(rows))

        self.assertIn(("yu7-2026-short", "su7"), pairs)

    def test_same_name_energy_and_length_share_one_spine_group(self):
        model_data = {
            "yu7-2025": {
                "bev": [(25.35, 4999, "标准版")],
            },
            "yu7-2026": {
                "bev": [(28.99, 4999, "长续航版"), (38.99, 4999, "GT")],
            },
        }
        model_x = {"yu7-2025": 4999, "yu7-2026": 4999}
        display_names = {"yu7-2025": "小米YU7", "yu7-2026": "小米YU7"}

        axes = model_axis_positions(model_data, model_x, [])
        points = spine_points_by_axis(model_data, display_names, axes)

        key = header_key_for_name("小米YU7", "bev", 4999)
        self.assertEqual(
            [(25.35, 4999, "标准版"), (28.99, 4999, "长续航版"), (38.99, 4999, "GT")],
            points[key],
        )

    def test_header_x_shifts_right_when_it_overlaps_other_axis(self):
        own_key = header_key_for_name("小米YU7", "bev", 4999)
        other_key = header_key_for_name("小米SU7", "bev", 4999)
        self.assertEqual(
            5004,
            shifted_header_x(4999, {own_key}, {own_key: 4999, other_key: 4999}),
        )
        self.assertEqual(
            4999,
            shifted_header_x(4999, {own_key, other_key}, {own_key: 4999, other_key: 4999}),
        )


if __name__ == "__main__":
    unittest.main()
