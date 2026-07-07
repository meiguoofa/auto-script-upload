"""
TikTok Drama Center 自动上传脚本：
- 读取 Excel 中选定的剧
- 下载封面和视频到本地
- 按平台规则过滤视频（大小 5MB~4GB、时长 15s~20min）
- 新建 draft，填写全部表单参数
- 上传封面图和视频
- 点击保存
"""

import argparse
import asyncio
import secrets
from pathlib import Path

from playwright.async_api import async_playwright

from config import (
    BROWSER_CHANNEL,
    DEFAULTS,
    ERROR_DIR,
    HEADLESS,
    SELECTORS,
    TARGET_LIST_URL,
    USER_DATA_DIR,
    VIEWPORT,
)
from downloader import ensure_downloads
from form import (
    click_save,
    close_overlays,
    create_new_draft,
    ensure_logged_in,
    fill_basic_info,
    select_contract,
    set_dropdowns,
    set_switches_and_radios,
    upload_cover,
    upload_videos,
    wait_for_uploads_complete,
)
from reader import read_excel
from video_validator import filter_videos

# 默认并发处理的剧集数；每部剧占用一个独立的浏览器 Tab。可用 --concurrency 覆盖
MAX_CONCURRENT = 5


async def process_one(context, d) -> None:
    """处理一部剧：新建 draft（独立 Tab）→ 填表 → 上传封面/视频 → 保存。失败时截图。"""
    page = None
    try:
        page = await create_new_draft(context)
        print(f"[row {d.row_idx}] 新建 draft: {page.url}")

        page.on("console", lambda msg: print(f"[console {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[pageerror] {err}"))

        print(f"[row {d.row_idx}] 本次使用剧名: {d.title}")

        # 1. 填写基础文本字段
        print(f"[row {d.row_idx}] 填写基础信息...")
        await fill_basic_info(page, d)

        # 2. 设置所有下拉框（关联合同、目标人群、源语言、AI短剧）
        print(f"[row {d.row_idx}] 设置下拉框...")
        await set_dropdowns(page)

        # 3. 设置开关和单选（托管模式、版权承诺、发布方式）
        print(f"[row {d.row_idx}] 设置开关/单选...")
        await set_switches_and_radios(page)

        # 4. 下拉框选择后总集数会被清空，重新填入
        await page.fill(SELECTORS["total_video_num"], str(d.episode_count))
        await close_overlays(page)

        # 5. 上传封面
        if d.cover_path and Path(d.cover_path).exists():
            print(f"[row {d.row_idx}] 上传封面...")
            await upload_cover(page, d.cover_path)
            await close_overlays(page)

        # 6. 上传视频
        print(f"[row {d.row_idx}] 上传 {len(d.video_paths)} 个视频...")
        await upload_videos(page, d.video_paths)

        # 7. 等待视频上传完成
        print(f"[row {d.row_idx}] 等待视频上传完成...")
        await wait_for_uploads_complete(page, expected=len(d.video_paths))

        # 8. 保存
        print(f"[row {d.row_idx}] 点击保存...")
        await close_overlays(page)
        await click_save(page)
        print(f"[row {d.row_idx}] [OK] 保存成功: {d.title}")

    except Exception as e:
        print(f"[row {d.row_idx}] [ERR] 失败: {e}")
        if page:
            try:
                ERROR_DIR.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(ERROR_DIR / f"row_{d.row_idx}_err.png"))
            except Exception:
                pass
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def run(excel_path: Path, limit: int | None = None, concurrency: int = MAX_CONCURRENT) -> None:
    excel_path = Path(excel_path)
    dramas = read_excel(excel_path)
    print(f"[INFO] 从 {excel_path} 读取到 {len(dramas)} 部剧")

    if limit is not None:
        dramas = dramas[:limit]
        print(f"[INFO] 本次仅处理前 {limit} 部")

    print("[INFO] 开始下载封面和视频...")
    dramas = await ensure_downloads(dramas)
    ready = [d for d in dramas if d.status == "ready"]
    print(f"[INFO] 下载完成: {len(ready)} 部可处理")

    if not ready:
        print("没有可处理的剧，退出。")
        return

    # 过滤视频 + 剧名加随机后缀
    for d in ready:
        d.video_paths = filter_videos(d.video_paths)
        if not d.video_paths:
            d.status = "failed"
            d.error = "没有符合大小/时长要求的视频"
        else:
            suffix = secrets.token_hex(3)
            base = d.title[:28].rstrip("_")
            d.title = f"{base}_{suffix}"

    ready = [d for d in ready if d.status == "ready"]
    if not ready:
        print("过滤后没有可处理的剧，退出。")
        return

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

        # 先确认已登录，未登录则等待用户手动登录
        await ensure_logged_in(context)

        # 并发处理：每部剧占用一个独立 Tab，同时最多 concurrency 部（至少 1，避免 0 卡死）
        sem = asyncio.Semaphore(max(1, concurrency))

        async def bounded(d):
            async with sem:
                await process_one(context, d)

        await asyncio.gather(*[bounded(d) for d in ready])

        await context.close()
    print("[INFO] 完成")


def main():
    parser = argparse.ArgumentParser(description="TikTok Drama Center 自动上传")
    parser.add_argument("excel", nargs="?", default="export_20260706_104908.xlsx", help="Excel 文件路径")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 部剧")
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENT, help=f"同时并发处理的剧集数（每个剧一个 Tab），默认 {MAX_CONCURRENT}")
    args = parser.parse_args()
    asyncio.run(run(Path(args.excel), limit=args.limit, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
