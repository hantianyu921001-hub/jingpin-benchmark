#!/usr/bin/env python3
"""网页截图抓取模块 — 加载汽车参数页 URL 并截图传给 extractor。

使用 Playwright 加载页面、等待渲染、截取参数配置区域。
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

# 延迟导入 Playwright，仅在需要时加载
_playwright = None


def _get_playwright():
    global _playwright
    if _playwright is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright
    return _playwright


# ── 站点配置 ──────────────────────────────────────────────────────────

# 各站点的参数配置页选择器和等待条件
SITE_CONFIGS = {
    "autohome.com.cn": {
        "name": "汽车之家",
        "param_selector": ".configuration-main, .car-param-content, .spec-param-wrap",
        "wait_selector": ".configuration-main, .spec-param-wrap, table.config-table",
        "wait_ms": 3000,
        "remove_selectors": [".header", ".footer", ".ad", ".popup", ".float-bar"],
    },
    "dongchedi.com": {
        "name": "懂车帝",
        "param_selector": ".tw-param-module, .parameter-module, .config-parameter",
        "wait_selector": ".tw-param-module, .parameter-module, .config-parameter",
        "wait_ms": 3000,
        "remove_selectors": [".header", ".footer", ".ad", ".float-btn"],
    },
    "hima.auto": {
        "name": "鸿蒙智行官网",
        "param_selector": ".spec-section, .parameter-section, .config-form, main",
        "wait_selector": ".spec-section, .parameter-section, main",
        "wait_ms": 5000,
        "remove_selectors": [".header", ".footer", ".float-icon"],
    },
    "lixiang.com": {
        "name": "理想官网",
        "param_selector": ".spec-content, .parameter-wrap, .config-content, main",
        "wait_selector": ".spec-content, .parameter-wrap, main",
        "wait_ms": 5000,
        "remove_selectors": [".header", ".footer"],
    },
    # 通用兜底
    "default": {
        "name": "通用",
        "param_selector": "body",
        "wait_selector": "body",
        "wait_ms": 5000,
        "remove_selectors": [],
    },
}


def _get_site_config(url: str) -> dict:
    """根据 URL 匹配站点配置。"""
    domain = urlparse(url).netloc.lower()
    for key, cfg in SITE_CONFIGS.items():
        if key in domain:
            return cfg
    return SITE_CONFIGS["default"]


# ── 抓取函数 ─────────────────────────────────────────────────────────

def capture_screenshot(
    url: str,
    output_path: Optional[str] = None,
    full_page: bool = False,
    viewport_width: int = 1440,
    viewport_height: int = 900,
) -> str:
    """加载网页并截图参数配置区域。

    Args:
        url: 目标网页 URL
        output_path: 截图保存路径，None 则保存到临时文件
        full_page: 是否截取整页（True）还是只截参数区域（False）
        viewport_width: 视口宽度
        viewport_height: 视口高度

    Returns:
        截图文件路径
    """
    playwright = _get_playwright()
    cfg = _get_site_config(url)

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="car_spec_")
        os.close(fd)

    print(f"  → 站点: {cfg['name']}", file=sys.stderr)
    print(f"  → 加载: {url}", file=sys.stderr)

    with playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            print(f"  → 最终 URL: {page.url}", file=sys.stderr)

            # 等待参数内容加载
            try:
                page.wait_for_selector(cfg["wait_selector"], timeout=15000)
            except Exception:
                print("  ⚠ 选择器等待超时，继续截图", file=sys.stderr)

            # 额外等待渲染
            page.wait_for_timeout(cfg["wait_ms"])

            # 移除干扰元素
            for sel in cfg["remove_selectors"]:
                try:
                    page.evaluate(f"""
                        document.querySelectorAll('{sel}').forEach(el => el.remove());
                    """)
                except Exception:
                    pass

            if full_page:
                page.screenshot(path=output_path, full_page=True)
            else:
                # 截取参数区域
                try:
                    param_el = page.locator(cfg["param_selector"]).first
                    param_el.screenshot(path=output_path)
                except Exception:
                    print("  ⚠ 无法定位参数区域，截取整页", file=sys.stderr)
                    page.screenshot(path=output_path, full_page=True)

            print(f"  ✓ 截图保存: {output_path}", file=sys.stderr)

        finally:
            context.close()
            browser.close()

    return output_path


def capture_multiple_screenshots(
    url: str,
    output_dir: Optional[str] = None,
    max_height_per_shot: int = 5000,
    viewport_width: int = 1440,
) -> List[str]:
    """分页截取长页面，用于参数配置很多的情况。

    Args:
        url: 目标 URL
        output_dir: 输出目录
        max_height_per_shot: 每张截图最大高度（像素）

    Returns:
        截图路径列表
    """
    playwright = _get_playwright()
    cfg = _get_site_config(url)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="car_spec_")

    print(f"  → 站点: {cfg['name']}", file=sys.stderr)

    paths = []
    with playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            try:
                page.wait_for_selector(cfg["wait_selector"], timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(cfg["wait_ms"])

            # 获取整页高度
            page_height = page.evaluate("document.body.scrollHeight")
            shots = max(1, (page_height + max_height_per_shot - 1) // max_height_per_shot)

            for i in range(shots):
                scroll_y = i * max_height_per_shot
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(500)

                path = os.path.join(output_dir, f"spec_{i + 1:02d}.png")
                page.screenshot(
                    path=path,
                    clip={
                        "x": 0,
                        "y": scroll_y,
                        "width": viewport_width,
                        "height": min(max_height_per_shot, page_height - scroll_y),
                    },
                )
                paths.append(path)
                print(f"  ✓ 截图 {i + 1}/{shots}: {path}", file=sys.stderr)

        finally:
            context.close()
            browser.close()

    return paths


# ── 快速抓取 + 提取 ──────────────────────────────────────────────────

def scrape_and_extract(
    url: str,
    cleanup: bool = True,
) -> dict:
    """一步完成：抓取网页截图 → 提取结构化数据。

    Args:
        url: 目标网页 URL
        cleanup: 提取后是否删除临时截图

    Returns:
        结构化车型数据 dict
    """
    from extractor import extract_from_image

    screenshot_path = capture_screenshot(url)

    try:
        print(f"  → 开始视觉提取...", file=sys.stderr)
        result = extract_from_image(screenshot_path)
        return result
    finally:
        if cleanup:
            try:
                os.unlink(screenshot_path)
                print(f"  ✓ 已清理临时文件", file=sys.stderr)
            except Exception:
                pass


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="网页参数截图抓取")
    parser.add_argument("url", help="目标网页 URL")
    parser.add_argument("--out", "-o", help="截图输出路径")
    parser.add_argument("--full", action="store_true", help="截取整页")
    parser.add_argument("--extract", action="store_true", help="截图后直接提取数据")
    parser.add_argument("--width", type=int, default=1440, help="视口宽度")
    args = parser.parse_args()

    if args.extract:
        result = scrape_and_extract(args.url, cleanup=not args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        path = capture_screenshot(
            args.url,
            output_path=args.out,
            full_page=args.full,
            viewport_width=args.width,
        )
        print(path)


if __name__ == "__main__":
    import json
    main()
