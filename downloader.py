"""并发下载封面图与视频文件。"""

import asyncio
import hashlib
from pathlib import Path
from typing import List

import aiofiles
import aiohttp

from config import DOWNLOAD_DIR
from models import Drama


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def _ext_from_url(url: str) -> str:
    """从 URL 路径提取扩展名；取不到时按视频/图片给一个默认扩展名。"""
    path = url.split("?")[0].split("#")[0]
    ext = Path(path).suffix.lower()
    if ext in {".mp4", ".mov", ".webm", ".mkv", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return ext
    # 兜底：视频默认 mp4，图片默认 png
    if any(k in url.lower() for k in ["video", ".mp4"]):
        return ".mp4"
    return ".png"


async def _download_one(
    session: aiohttp.ClientSession,
    url: str,
    dest: Path,
    retries: int = 2,
) -> Path:
    """下载单个文件，失败时重试；已存在则跳过。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    last_err = None
    for attempt in range(retries + 1):
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                resp.raise_for_status()
                async with aiofiles.open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)
                return dest
        except Exception as e:
            last_err = e
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"下载失败 {url}: {last_err}")


async def ensure_downloads(dramas: List[Drama], max_concurrency: int = 10) -> List[Drama]:
    """为所有 Drama 下载封面与视频，填充 cover_path / video_paths。"""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(max_concurrency)

    async def _bound_download(session, url, dest):
        async with sem:
            return await _download_one(session, url, dest)

    async with aiohttp.ClientSession() as session:
        tasks = []
        path_map = {}  # task -> (drama, field, index)

        for d in dramas:
            d.status = "downloading"
            # 封面
            if d.cover_url:
                ext = _ext_from_url(d.cover_url)
                dest = DOWNLOAD_DIR / f"cover_{d.row_idx}_{_url_hash(d.cover_url)}{ext}"
                coro = _bound_download(session, d.cover_url, dest)
                tasks.append(coro)
                path_map[id(coro)] = ("cover", d, None)
            # 视频
            d.video_paths = []
            for i, url in enumerate(d.video_urls, start=1):
                ext = _ext_from_url(url)
                dest = DOWNLOAD_DIR / f"video_{d.row_idx}_ep{i}_{_url_hash(url)}{ext}"
                coro = _bound_download(session, url, dest)
                tasks.append(coro)
                path_map[id(coro)] = ("video", d, i - 1)

        if not tasks:
            return dramas

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for coro, result in zip(tasks, results):
            field, d, idx = path_map[id(coro)]
            if isinstance(result, Exception):
                d.status = "failed"
                d.error = f"下载失败: {result}"
                continue
            if field == "cover":
                d.cover_path = result
            else:
                # 保持顺序
                while len(d.video_paths) <= idx:
                    d.video_paths.append(None)
                d.video_paths[idx] = result

        # 标记完成
        for d in dramas:
            if d.status != "failed":
                missing_videos = [p for p in d.video_paths if p is None]
                if missing_videos:
                    d.status = "failed"
                    d.error = "部分视频未成功下载"
                else:
                    d.status = "ready"

    return dramas


if __name__ == "__main__":
    from pathlib import Path
    from reader import read_excel

    async def main():
        dramas = read_excel(Path("export_20260705_180246.xlsx"))
        dramas = await ensure_downloads(dramas)
        for d in dramas:
            print(f"[{d.row_idx}] {d.title}: cover={d.cover_path}, videos={d.video_paths}")

    asyncio.run(main())
