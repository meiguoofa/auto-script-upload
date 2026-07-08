"""Playwright 表单操作封装（异步 API）。"""

from pathlib import Path
from typing import List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config import COMBOBOX_PLACEHOLDERS, DEFAULTS, SELECTORS, TARGET_LIST_URL


async def ensure_logged_in(context, list_url: str = TARGET_LIST_URL) -> None:
    """打开列表页检查登录状态，未登录则等待用户手动登录，登录完成后关闭检查页。"""
    page = await context.new_page()
    await page.set_viewport_size({"width": 1440, "height": 900})
    await page.goto(list_url, wait_until="domcontentloaded")
    # 等待可能的 JS 重定向
    await page.wait_for_timeout(3000)

    current_url = page.url
    if "login" in current_url.lower() or "signin" in current_url.lower():
        print("[等待登录] 检测到未登录，请在浏览器中手动完成登录...")
        print("[等待登录] 登录完成后脚本会自动继续，无需其他操作。")
        try:
            await page.wait_for_url(
                lambda url: "login" not in url.lower() and "signin" not in url.lower(),
                timeout=300000,
            )
        except PlaywrightTimeout:
            await page.close()
            raise RuntimeError("等待登录超时（5 分钟），请重新运行脚本")
        print("[等待登录] 登录成功！")
        # 等待登录后页面稳定
        await page.wait_for_timeout(3000)

    await page.close()


