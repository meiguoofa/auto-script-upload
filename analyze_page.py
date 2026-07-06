"""
页面分析脚本：打开 TikTok drama center 的剧集详情页，
让用户手动登录（首次）并导航到上传表单，然后抓取页面上所有表单元素，
输出字段清单到 page_fields.json 并在终端打印摘要表。

用法:
    .venv/Scripts/python.exe analyze_page.py

首次运行会弹出浏览器；登录后把上传表单点开，回到终端按回车开始抓取。
登录态会保存在 ./browser_data 目录，下次直接复用。
"""

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.tiktokdramacenter.com/series/detail/7658602410335556625"
USER_DATA_DIR = str(Path(__file__).parent / "browser_data")
OUTPUT_FILE = str(Path(__file__).parent / "page_fields.json")
SCREENSHOT_FILE = str(Path(__file__).parent / "page_form.png")
# 抓取触发信号文件：脚本启动后等待此文件出现才开始抓取。
TRIGGER_FILE = str(Path(__file__).parent / ".scrape_now")
WAIT_TIMEOUT = 60 * 30  # 最多等 30 分钟

# TikTok 反爬较强，用真实安装的 Edge 通道比 Playwright 自带 chromium 更不易被识别。
# 系统已检测到 Edge；如需改用 Chrome，把 channel 改成 "chrome"。
BROWSER_CHANNEL = "msedge"


# 注入到页面里执行的 DOM 抓取逻辑。返回每个可见表单元素的描述。
SCRAPE_JS = r"""
() => {
  const results = [];
  const seen = new Set();

  function getSelector(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    const testid = el.getAttribute('data-testid');
    if (testid) return `[data-testid="${testid}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 5) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      const parent = cur.parentElement;
      if (parent) {
        const sibs = Array.from(parent.children).filter(s => s.tagName === cur.tagName);
        if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(cur)+1})`;
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function getLabel(el) {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.textContent.trim()) return lab.textContent.trim();
    }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const lb = document.getElementById(labelledby);
      if (lb && lb.textContent.trim()) return lb.textContent.trim();
    }
    if (el.placeholder) return el.placeholder;
    if (el.title) return el.title;
    const parent = el.closest('label, [class*="label"], [class*="form"], [class*="item"]');
    if (parent && parent !== el) {
      const txt = parent.textContent.trim().slice(0, 80);
      if (txt) return txt;
    }
    return '';
  }

  const sel = 'input, textarea, select, button, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="listbox"]';
  document.querySelectorAll(sel).forEach(el => {
    if (seen.has(el)) return;
    seen.add(el);
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    results.push({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      name: el.getAttribute('name') || '',
      id: el.id || '',
      testid: el.getAttribute('data-testid') || '',
      placeholder: el.placeholder || '',
      role: el.getAttribute('role') || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      label: getLabel(el),
      required: el.required === true || el.getAttribute('aria-required') === 'true',
      disabled: el.disabled === true,
      readOnly: el.readOnly === true,
      contentEditable: el.getAttribute('contenteditable') === 'true',
      value: el.value || (el.textContent ? el.textContent.trim().slice(0,100) : ''),
      options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.textContent.trim()).filter(Boolean) : [],
      selector: getSelector(el),
      text: (el.tagName === 'BUTTON' || el.getAttribute('contenteditable') === 'true' || el.getAttribute('role') === 'textbox')
            ? el.textContent.trim().slice(0,80) : '',
      x: Math.round(rect.x), y: Math.round(rect.y),
      w: Math.round(rect.width), h: Math.round(rect.height),
    });
  });
  return results;
}
"""


def main():
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    with sync_playwright() as p:
        # channel=msedge 复用系统 Edge；若机器没有 Edge，可去掉 channel 改用自带 chromium。
        try:
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                channel=BROWSER_CHANNEL,
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            print(f"[WARN] 启动 {BROWSER_CHANNEL} 通道失败: {e}")
            print("[WARN] 回退到 Playwright 自带 chromium。")
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )

        page = context.pages[0] if context.pages else context.new_page()
        print(f"[INFO] 打开目标页: {TARGET_URL}")
        page.goto(TARGET_URL, wait_until="domcontentloaded")

        print()
        print("=" * 60)
        print("浏览器已打开。请在浏览器里：")
        print("  1. 如未登录，先完成登录；")
        print("  2. 把【上传表单】点开（点上传按钮、打开弹窗等），")
        print("     让所有要填的字段都显示出来；")
        print("  3. 在聊天里告诉 Claude「好了」，Claude 会创建信号文件触发抓取。")
        print("=" * 60)
        print(f"[INFO] 等待信号文件出现: {TRIGGER_FILE}")
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)

        start = time.time()
        while not os.path.exists(TRIGGER_FILE):
            if time.time() - start > WAIT_TIMEOUT:
                print("[ERR] 等待超时，退出。")
                context.close()
                return
            page.wait_for_timeout(1000)
        os.remove(TRIGGER_FILE)
        print("[INFO] 收到信号，开始抓取...")

        # 抓取前再等一下，确保动态渲染完成
        page.wait_for_timeout(800)

        fields = page.evaluate(SCRAPE_JS)
        title = page.title()
        page.screenshot(path=SCREENSHOT_FILE, full_page=True)

    # 输出 JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"url": TARGET_URL, "title": title, "fields": fields},
                  f, ensure_ascii=False, indent=2)

    # 终端打印摘要表
    print()
    print(f"[OK] 页面标题: {title}")
    print(f"[OK] 抓到 {len(fields)} 个表单元素，已保存到 {OUTPUT_FILE}")
    print(f"[OK] 截图: {SCREENSHOT_FILE}")
    print()
    print("-" * 100)
    print(f"{'#':>3}  {'标签':<6} {'type':<10} {'label/text':<30} {'placeholder':<20} {'必填':<4} {'selector(简)'}")
    print("-" * 100)
    for i, f in enumerate(fields):
        label = (f.get("label") or f.get("text") or "")[:30]
        ph = (f.get("placeholder") or "")[:20]
        req = "Y" if f.get("required") else ""
        sel = f.get("selector", "")
        if len(sel) > 50:
            sel = sel[:47] + "..."
        print(f"{i:>3}  {f['tag']:<6} {f.get('type',''):<10} {label:<30} {ph:<20} {req:<4} {sel}")
    print("-" * 100)
    print()
    print("下一步：把上面这份清单贴给我，并标注每个字段的值从哪里来，")
    print("我再据此实现批量上传脚本。")


if __name__ == "__main__":
    main()
