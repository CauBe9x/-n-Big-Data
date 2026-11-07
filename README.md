# VietJobs Lab: phân tích thị trường tuyển dụng, dự đoán lương và kỹ năng

Đồ án môn Công nghệ Dữ liệu lớn, UIT.

**Đề bài:** xây dựng bộ dữ liệu từ các trang tuyển dụng về mức lương, vị trí, kỹ năng; dùng máy học để dự đoán lương và kỹ năng cần thiết; xây dựng giao diện minh chứng.

**Dữ liệu:** VietJobs, 48.092 dòng tin tuyển dụng TopCV, 18 trường, 16 nhóm ngành ([Hugging Face](https://huggingface.co/datasets/dinhieufam/VietJobs), [bài báo LREC 2026](https://arxiv.org/abs/2603.05262), [mã nguồn gốc](https://github.com/VinNLP/VietJobs)).

## Mục tiêu

1. Làm sạch và lưu trữ dữ liệu tuyển dụng có cấu trúc, có kiểm chứng.
2. Trả lời: thị trường đang trả bao nhiêu, một vị trí nên có mức lương nào, vị trí đó cần kỹ năng gì.
3. Thể hiện quy trình Big Data từ dữ liệu thô tới dashboard, chạy thật trên một máy.

## Khởi chạy nhanh

Cần Python 3.12, Node.js 18+, PostgreSQL đã cài (không cần Docker, không cần mật khẩu của server có sẵn). Máy mới cần có mạng ở lần đầu để cài thư viện và tải dữ liệu.

Bấm đúp `run.bat`, hoặc gõ trong PowerShell:

```powershell
.\run.bat
```

Mở **http://localhost:8000**. Script tự làm các bước còn thiếu: môi trường Python, CSDL riêng ở cổng 5433, dữ liệu và mô hình, build frontend. Tắt: Ctrl+C, rồi `stop.bat`.

| Lần chạy | Thời gian |
|---|---|
| Đã có dữ liệu | vài giây |
| Có `data/snapshot/vietjobs.dump` và mô hình | khoảng 1 phút |
| Chạy toàn bộ pipeline từ đầu | khoảng 30 phút trên máy 4 lõi, 12 GB RAM; thêm khoảng 8 phút cho Spark, MLlib và benchmark |

Phần Spark cài riêng một lần, cần Java 17 trở lên:

```bat
backend\.venv\Scripts\python scripts\setup_spark.py
cd backend
.venv\Scripts\python -m pipeline.spark_job --ml
.venv\Scripts\python -m pipeline.spark_job --benchmark
```

Hướng dẫn trình diễn: [DEMO_GUIDE.md](DEMO_GUIDE.md).

### Sau khi clone từ GitHub

GitHub không chứa dataset, mô hình và CSDL. Có hai cách lấy:

| Cách | Làm gì | Thời gian |
|---|---|---|
| **Dùng gói dữ liệu** (nên dùng) | Giải nén `vietjobs-du-lieu-demo.zip` vào thư mục `vietjobs-app`, rồi chạy `.\run.bat` | vài phút |
| Tự chạy lại | Chạy thẳng `.\run.bat`, script tự tải dataset từ Hugging Face rồi chạy pipeline | khoảng 30 phút |

Trang Pipeline cần thêm `python scripts/setup_spark.py` nếu muốn chạy Spark trực tiếp; không cài thì kết quả Spark có sẵn trong gói dữ liệu vẫn hiển thị, nút chạy bị khoá.

## Công nghệ

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Cơ sở dữ liệu | PostgreSQL (kiểm thử trên 18.3) | 20 bảng, 4 view, 23 khoá ngoại |
| Xử lý | pandas, Apache Spark 4.3 (`local[*,8]`), Parquet | ETL phục vụ ứng dụng; Lakehouse Bronze/Silver/Gold và đối soát |
| Máy học | scikit-learn, LightGBM, mlxtend, Spark MLlib | 3 mô hình, FP-Growth, K-Means; MLlib để đối chứng |
| Backend | FastAPI, SQLAlchemy 2 | REST API, điều phối job |
| Frontend | React 18, Vite 5, Recharts | Dashboard và các trang chức năng |
| BI (tuỳ chọn) | Apache Superset | Dashboard riêng của nhóm, không cần cho demo |

Không dùng Kafka, HDFS, YARN, Airflow: dữ liệu là file tĩnh trên một máy. Lý do chi tiết ở [ARCHITECTURE.md](ARCHITECTURE.md).

## Kiến trúc

```mermaid
flowchart LR
  CSV[VietJobs.csv] --> ETL[ETL pandas] --> PG[(PostgreSQL)]
  PG --> ML[Máy học, khai phá] --> PG
  CSV --> S[Spark: Bronze, Silver, Gold]
  S --> R{Đối soát}
  PG --> R
  PG --> API[FastAPI] --> WEB[React]
  R --> API
```

Tài liệu: [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md), [DEMO_GUIDE.md](DEMO_GUIDE.md), [PRESENTATION_NOTES.md](PRESENTATION_NOTES.md).

## Các trang

| Trang | Đường dẫn | Chức năng |
|---|---|---|
| Trang chủ | `/` | Số liệu chính, trạng thái hệ thống, lối vào các chức năng |
| Dashboard thị trường | `/dashboard` | Lương, ngành, địa lý, kỹ năng; lọc theo 5 chiều và lọc chéo; nhận định sinh từ số liệu |
| Tra cứu tin | `/jobs` | Tìm không dấu, lọc, xem chi tiết, ước tính lương cho tin thoả thuận |
| Dự đoán lương | `/predict/salary` | Mức lương, khoảng 80%, yếu tố ảnh hưởng |
| Gợi ý kỹ năng | `/predict/skills` | Kỹ năng chuyên môn và kỹ năng mềm kèm xác suất |
| Phân loại ngành | `/predict/category` | Top 5 ngành từ tiêu đề và mô tả |
| Đánh giá mô hình | `/models` | So sánh mô hình, đối chiếu bài báo, sai số theo ngành |
| Khai phá dữ liệu | `/mining/*` | Kỹ năng và lương, luật kết hợp, phân cụm |
| Pipeline Big Data | `/pipeline` | Luồng dữ liệu, chạy job trực tiếp, đối soát, kết quả Spark, benchmark, nhật ký |
| Chất lượng dữ liệu | `/data` | Thiếu, trùng, bất thường, trước và sau làm sạch, lược đồ |
| Kiến trúc | `/about` | Bài toán, các tầng, lý do chọn công nghệ, giới hạn |

## Cấu hình

Sao chép `.env.example` thành `.env` (`run.bat` tự làm).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | cổng 5433 | Đổi sang 5432 nếu dùng `docker compose up -d postgres` |
| `DASHBOARD_URL` | `http://localhost:8088/superset/dashboard/vietjobs/` | Mục Superset trong menu chỉ hiện khi địa chỉ này phản hồi |
| `CORS_ORIGINS` | cổng 5173 | Chỉ cần khi chạy Vite riêng |

Biến tuỳ chọn: `VIETJOBS_CSV`, `VIETJOBS_PORT`, `PG_BIN`, `VIETJOBS_PG_PORT`.

## Chạy từng phần

```bat
python scripts\local_db.py start            :: CSDL
cd backend
.venv\Scripts\python -m pipeline.run_all    :: toàn bộ pipeline
.venv\Scripts\python -m pipeline.reconcile  :: đối soát trên dòng lệnh
.venv\Scripts\uvicorn app.main:app --port 8000
cd ..\frontend && npm run dev               :: phát triển giao diện ở cổng 5173
```

Dùng Docker thay cụm riêng: `docker compose up -d postgres`, rồi đổi `DATABASE_URL` sang cổng 5432.

Superset (chưa chạy lại trong đợt nâng cấp này, cần Python 3.11 hoặc Docker): dùng `bi/run_superset.bat`, rồi đặt `VIETJOBS_DB_URI=postgresql+psycopg2://vietjobs:vietjobs@127.0.0.1:5433/vietjobs` và `SUPERSET_METADATA_URI` tương ứng trước khi chạy `bi/setup_dashboard.py`.

Tạo lại gói dữ liệu sau khi chạy lại pipeline: `python scripts\local_db.py dump`, rồi `python scripts\pack_data.py`.

## Kiểm thử

```bat
cd backend
.venv\Scripts\python -m pytest -q
```

57 test gồm làm sạch dữ liệu, lược đồ, toàn bộ API, tính đúng của số liệu dashboard, xử lý lỗi, đối soát và cơ chế dừng job treo.

## Kết quả (tập test, chia 80/10/10 theo tin)

**Dự đoán lương** (25.819 tin có lương, sai số tính bằng triệu đồng/tháng)

| Mô hình | RMSE | MAE | R² |
|---|---:|---:|---:|
| Baseline: trung vị theo ngành | 8,82 | 5,15 | −0,06 |
| Ridge (α = 3) | 6,30 | 3,68 | 0,456 |
| **LightGBM** (triển khai) | **5,76** | **3,41** | **0,546** |
| LightGBM, chỉ các trường như bài báo | 5,86 | 3,44 | 0,531 |

Khoảng dự đoán 80% bao phủ 80,2% giá trị thật. Bài báo gốc đạt RMSE 10,24, R² 0,23 (Llama-SEA-LION-v3-8B-IT, fine-tune trên cả hai bộ dữ liệu); hai số không so sánh trực tiếp được vì bài báo không gộp tin trùng.

**Gợi ý kỹ năng** (300 nhãn): OvR Logistic Regression chỉ dùng chức danh đạt P@5 = 0,333, R@10 = 0,534, so với baseline phổ biến theo ngành P@5 = 0,277.

**Phân loại 16 ngành:** Linear SVM cân bằng lớp đạt Accuracy 0,719, Macro-F1 0,676. Accuracy này tính đúng nếu ngành dự đoán thuộc tập ngành của tin; so chặt với ngành chính là 0,658. Bài báo (Qwen2.5-7B few-shot) đạt 0,47 và 0,42.

**Khai phá:** FP-Growth trên 36.263 giao dịch sinh 1.116 tập phổ biến, lưu 431 luật. K-Means chọn k = 40 trong khoảng 8–40.

**Spark:** đối soát với PostgreSQL đạt 24/24 kiểm tra. MLlib đối chứng (chia 80/20): LinearRegression R² 0,36, GBT R² 0,33. Ở dữ liệu thật pandas nhanh hơn Spark; từ khoảng 700 nghìn dòng trở lên Spark nhanh hơn. Số đo chi tiết ở trang Pipeline và [PRESENTATION_NOTES.md](PRESENTATION_NOTES.md).

## Cấu trúc thư mục

```
vietjobs-app/
├── backend/
│   ├── app/            FastAPI: analytics, jobrunner, db, routers/
│   ├── pipeline/       cleaning, etl, quality, reconcile, train_*, mining, spark_job
│   ├── artifacts/      mô hình .joblib
│   └── tests/
├── frontend/           React + Vite (src/pages, src/components)
├── spark/              spark_pipeline.py, benchmark.py; original/ giữ bản gốc của nhóm
├── database/           schema.sql, pipeline_runs.sql, queries.sql
├── bi/                 Superset
├── scripts/            start.py, local_db.py, setup_spark.py, download_data.py
├── data/               raw/, processed/, lake/, snapshot/, logs/
├── docs/               ERD và sơ đồ gốc của nhóm
└── run.bat, stop.bat, run.sh, docker-compose.yml
```

## Giới hạn

- Spark chạy trên một máy: có song song theo lõi CPU, không có xử lý phân tán nhiều máy.
- Hệ thống xử lý batch, không có xử lý thời gian thực.
- Dữ liệu khoảng 100 MB, nằm gọn trong RAM; ở cỡ này pandas nhanh hơn Spark.
- Không có ngày đăng tin, nên không có phân tích xu hướng theo thời gian.
- Khoảng 29% tin không công bố lương; kết quả lương chỉ đại diện cho nhóm công bố.
- Kỹ năng do LLM trích xuất nên còn nhiễu. Chênh lệch lương theo kỹ năng là tương quan.
- API không có xác thực, chỉ dùng trên localhost.
