"""Đóng gói những thứ không nằm trên GitHub để gửi cho bạn cùng nhóm: dataset, mô hình, CSDL, kết quả Spark.

    python scripts/pack_data.py     # tạo ../vietjobs-du-lieu-demo.zip

Người nhận giải nén vào thư mục vietjobs-app (các file tự vào đúng chỗ) rồi chạy run.bat: script khôi phục CSDL trong khoảng
1 phút thay vì chạy pipeline 30 phút. Cần chạy `python scripts/local_db.py dump` trước để có snapshot mới nhất.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "vietjobs-du-lieu-demo.zip"
ITEMS = ["data/snapshot/vietjobs.dump", "data/raw/VietJobs.csv", "backend/artifacts", "data/lake"]


def main() -> None:
    files: list[Path] = []
    for item in ITEMS:
        path = ROOT / item
        if not path.exists():
            sys.exit(f"Thiếu {item}. Chạy pipeline và `local_db.py dump` trước.")
        files += [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in files:
            z.write(f, f.relative_to(ROOT).as_posix())
    print(f"Đã tạo {OUT} ({OUT.stat().st_size / 1e6:.0f} MB, {len(files)} file)")


if __name__ == "__main__":
    main()
