"""数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Drama:
    """一部剧的完整数据，从 Excel 一行解析而来。"""

    row_idx: int
    original_title: str
    original_desc: str
    author: str
    category: str
    original_cover_url: str
    translation_language: str
    title: str          # 翻译后剧名 → 表单「剧集名」
    description: str    # 翻译后简介 → 表单「剧集描述」
    cover_url: str      # 新海报 URL → 表单「封面图」
    episode_count: int  # 剧集数 → 表单「总集数」
    video_urls: List[str] = field(default_factory=list)

    # 下载后填充
    cover_path: Path = None
    video_paths: List[Path] = field(default_factory=list)

    # 执行结果
    status: str = "pending"   # pending / downloading / ready / processing / done / failed
    error: str = ""
    draft_url: str = ""
