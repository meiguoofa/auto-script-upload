"""Playwright 表单操作封装（异步 API）。"""

import asyncio
from pathlib import Path
from typing import List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config import COMBOBOX_PLACEHOLDERS, DEFAULTS, SELECTORS, TARGET_LIST_URL


async def create_new_draft(context, list_url: str = TARGET_LIST_URL) -> Page:
    """在 series/list 点击「新建」，等待导航到 draft 编辑页，返回 Page。"""
    from config import ERROR_DIR

    page = await context.new_page()
    await page.set_viewport_size({"width": 1440, "height": 900})
    await page.goto(list_url, wait_until="domcontentloaded")

    # 检查是否被踢到登录页
    current_url = page.url
    if "login" in current_url.lower() or "signin" in current_url.lower():
        await page.close()
        raise RuntimeError(f"未登录，当前URL: {current_url}，请先运行 analyze_page.py 登录")

    create_btn = page.get_by_role("button", name="新建")
    if await create_btn.count() == 0:
        create_btn = page.locator(SELECTORS["create_button"])

    try:
        await create_btn.first.wait_for(state="visible", timeout=10000)
        await create_btn.first.click()

        # 等待 draft 页：可能是 URL 变化，也可能是当前页出现 #title 输入框（modal 或 SPA 路由）
        try:
            await page.wait_for_url("**/series/draft*", wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            await page.wait_for_selector("#title", state="visible", timeout=30000)
    except Exception as e:
        ERROR_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(ERROR_DIR / "create_draft_failed.png"))
        current_url = page.url
        await page.close()
        raise RuntimeError(f"新建 draft 失败，当前URL: {current_url}, 错误: {e}")

    return page


async def fill_basic_info(page: Page, drama) -> None:
    """填写基础信息文本字段。"""
    await page.fill(SELECTORS["title"], drama.title)
    await page.fill(SELECTORS["description"], drama.description)
    await page.fill(SELECTORS["total_video_num"], str(drama.episode_count))
    await page.fill(SELECTORS["preview_video_num"], DEFAULTS["preview_video_num"])
    await page.fill(SELECTORS["preview_video_num_on_profile"], DEFAULTS["preview_video_num_on_profile"])


async def _set_checkbox(page: Page, selector: str, checked: bool = True) -> None:
    """勾选或取消勾选真实 input checkbox；若被自定义 UI 覆盖则用 JS click。"""
    loc = page.locator(selector)
    try:
        is_checked = await loc.is_checked(timeout=5000)
    except PlaywrightTimeout:
        is_checked = False
    if is_checked != checked:
        try:
            await loc.click(timeout=5000)
        except Exception:
            # 自定义组件覆盖时，直接用 DOM click 触发
            await loc.evaluate("el => el.click()")


async def set_switches_and_radios(page: Page) -> None:
    """设置托管模式、版权承诺、发布方式单选。"""
    await _set_checkbox(page, SELECTORS["consignment_status"], checked=True)
    await _set_checkbox(page, SELECTORS["signed"], checked=True)

    # 发布方式：找到包含「过审后自动发布」的 label，点击其内部 radio
    publish_label = page.locator("label", has_text=DEFAULTS["publish_method"])
    try:
        await publish_label.click(timeout=5000)
    except Exception:
        radio = publish_label.locator("input[type='radio']")
        await radio.evaluate("el => el.click()")


async def select_dropdown_by_placeholder(page: Page, placeholder: str, option_text: str) -> None:
    """通过 combobox 的 placeholder 文本定位，选择指定选项。"""
    # 直接用 role=combobox + placeholder 文本定位，比字段容器更精确
    combobox = page.get_by_role("combobox", name=placeholder)
    if await combobox.count() == 0:
        # 兜底：用 :has-text 选择器
        combobox = page.locator(f"[role='combobox']:has-text('{placeholder}')")
    await combobox.first.scroll_into_view_if_needed()
    await combobox.first.click()

    # 等待下拉选项出现
    await page.wait_for_timeout(400)

    # 先按 role="option" 找，再按常见下拉选项类名兜底
    option = page.get_by_role("option", name=option_text)
    if await option.count() == 0:
        option = page.locator(
            ".semi-select-option, .ant-select-item, .arco-select-option, "
            ".dropdown-item, [class*='select-option'], [class*='dropdown-option']",
            has_text=option_text,
        )
    await option.first.click()

    # 给下拉关闭留一点时间
    await page.wait_for_timeout(300)


