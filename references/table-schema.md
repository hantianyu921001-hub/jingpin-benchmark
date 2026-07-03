# Vehicle Benchmark Table Scheme

## Base

- Base token: `E571b0YbQa2MxysVn4RctXcDn7d`
- Main object: Feishu/Lark Base `竞品benchmark`

## Tables

| Module | Table | Table ID | Row grain |
| --- | --- | --- | --- |
| 00 | `00_车型` | `tbl92hQB5ngDEvRH` | One row per unified vehicle model/generation |
| 10 | `10_版本价格` | `tblWDFfm3M3uX9qx` | One row per distinct version, price, energy type, and seat layout |
| 11 | `11_设计(尺寸灯光车门)` | `tblUAEHLyihXdwXn` | Split only by distinct body length |
| 11A | `11A_设计差异明细` | `tblWBFDRhxip77jy` | One row per design configuration item/value/version-scope difference |
| 12 | `12_空间(座椅NVH空调)` | `tblyyiC7y6r21Ti5` | Split by distinct space, seat, NVH, AC, cabin health values |
| 13 | `13_智能驾驶` | `tblFLQjKa91NiFKz` | Split by ADAS hardware, compute, sensor, or function differences |
| 14 | `14_智能座舱` | `tblZv13LhbwJ4l6e` | Split by cockpit, screen, chip, audio, interaction differences |
| 15 | `15_底盘` | `tblVhYbXA8WQDSkS` | Split by suspension, material, steering, braking, wheelbase/chassis differences |
| 16 | `16_三电` | `tbllgpvch11HVnqq` | Split by powertrain, battery, range, charging, motor differences |
| 17 | `17_安全` | `tblTjuDT2NHD3xGR` | Split by body, airbag, active/passive safety differences |

## Unified IDs

Recommended formats:

- `车型统一ID`: `<品牌>_<核心车系>_<年款/代际>`
- `版本统一ID`: `<车型统一ID>_<版本等级>`；只有不能唯一定位版本时，才追加最少必要的区分字段

`核心车系` should remove brand or sub-brand prefixes already represented in `品牌`.
Examples: `理想MEGA` -> `MEGA`, `问界M7` -> `M7`, `智界V9` -> `V9`, `乐道L80` -> `L80`, `小米YU7` -> `YU7`.

`版本等级` is the standard `<版本>` field. Use the actual sale-version level from `10_版本价格.版本等级`, such as `Max+`, `Ultra`, or `Livis`.

Build `版本统一ID` with the minimum fields needed for uniqueness:

1. Start with `<车型统一ID>_<版本等级>`.
2. Append extra fields only for the duplicate group where that field is needed.
3. If energy type creates a version difference, append `_<能源类型>`.
4. If seat count creates a version difference, append `_<座位数>`.
5. If a model-level rule requires a discriminator, keep it even if a subset of rows could be unique without it.
6. If still duplicate, stop and report the collision before adding another discriminator.

Model-level discriminator rules:

- 问界 M7 / M8 / M9: keep `座位数` in `版本统一ID`.
- 蔚来 ES9: use seat layout such as `6座通道` / `6座中岛` when seat count alone cannot distinguish.
- 极氪 8X / 9X: use battery pack or capacity such as `55kWh` / `70kWh` when needed.

Examples:

- `理想_L9_2026款全新`
- `理想_L9_2026款全新_Ultra`
- `理想_L9_2026款全新_Livis`
- `鸿蒙智行-问界_M9_2026款全新_Ultra_增程_5座`

## Splitting Rules

- `00_车型`: do not split by trim unless the user asks for separate generations/models.
- `10_版本价格`: always split by distinct listed sale version.
- `11_设计`: split only when `长(mm)` differs. Rows with the same `车型排序码` and body length should be merged even when they link to different year/generation model records. If one row has blank length and the same `车型排序码` has only one known body length, merge the blank-length row into that known-length row. Width, height, wheelbase, paint, interior color/material, wheel/tire, light, door, and other version-level design differences stay in the first row for that model and body length.
- `11A_设计差异明细`: use for version-level design differences under a 11 design row. One row represents one `配置模块 + 配置项 + 参数值 + 适用版本` combination, linked back to the corresponding 11 row and 10 versions.
- `12_空间`: merge if seat layout and all space/comfort/health cabin fields are the same.
- `13_智能驾驶`: split when chip, TOPS, LiDAR count, sensor set, ADAS functions, or ADAS platform differs.
- `14_智能座舱`: merge if screen, chip, OS, audio, connectivity, and interaction fields are the same.
- `15_底盘`: split when suspension, air suspension, active suspension, CDC, rear steering, braking, chassis material, turning radius, or towing differs.
- `16_三电`: split when battery, range, fuel tank, motor, charging, voltage platform, or energy type differs.
- `17_安全`: merge if body, airbag, battery safety, active safety, and emergency functions are the same.

## Module Row-count Guard (20-70)

- Apply to every configuration table from `20_设计` through `70_安全`, grouped by the linked `关联车型` record rather than `车型排序码`.
- More than 3 rows for one model is a mandatory review trigger, not an automatic pass.
- Before completion, compare all rows field by field. Merge rows with no actual parameter-value difference; retain more than 3 rows only when every row has a concrete, module-relevant differentiating parameter.
- Report the review result outside the configuration table. Do not add review notes to module parameter fields.

## Write Rules

- For module tables, write only parameter values in fields.
- Do not write source commentary, uncertainty wording, or long explanatory prose into module fields.
- Assign each fact to one most-specific field only. Do not duplicate it in another field merely because it is related.
- Dedicated columns take priority over broad fields. Split structured facts into the existing columns, and do not write a mixed bundle into one cell when sibling columns exist for the same facts.
- For cockpit/cabin rows, separate screen, HUD, chip, OS, audio, speaker, connectivity, interaction, seat, storage, charging, lighting, and cabin-health facts into their own fields where available.
- For chassis rows, separate front suspension, rear suspension, active suspension, chassis material, steering, braking, turning radius, towing, and wheelbase/chassis facts into their own fields where available.
- Use a broad/free-text field only for residual facts with no exact field. If the nearest field would hide a missing schema decision, ask the user instead of writing there.
- When field ownership is ambiguous, ask the user before writing; leave the fact unwritten until the owner field is confirmed.
- If a field is unknown, leave it blank.
- If a value is a minimum or threshold, preserve the symbol when the field supports text, for example `>10000N`.
- Keep old rows marked as retired/退市 unchanged unless explicitly requested.

## Display Order

- Tables `00` and `10-17` use a text helper field named `车型排序码`.
- `车型排序码` is a four-character code: `xxyy`.
- `xx` is the two-digit brand code. Current convention starts with `01=理想`, `02=鸿蒙智行-问界`; remaining brands continue by agreed benchmark order.
- `yy` is the two-digit model code within that brand. Example: `理想_L9=0101`, `理想_MEGA=0102`.
- Same model across different years can share the same `yy`, such as `小米_YU7_2025款` and `小米_YU7_2026款`.
- Set each `00` and `10-17` table view sort to `车型排序码` ascending.