async def create_new_draft(context, list_url: str = TARGET_LIST_URL) -> Page:
    """在 series/list 点击「新建」，等待导航到 draft 编辑页，返回 Page。"""
    from config import ERROR_DIR

    page = await context.new_page()
    await page.set_viewport_size({"width": 1440, "height": 900})
    await page.goto(list_url, wait_until="domcontentloaded")
    # 等待可能的 JS 重定向
    await page.wait_for_timeout(3000)

    # 如果仍在登录页，等待用户登录完成（不关闭页面）
    current_url = page.url
    if "login" in current_url.lower() or "signin" in current_url.lower():
        print("[等待登录] 请在浏览器中完成登录...")
        try:
            await page.wait_for_url(
                lambda url: "login" not in url.lower() and "signin" not in url.lower(),
                timeout=300000,
            )
        except PlaywrightTimeout:
            await page.close()
            raise RuntimeError("等待登录超时（5 分钟），请重新运行脚本")
        print("[等待登录] 登录成功，继续新建 draft...")
        await page.goto(list_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

    create_btn = page.get_by_role("button", name="新建")
    if await create_btn.count() == 0:
        create_btn = page.locator(SELECTORS["create_button"])

    try:
        await create_btn.first.wait_for(state="visible", timeout=10000)
        await create_btn.first.click()

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
    await page.fill(SELECTORS["preview_video_num"],  str(min(DEFAULTS["preview_video_num"], str(int(drama.episode_count) - 1))))
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
    """设置托管模式、版权承诺（含侧边栏全部 checkbox + 同意）、发布方式单选。"""
    await _set_checkbox(page, SELECTORS["consignment_status"], checked=True)

    # ---- 步骤 1：勾选「本人承诺根据事实勾选《版权内容自查清单》...」 ----
    # 页面此时只有这一个未勾选的 semi-checkbox，直接定位点击
    promise_cb = page.locator("span.semi-checkbox-unChecked").first
    await promise_cb.scroll_into_view_if_needed()
    await promise_cb.click()
    await page.wait_for_timeout(500)
    print("[步骤1] 已点击「本人承诺」checkbox")

    # ---- 步骤 2：等待侧边栏出现，勾选所有 checkbox ----
    await page.wait_for_timeout(1000)
    sidesheet = page.locator(".semi-sidesheet-body")
    try:
        await sidesheet.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        print("[步骤2] 未检测到版权自查清单侧边栏，跳过")
        sidesheet = None

    if sidesheet and await sidesheet.count() > 0:
        unchecked = sidesheet.locator("span.semi-checkbox-unChecked")
        total = await sidesheet.locator("span.semi-checkbox").count()
        clicked = 0
        while await unchecked.count() > 0:
            await unchecked.first.click()
            clicked += 1
            await page.wait_for_timeout(300)
        print(f"[步骤2] 侧边栏共 {total} 个 checkbox，勾选了 {clicked} 个")

        # ---- 步骤 3：点击「同意」按钮（用 JS evaluate 直接点击） ----
        clicked_agree = await page.evaluate("""() => {
            const btns = document.querySelectorAll('.semi-sidesheet-footer button');
            for (const btn of btns) {
                if (btn.textContent.trim() === '同意' && !btn.disabled) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked_agree:
            print("[步骤3] 已点击「同意」")
        else:
            print("[步骤3] 未找到可点击的「同意」按钮")
        await page.wait_for_timeout(1000)

        # 确保侧边栏关闭
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

    # ---- 发布方式：选择「手动发布」（点击 label 外层触发 Semi Design 状态变更） ----
    manual_radio = page.locator("label.semi-radio:has-text('手动发布')")
    await manual_radio.scroll_into_view_if_needed()
    await manual_radio.click()
    print("[发布方式] 已选择「手动发布」")
    await page.wait_for_timeout(300)


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


async def select_contract(page: Page) -> None:
    """选择「关联合同」下拉框，默认选第一个选项。"""
    placeholder = COMBOBOX_PLACEHOLDERS["关联合同"]
    combobox = page.get_by_role("combobox", name=placeholder)
    if await combobox.count() == 0:
        combobox = page.locator(f'[role="combobox"]:has-text("{placeholder}")')
    await combobox.first.scroll_into_view_if_needed()
    await combobox.first.click()
    await page.wait_for_timeout(600)

    # 选择第一个选项
    option = page.locator(".semi-select-option-list > div").first
    await option.wait_for(state="visible", timeout=10000)
    await option.click()
    await page.wait_for_timeout(300)


async def set_dropdowns(page: Page) -> None:
    """设置需要选择的下拉项；选完后按 Esc 确保弹窗/遮罩关闭。"""
    await select_contract(page)
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


async def fill_minimal_for_upload(page, drama) -> None:
    """仅填写解锁「本地上传」按钮所需的最少字段：剧集名、剧集描述、关联合同。

    平台建议剧名字符数不超过 35，超过时截断以避免后续合同创建接口报错。
    """
    title = drama.title[:35]
    await page.fill(SELECTORS["title"], title)
    await page.fill(SELECTORS["description"], drama.description)
    await select_contract(page)
    await close_overlays(page)


async def close_overlays(page: Page) -> None:
    """关闭可能残留的下拉/弹窗/portal，避免遮挡点击。"""
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    # 点一下页面空白处（基础信息标题附近），进一步关闭 tooltip/popover
    try:
        await page.locator("h1, h2, h3").first.click()
    except Exception:
        pass
    await page.wait_for_timeout(300)
    # 强制移除仍存在的 portal 遮罩，避免遮挡后续点击
    try:
        await page.locator(".semi-portal, .semi-popover-wrapper, .semi-tooltip-wrapper").evaluate_all(
            "els => els.forEach(el => el.remove())"
        )
    except Exception:
        pass


async def upload_cover(page: Page, cover_path: Path) -> None:
    """上传封面图：操作隐藏 input，处理裁剪弹窗后确认。"""
    cover_path = Path(cover_path)
    if not cover_path.exists():
        raise FileNotFoundError(f"封面图不存在: {cover_path}")

    # 封面图对应的隐藏 input 接受 image/*
    file_input = page.locator("input[type='file'][accept='image/*']").first
    await file_input.set_input_files(str(cover_path))

    # 等待并处理裁剪弹窗
    modal = page.locator('[data-testid="minidrama-dialog"]')
    try:
        await modal.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        return

    confirm_btn = modal.locator('button:has-text("Confirm")')
    if await confirm_btn.count() == 0:
        confirm_btn = modal.locator('button:has-text("确认")')
    if await confirm_btn.count() == 0:
        confirm_btn = modal.locator('button[type="button"]').last
    await confirm_btn.click()
    await modal.wait_for(state="hidden", timeout=10000)


async def upload_videos(page: Page, video_paths: List[Path]) -> None:
    """点击「本地上传」按钮触发 file chooser，批量选择视频，触发上传后不等待完成。"""
    video_paths = [Path(p) for p in video_paths]
    missing = [p for p in video_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"视频文件不存在: {missing}")

    btn = page.locator('[class*="uploadContent"] button:has-text("本地上传")')
    if await btn.count() == 0:
        btn = page.locator(SELECTORS["local_upload_button"])
    await btn.first.scroll_into_view_if_needed()

    async with page.expect_file_chooser(timeout=15000) as fc_info:
        await btn.first.click()
    file_chooser = await fc_info.value
    await file_chooser.set_files([str(p) for p in video_paths])

    # 给上传组件初始化时间
    await page.wait_for_timeout(3000)


async def wait_for_uploads_complete(page: Page, expected: int, timeout_s: int = 900) -> None:
    """通过监听控制台的 VIDEO_UPLOAD_FULL_FLOW_SUCCESS 事件，等待所有视频上传完成。"""
    import asyncio

    done_count = {"n": 0}

    def _on_console(msg):
        if "VIDEO_UPLOAD_FULL_FLOW_SUCCESS" in msg.text:
            done_count["n"] += 1

    page.on("console", _on_console)
    try:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        grace = loop.time() + 120  # 0 进度宽限期
        while loop.time() < deadline:
            if done_count["n"] >= expected:
                # 再给页面一点时间把视频写入表单状态
                await page.wait_for_timeout(2000)
                return
            if await accept_invite_modal(page):
                modal_seen["b"] = True
            # 接受过弹窗但依然 0 进度 → 提前抛出，让上层重传
            if modal_seen["b"] and done_count["n"] == 0 and loop.time() > grace:
                raise TimeoutError("被邀请弹窗阻断，0 完成，需重试上传")
            await asyncio.sleep(2)
        raise TimeoutError(
            f"视频上传等待超时：完成 {done_count['n']} / 预期 {expected}"
        )
    finally:
        page.remove_listener("console", _on_console)


async def click_save(page: Page) -> None:
    """点击保存按钮，确保触发保存事件。"""
    save_btn = page.locator('button[data-size="lg"][data-type="neutral"] .Button__content:has-text("保存")')
    if await save_btn.count() == 0:
        save_btn = page.locator(SELECTORS["save_button"])
    btn = save_btn.first
    await btn.wait_for(state="visible", timeout=10000)
    await btn.scroll_into_view_if_needed()

    # 确保按钮已启用
    for _ in range(5):
        parent = page.locator('button[data-size="lg"][data-type="neutral"]:has-text("保存")').first
        disabled = await parent.get_attribute("aria-disabled")
        if disabled != "true":
            break
        await page.wait_for_timeout(1000)

    # 用 evaluate 直接在 button 元素上触发点击，绕过可能的遮挡
    await parent.evaluate("el => el.click()")
    print("[click_save] 已通过 JS click 触发保存按钮")

    # 等待保存请求完成
    await page.wait_for_timeout(5000)


async def fill_and_save(page, drama) -> None:
    """对一个 draft 页完成：填表、上传、保存。"""
    print(f"[row {drama.row_idx}] 填写基础信息...")
    await fill_basic_info(page, drama)
    print(f"[row {drama.row_idx}] 设置下拉框...")
    await set_dropdowns(page)
    print(f"[row {drama.row_idx}] 设置开关/单选...")
    await set_switches_and_radios(page)
    # 选择下拉框后总集数会被清空，需要重新填入
    await page.fill(SELECTORS["total_video_num"], str(drama.episode_count))
    await close_overlays(page)
    print(f"[row {drama.row_idx}] 上传封面...")
    await upload_cover(page, drama.cover_path)
    await close_overlays(page)
    print(f"[row {drama.row_idx}] 上传 {len(drama.video_paths)} 个视频...")
    await upload_videos(page, drama.video_paths)
    print(f"[row {drama.row_idx}] 等待视频上传完成...")
    await wait_for_uploads_complete(page, expected=len(drama.video_paths))
    await close_overlays(page)
    print(f"[row {drama.row_idx}] 点击保存...")
    await click_save(page)
