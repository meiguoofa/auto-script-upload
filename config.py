"""常量、selector 与默认值配置。"""

from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
USER_DATA_DIR = str(BASE_DIR / "browser_data")
DOWNLOAD_DIR = BASE_DIR / "downloads"
ERROR_DIR = BASE_DIR / "errors"

TARGET_LIST_URL = "https://www.tiktokdramacenter.com/series/list"
DRAFT_URL_PREFIX = "https://www.tiktokdramacenter.com/series/draft"
BROWSER_CHANNEL = "msedge"
MAX_PARALLEL_TABS = 10
HEADLESS = False
VIEWPORT = {"width": 1440, "height": 900}

# 从 attr_require.txt 提炼的默认值
DEFAULTS = {
    "preview_video_num": "8",
    "preview_video_num_on_profile": "3",
    "target_audience": "男性",
    "source_language": "中文",
    "is_ai_drama": "是",
    "publish_method": "手动发布",
    "contract": "MINTAI PTE. LTD.",
}

# 表单字段 selector / 定位文本
SELECTORS = {
    # 文本输入
    "title": "#title",
    "description": "#description",
    "total_video_num": "#totalVideoNum",
    "preview_video_num": "#previewVideoNum",
    "preview_video_num_on_profile": "#previewVideoNumOnProfile",
    # 复选/开关
    "consignment_status": "#consignmentStatus",
    "signed": "#signed input[type='checkbox']",
    # 单选：按 label 文本选
    "publish_radio": 'input[name="default"]',
    # 上传
    "local_upload_button": 'button:has-text("本地上传")',
    "cover_upload_area": 'div:has-text("封面图")',  # 在其下再找上传区
    # 操作按钮
    "create_button": 'div.Button__content:has-text("新建")',
    "save_button": 'button[data-size="lg"][data-type="neutral"]:has-text("保存")',
    "submit_button": 'button:has-text("提交")',
    "discard_button": 'button:has-text("放弃更改")',
}

# 字段标签 → 下拉框 placeholder/aria 文本 的映射
COMBOBOX_PLACEHOLDERS = {
    "关联合同": "请选择合同",
    "目标人群": "选择内容主要面向的目标人群",
    "源语言": "请选择剧集的源语言",
    "AI 短剧": "请选择是否 AI 短剧",
}
