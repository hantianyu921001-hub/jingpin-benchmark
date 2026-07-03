# Vehicle Data Source Policy

## Priority

1. Existing internal Base data, especially `01_发布会文档` reference documents when migrating from `01/02`.
2. 工信部公告批次数据（仅限公示期车型的产品型号、尺寸、能源类型、座位数；不含价格）
3. 汽车之家
4. 懂车帝
5. Official brand site, launch conference pages, press releases
6. Major automotive media, only for fields missing from the first four
7. Social media posts, only when the user explicitly provides them or no better source exists

## Lookup Rules

- For current or latest data, browse before answering or writing.
- Search the exact model year, trim, and launch date when available.
- Prefer configuration pages or spec tables over narrative articles.
- Use at least two sources for high-impact fields when practical: price, size, battery, range, ADAS hardware, chassis, and audio.
- If 汽车之家 and 懂车帝 differ, do not silently average or combine values. State the conflict and use the source with clearer version-level configuration.

## Field Handling

- Use official Chinese model/version names from the source where possible.
- Convert units only when the table requires it; otherwise keep common automotive units, such as `mm`, `kWh`, `km`, `kW`, `Ps`, `Nm`.
- Keep prices in `万元`.
- Use exact launch and delivery dates when available.
- Do not infer optional equipment as standard equipment unless a source clearly says it is standard for that version.

## Final Response

When data was written, summarize:

- Which tables were updated.
- How many rows were created or updated by table.
- Important source conflicts or unresolved blanks.
- Primary source links used.
