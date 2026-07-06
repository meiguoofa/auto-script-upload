"""
最小视频上传验证：
- 读取 Excel 中选定的剧
- 仅下载视频到本地（不下载封面）
- 按平台规则过滤视频（大小、时长）
- 新建 draft，只填写「关联合同、剧集名、剧集描述」三个字段
- 点击「本地上传」上传过滤后的视频
- 不保存，仅截图验证
"""

import argparse
import asyncio
import secrets
from pathlib import Path

from playwright.async_api import async_playwright

from config import (
    BROWSER_CHANNEL,
    DOWNLOAD_DIR,
    ERROR_DIR,
    HEADLESS,
    TARGET_LIST_URL,
    USER_DATA_DIR,
    VIEWPORT,
)
from downloader import ensure_downloads
from form import (
    click_save,
    close_overlays,
    create_new_draft,
    fill_minimal_for_upload,
    upload_videos,
    wait_for_uploads_complete,
)
from reader import read_excel
from video_validator import filter_videos


async def run(excel_path: Path, limit: int | None = None) -> None:
    excel_path = Path(excel_path)
    dramas = read_excel(excel_path)
    print(f"[INFO] 从 {excel_path} 读取到 {len(dramas)} 部剧")

    if limit is not None:
        dramas = dramas[:limit]
        print(f"[INFO] 本次仅处理前 {limit} 部")

    # 跳过封面下载，只下载视频
    for d in dramas:
        d.cover_url = ""

    print("[INFO] 开始下载视频...")
    dramas = await ensure_downloads(dramas)
    ready = [d for d in dramas if d.status == "ready"]
    print(f"[INFO] 下载完成: {len(ready)} 部可处理")

    if not ready:
        print("没有可处理的剧，退出。")
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

        for d in ready:
            page = None
            try:
                page = await create_new_draft(context)
                print(f"[row {d.row_idx}] 新建 draft: {page.url}")

                page.on("console", lambda msg: print(f"[console {msg.type}] {msg.text}"))
                page.on("pageerror", lambda err: print(f"[pageerror] {err}"))

                # 为避免（关联合同 + 剧集名）重复，给剧名加一个随机后缀（总长度不超过 35）
                suffix = secrets.token_hex(3)
                base = d.title[:28].rstrip("_")
                d.title = f"{base}_{suffix}"
                print(f"[row {d.row_idx}] 本次使用剧名: {d.title}")

                print(f"[row {d.row_idx}] 填写关联合同、剧集名、剧集描述...")
                await fill_minimal_for_upload(page, d)
                # 等待合同对象初始化完成，避免后续上传因 contractId 缺失失败
                await page.wait_for_timeout(2000)

                filtered = filter_videos(d.video_paths)
                if not filtered:
                    print(f"[row {d.row_idx}] 没有符合要求的视频，跳过上传")
                    continue

                print(f"[row {d.row_idx}] 上传 {len(filtered)} 个视频...")
                await upload_videos(page, filtered)

                print(f"[row {d.row_idx}] 等待视频上传完成...")
                await wait_for_uploads_complete(page, expected=len(filtered))

                print(f"[row {d.row_idx}] 点击保存...")
                await close_overlays(page)
                await click_save(page)

                ERROR_DIR.mkdir(parents=True, exist_ok=True)
                shot_path = ERROR_DIR / f"row_{d.row_idx}_videos_minimal.png"
                await page.screenshot(path=str(shot_path), full_page=True)
                print(f"[row {d.row_idx}] 截图已保存: {shot_path}")

            except Exception as e:
                print(f"[row {d.row_idx}] 失败: {e}")
                if page:
                    try:
                        ERROR_DIR.mkdir(parents=True, exist_ok=True)
                        await page.screenshot(path=str(ERROR_DIR / f"row_{d.row_idx}_videos_minimal_err.png"))
                    except Exception:
                        pass
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass

        await context.close()
    print("[INFO] 完成")


def main():
    parser = argparse.ArgumentParser(description="最小视频上传验证（仅填 3 个字段）")
    parser.add_argument("excel", nargs="?", default="export_20260706_104908.xlsx", help="Excel 文件路径")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 部剧")
    args = parser.parse_args()
    asyncio.run(run(Path(args.excel), limit=args.limit))


if __name__ == "__main__":
    main()
