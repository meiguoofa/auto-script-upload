"""TikTok Drama Center 批量上传主入口。"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright


def safe_str(s: str) -> str:
    """把字符串编码成当前终端可显示的格式，无法显示的字用 ? 代替。"""
    try:
        enc = sys.stdout.encoding or "gbk"
        return s.encode(enc, errors="replace").decode(enc)
    except Exception:
        return s

from config import (
    BROWSER_CHANNEL,
    ERROR_DIR,
    HEADLESS,
    MAX_PARALLEL_TABS,
    USER_DATA_DIR,
    VIEWPORT,
)
from downloader import ensure_downloads
from form import create_new_draft, fill_and_save
from models import Drama
from reader import read_excel


async def process_one_drama(context, drama: Drama) -> None:
    """处理一部剧：新建 draft、填表、上传、保存。"""
    page = None
    try:
        drama.status = "processing"
        page = await create_new_draft(context)
        drama.draft_url = page.url
        print(f"[row {drama.row_idx}] 新建 draft: {page.url}")

        await fill_and_save(page, drama)
        drama.status = "done"
        print(f"[row {drama.row_idx}] [OK] 保存成功: {safe_str(drama.title)}")
    except Exception as e:
        drama.status = "failed"
        drama.error = str(e)
        print(f"[row {drama.row_idx}] [ERR] 失败: {e}")
        if page:
            try:
                ERROR_DIR.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(ERROR_DIR / f"row_{drama.row_idx}.png"))
            except Exception:
                pass
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def run(excel_path: Path, limit: Optional[int] = None) -> None:
    """主流程：读 Excel → 下载 → 并行上传。"""
    excel_path = Path(excel_path)
    dramas = read_excel(excel_path)
    print(f"[INFO] 从 {excel_path} 读取到 {len(dramas)} 部剧")

    if limit is not None:
        dramas = dramas[:limit]
        print(f"[INFO] 本次仅处理前 {limit} 部")

    # 下载封面与视频
    print("[INFO] 开始下载封面和视频...")
    dramas = await ensure_downloads(dramas)
    ready = [d for d in dramas if d.status == "ready"]
    failed_download = [d for d in dramas if d.status == "failed"]
    if failed_download:
        for d in failed_download:
            print(f"[row {d.row_idx}] 下载失败: {d.error}")
    print(f"[INFO] 下载完成: {len(ready)} 部可处理")

    if not ready:
        print("没有可处理的剧，退出。")
        return

    # 启动浏览器
    print("[INFO] 启动浏览器...")
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                channel=BROWSER_CHANNEL,
                headless=HEADLESS,
                viewport=VIEWPORT,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            print(f"启动 {BROWSER_CHANNEL} 失败: {e}，回退到自带 chromium")
            context = await p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=HEADLESS,
                viewport=VIEWPORT,
                args=["--disable-blink-features=AutomationControlled"],
            )

        # 限制并发 Tab 数
        sem = asyncio.Semaphore(MAX_PARALLEL_TABS)

        async def bounded(d: Drama):
            async with sem:
                await process_one_drama(context, d)

        await asyncio.gather(*[bounded(d) for d in ready])

        await context.close()

    # 汇总
    done = [d for d in dramas if d.status == "done"]
    failed = [d for d in dramas if d.status == "failed"]
    print("\n" + "=" * 60)
    print(f"[SUMMARY] 处理完成: 成功 {len(done)} / 失败 {len(failed)} / 总计 {len(dramas)}")
    if failed:
        print("失败明细:")
        for d in failed:
            print(f"  [row {d.row_idx}] {safe_str(d.title)}: {safe_str(d.error)}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="TikTok Drama Center 批量上传")
    parser.add_argument("excel", nargs="?", default="export_20260705_180246.xlsx", help="Excel 文件路径")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 部剧（用于测试）")
    args = parser.parse_args()

    asyncio.run(run(Path(args.excel), limit=args.limit))


if __name__ == "__main__":
    main()