async def set_dropdowns(page: Page) -> None:
    """设置需要选择的下拉项；选完后按 Esc 确保弹窗/遮罩关闭。"""
    await select_dropdown_by_placeholder(
        page, COMBOBOX_PLACEHOLDERS["目标人群"], DEFAULTS["target_audience"]
    )
    await select_dropdown_by_placeholder(
        page, COMBOBOX_PLACEHOLDERS["源语言"], DEFAULTS["source_language"]
    )
    await select_dropdown_by_placeholder(
        page, COMBOBOX_PLACEHOLDERS["AI 短剧"], DEFAULTS["is_ai_drama"]
    )
    # 关闭可能残留的下拉/弹窗遮罩
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(800)
    # 等待遮罩消失
    masks = page.locator(".semi-sidesheet-mask, .semi-modal-mask, .semi-popover-wrapper")
    if await masks.count() > 0:
        try:
            await masks.first.wait_for(state="hidden", timeout=5000)
        except Exception:
            pass


async def close_overlays(page: Page) -> None:
    """关闭可能残留的下拉/弹窗/portal，避免遮挡点击。"""
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    # 点一下页面空白处（基础信息标题附近），进一步关闭 tooltip/popover
    try:
        await page.locator("h1, h2, h3").first.click()
    except Exception:
        pass
    # 等待常见 portal 消失
    for selector in [".semi-portal", ".semi-popover-wrapper", ".semi-tooltip-wrapper"]:
        try:
            await page.locator(selector).first.wait_for(state="hidden", timeout=3000)
        except Exception:
            pass


async def upload_cover(page: Page, cover_path: Path) -> None:
    """上传封面图。优先用 filechooser，兜底用隐藏 file input。"""
    cover_path = Path(cover_path)
    if not cover_path.exists():
        raise FileNotFoundError(f"封面图不存在: {cover_path}")

    # 找到封面图区域并滚动到视口
    section = page.locator("div", has_text="封面图").first
    await section.scroll_into_view_if_needed()

    # 优先点击区域触发 filechooser
    try:
        async with page.expect_file_chooser(timeout=10000) as fc_info:
            await section.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(str(cover_path))
        return
    except PlaywrightTimeout:
        pass

    # 兜底：找隐藏 file input
    file_inputs = page.locator("input[type='file']")
    if await file_inputs.count() > 0:
        await file_inputs.first.set_input_files(str(cover_path))
        return

    raise RuntimeError("无法定位封面图上传控件")


async def upload_videos(page: Page, video_paths: List[Path], timeout_per_video: int = 180) -> None:
    """点击本地上传，批量选择视频文件，并等待上传完成。"""
    video_paths = [Path(p) for p in video_paths]
    missing = [p for p in video_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"视频文件不存在: {missing}")

    expected_count = len(video_paths)
    basenames = {p.stem for p in video_paths}

    btn = page.locator(SELECTORS["local_upload_button"])
    await btn.scroll_into_view_if_needed()

    async with page.expect_file_chooser() as fc_info:
        await btn.click()
    file_chooser = await fc_info.value
    await file_chooser.set_files([str(p) for p in video_paths])

    # 先等上传 UI 渲染出来
    await page.wait_for_timeout(5000)

    # 等待上传完成：轮询检查
    deadline = asyncio.get_event_loop().time() + timeout_per_video * expected_count
    while asyncio.get_event_loop().time() < deadline:
        # 1. 页面中没有 loading/spin/progress 元素
        loaders = page.locator(
            ".loading, .spin, [class*='loading'], [class*='spin'], "
            "[class*='progress'], [class*='uploading']"
        )
        has_loader = await loaders.count() > 0

        # 2. 页面上能看到所有上传视频的文件名（去掉扩展名）
        page_text = await page.locator("body").text_content() or ""
        visible_names = sum(1 for name in basenames if name in page_text)

        if not has_loader and visible_names >= expected_count:
            # 再等一下让列表稳定
            await page.wait_for_timeout(1500)
            return

        await asyncio.sleep(2)

    raise TimeoutError("视频上传等待超时")


async def click_save(page: Page) -> None:
    """点击保存按钮。"""
    save_btn = page.locator(SELECTORS["save_button"])
    await save_btn.scroll_into_view_if_needed()
    # 如果按钮禁用，等一小会儿再试
    if not await save_btn.is_enabled():
        await page.wait_for_timeout(2000)
    await save_btn.click()
    # 给保存请求响应时间
    await page.wait_for_timeout(3000)


async def fill_and_save(page, drama) -> None:
    """对一个 draft 页完成：填表、上传、保存。"""
    await fill_basic_info(page, drama)
    await set_dropdowns(page)
    await set_switches_and_radios(page)
    await close_overlays(page)
    await upload_cover(page, drama.cover_path)
    await close_overlays(page)
    await upload_videos(page, drama.video_paths)
    await close_overlays(page)
    await click_save(page)
