"""Tải dataset VietJobs (dinhieufam/VietJobs) từ Hugging Face về data/raw/VietJobs.csv.

Cách chạy (từ thư mục gốc dự án):
    python scripts/download_data.py

Ưu tiên dùng thư viện huggingface_hub; nếu chưa cài thì tải trực tiếp qua URL.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
TARGET = RAW_DIR / "VietJobs.csv"
REPO_ID = "dinhieufam/VietJobs"
FILENAME = "VietJobs.csv"
DIRECT_URL = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main/{FILENAME}"


def _progress(block_num: int, block_size: int, total_size: int) -> None:
    if total_size <= 0:
        return
    done = min(block_num * block_size, total_size)
    pct = done * 100 / total_size
    sys.stdout.write(f"\r  Đang tải: {pct:5.1f}% ({done / 1e6:.1f}/{total_size / 1e6:.1f} MB)")
    sys.stdout.flush()


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() and TARGET.stat().st_size > 1_000_000:
        print(f"Đã có dữ liệu: {TARGET} ({TARGET.stat().st_size / 1e6:.1f} MB) – bỏ qua bước tải.")
        return

    try:
        from huggingface_hub import hf_hub_download  # type: ignore

        print(f"Tải {REPO_ID}/{FILENAME} bằng huggingface_hub ...")
        path = hf_hub_download(repo_id=REPO_ID, filename=FILENAME, repo_type="dataset", local_dir=str(RAW_DIR))
        print(f"Xong: {path}")
        return
    except ImportError:
        print("Chưa cài huggingface_hub → tải trực tiếp qua HTTPS.")
    except Exception as exc:  # mạng chập chờn, bị chặn, ...
        print(f"huggingface_hub lỗi ({exc}) → thử tải trực tiếp.")

    print(f"URL: {DIRECT_URL}")
    tmp = TARGET.with_suffix(".part")
    urllib.request.urlretrieve(DIRECT_URL, tmp, reporthook=_progress)
    tmp.replace(TARGET)
    print(f"\nXong: {TARGET} ({TARGET.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
