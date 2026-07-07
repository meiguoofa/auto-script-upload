"""监控服务端批次完成，自动下载 xlsx 并触发 upload.py。

用法:
    python monitor.py <batch_id>
    python monitor.py <batch_id> --no-upload          # 只下载 xlsx
    python monitor.py <batch_id> --limit 1            # 仅处理前 1 部剧
    python monitor.py <batch_id> --interval 60        # 自定义轮询间隔
    python monitor.py <batch_id> --server http://...  # 自定义服务端
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import requests

DEFAULT_SERVER = "http://45.78.235.74:5173"
POLL_INTERVAL = 30  # 秒
DOWNLOAD_DIR = Path(__file__).parent / "downloads"


def check_batch_status(server: str, batch_id: str) -> dict:
    r = requests.get(f"{server}/api/daily-new/batches/{batch_id}", timeout=10)
    r.raise_for_status()
    d = r.json()
    return {
        "total": d.get("total_jobs", 0),
        "done": d.get("done_count", 0),
        "failed": d.get("failed_count", 0),
        "pending": d.get("pending_count", 0),
    }


def wait_for_completion(server: str, batch_id: str, interval: int) -> dict:
    print(f"[monitor] 开始监控批次 {batch_id}（每 {interval}s 轮询一次，Ctrl+C 退出）")
    last = None
    while True:
        try:
            s = check_batch_status(server, batch_id)
        except Exception as e:
            print(f"  [warn] 查询失败: {e}，{interval}s 后重试")
            time.sleep(interval)
            continue
        if s != last:
            print(f"  total={s['total']} done={s['done']} failed={s['failed']} pending={s['pending']}")
            last = s
        if s["total"] > 0 and s["done"] + s["failed"] == s["total"]:
            return s
        time.sleep(interval)


def download_xlsx(server: str, batch_id: str) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out = DOWNLOAD_DIR / f"batch_{batch_id[:8]}.xlsx"
    r = requests.get(
        f"{server}/api/daily-new/batches/{batch_id}/export",
        params={"format": "xlsx"},
        timeout=60,
    )
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"[monitor] xlsx 已下载: {out} ({len(r.content) / 1024:.1f} KB)")
    return out


def trigger_upload(xlsx_path: Path, limit: int | None = None) -> int:
    cmd = [sys.executable, "upload.py", str(xlsx_path)]
    if limit:
        cmd.extend(["--limit", str(limit)])
    print(f"[monitor] 触发上传: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=Path(__file__).parent)


def main():
    p = argparse.ArgumentParser(description="监控服务端批次完成并自动上传")
    p.add_argument("batch_id", help="要监控的 batch_id (UUID)")
    p.add_argument("--server", default=DEFAULT_SERVER, help="服务端地址")
    p.add_argument("--interval", type=int, default=POLL_INTERVAL, help="轮询间隔秒数（默认 30）")
    p.add_argument("--limit", type=int, default=None, help="仅处理前 N 部剧（测试用）")
    p.add_argument("--no-upload", action="store_true", help="只下载 xlsx 不触发 upload.py")
    args = p.parse_args()

    status = wait_for_completion(args.server, args.batch_id, args.interval)
    print(f"[monitor] 批次完成: done={status['done']} failed={status['failed']} total={status['total']}")
    if status["failed"] > 0:
        print(f"[monitor] 警告: 有 {status['failed']} 个任务失败，xlsx 中将缺少这些剧的数据")

    xlsx = download_xlsx(args.server, args.batch_id)

    if args.no_upload:
        print("[monitor] --no-upload 模式，不触发 upload.py")
        return

    code = trigger_upload(xlsx, limit=args.limit)
    print(f"[monitor] upload.py 退出码: {code}")
    sys.exit(code)


if __name__ == "__main__":
    main()
