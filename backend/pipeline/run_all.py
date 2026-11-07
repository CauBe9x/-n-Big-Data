"""Chạy toàn bộ pipeline: tải dữ liệu -> ETL -> huấn luyện 3 mô hình -> khai phá dữ liệu.

    cd backend
    python -m pipeline.run_all            # chạy tất cả
    python -m pipeline.run_all --skip-etl # dùng lại CSDL / bảng sạch đã có
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import warnings

from app.config import RAW_CSV, ROOT_DIR

warnings.filterwarnings("ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-etl", action="store_true")
    ap.add_argument("--only", choices=["quality", "salary", "skills", "category", "mining"])
    args = ap.parse_args()
    t0 = time.time()

    if not RAW_CSV.exists():
        print("Chưa có dữ liệu -> tải từ Hugging Face")
        subprocess.check_call([sys.executable, str(ROOT_DIR / "scripts" / "download_data.py")])

    from . import etl, mining, quality, train_category, train_salary, train_skills

    if not args.skip_etl and not args.only:
        etl.run()
    steps = {"quality": quality.run, "salary": train_salary.run, "skills": train_skills.run,
             "category": train_category.run, "mining": mining.run}
    for name, fn in steps.items():
        if args.only and args.only != name:
            continue
        print()
        fn()
    print(f"\nHoàn tất toàn bộ pipeline trong {(time.time() - t0) / 60:.1f} phút.")


if __name__ == "__main__":
    main()
