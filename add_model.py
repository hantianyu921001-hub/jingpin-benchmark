#!/usr/bin/env python3
"""Compatibility guard for the removed direct-write workflow."""
import sys


def main():
    print(
        "car-spectrum-chart v3 只负责生成谱系图，不再直接写入旧表 02_整车配置。\n"
        "请先按 lark-vehicle-benchmark 流程将车型补充到 00_车型、10_版本价格、"
        "11_设计(尺寸灯光车门)，再运行 chart.py 刷新图表。"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
