"""视频文件大小与时长校验。"""

from pathlib import Path
from typing import List

import cv2


# 平台要求：大小 ≥ 5 MB 且 ≤ 4 GB，单集时长 ≥ 15 秒且 ≤ 20 分钟
MIN_SIZE_BYTES = 5 * 1024 * 1024
MAX_SIZE_BYTES = 4 * 1024 * 1024 * 1024
MIN_DURATION_SECONDS = 15
MAX_DURATION_SECONDS = 20 * 60


def _video_duration(path: Path) -> float:
    """使用 OpenCV 读取视频时长（秒）。"""
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0:
            raise ValueError(f"无法获取视频 fps: {path}")
        return frame_count / fps
    finally:
        cap.release()


def filter_videos(paths: List[Path]) -> List[Path]:
    """
    过滤掉不符合平台要求的视频。
    返回通过校验的视频路径列表，并打印被过滤掉的文件及原因。
    """
    valid: List[Path] = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            print(f"[FILTER] 文件不存在，跳过: {p.name}")
            continue

        size = p.stat().st_size
        if size < MIN_SIZE_BYTES or size > MAX_SIZE_BYTES:
            print(
                f"[FILTER] 大小不符合要求 ({size / 1024 / 1024:.2f} MB)，跳过: {p.name}"
            )
            continue

        try:
            duration = _video_duration(p)
        except Exception as e:
            print(f"[FILTER] 无法读取时长 ({e})，跳过: {p.name}")
            continue

        if duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS:
            print(
                f"[FILTER] 时长不符合要求 ({duration:.1f} s)，跳过: {p.name}"
            )
            continue

        valid.append(p)

    print(f"[FILTER] 通过 {len(valid)} / 总计 {len(paths)}")
    return valid
