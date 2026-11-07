# Từ điển dữ liệu

Tài liệu này mô tả dữ liệu đầu vào, các quy tắc làm sạch, lược đồ PostgreSQL và các tầng Parquet. Số liệu đo trên `VietJobs.csv`; bản cập nhật theo thời gian thực nằm ở trang **Chất lượng dữ liệu** của ứng dụng (`/data`).

## 1. Nguồn dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Bộ dữ liệu | VietJobs, Hugging Face `dinhieufam/VietJobs` |
| Bài báo | *VietJobs: A Vietnamese Job Advertisement Dataset*, arXiv:2603.05262, LREC 2026 |
| Nguồn gốc | Tin tuyển dụng công khai trên TopCV, trích xuất trường có cấu trúc bằng LLM |
| Kích thước | 48.092 dòng, 18 cột, 103 MB |
| Giấy phép | Repo GitHub `VinNLP/VietJobs` ghi MIT; không thấy ghi rõ giấy phép riêng cho dữ liệu |

**Thời gian thu thập không thống nhất giữa các nguồn.** Repo GitHub ghi "July – October 2025", bài báo ghi thu thập trong tháng 7/2025 (Bảng 1: 1 tuần). File dữ liệu không có cột ngày nào nên không tự kiểm chứng được. Ứng dụng dùng nhãn 07–10/2025 theo repo chính thức.

## 2. File gốc `VietJobs.csv`

| Cột | Kiểu | Thiếu | Giá trị khác nhau | Ý nghĩa |
|---|---|---:|---:|---|
| `job_title` | chuỗi | 0% | 16.720 | Chức danh |
| `location` | chuỗi | 0% | 984 | Địa điểm thô |
| `country` | chuỗi | 0% | 10 | Quốc gia |
| `qualifications` | chuỗi list | 0,8% | 18.167 | Bằng cấp |
| `technical_skills` | chuỗi list | 13,4% | 26.426 | Kỹ năng chuyên môn do LLM trích xuất |
| `soft_skills` | chuỗi list | 5,5% | 31.790 | Kỹ năng mềm do LLM trích xuất |
| `languages_required` | chuỗi | 74,4% | 123 | Ngoại ngữ; trống nghĩa là không yêu cầu |
| `experience_required` | chuỗi | 0% | 19 | Kinh nghiệm dạng chữ |
| `salary` | chuỗi | 0% | 839 | Chuỗi lương gốc |
| `contract_type` | chuỗi | 0% | 9 | Loại hợp đồng |
| `working_hours` | chuỗi | 10,4% | 9.786 | Thời gian làm việc |
| `benefits` | chuỗi list | 0,1% | 36.555 | Phúc lợi |
| `description` | chuỗi | 0% | 34.560 | Mô tả công việc |
| `requirements_text` | chuỗi | 0,02% | 35.331 | Yêu cầu ứng viên |
| `category` | chuỗi | 0% | 16 | Ngành TopCV |
| `salary_min` | số nguyên | 0% | 57 | Lương tối thiểu, triệu/tháng; 0 khi thoả thuận |
| `salary_max` | số nguyên | 0% | 69 | Lương tối đa, triệu/tháng; 0 khi thoả thuận |
| `salary_avg` | chuỗi | 0% | 88 | Lương trung bình dạng chữ |

## 3. Vấn đề phát hiện và cách xử lý

| Vấn đề đo được | Xử lý | Ở đâu |
|---|---|---|
| 11.507 dòng trùng tin; 385 dòng trùng hoàn toàn | Gộp theo (`job_title`, `location`, `description`), còn 36.585 tin; `jobs.source_rows` lưu số dòng đã gộp | `etl.clean_dataframe` |
| 7.588 tin xuất hiện ở nhiều ngành | Lưu N–N trong `job_categories`; ngành chính là ngành phổ biến nhất với cùng chức danh trên toàn bộ dữ liệu | `etl.clean_dataframe` |
| 984 cách ghi địa điểm | Bí danh quận/huyện về 54 giá trị (tỉnh/thành, Nước ngoài, Khác) và miền | `cleaning.normalize_location` |
| 30.426 tên kỹ năng chuyên môn, 19.600 tên kỹ năng mềm | Bỏ tiền tố/hậu tố, gộp bí danh, còn 22.445 và 14.748 | `cleaning.normalize_skill` |
| 28,6% dòng ghi thoả thuận | Lương để NULL, `is_negotiable = true`; không suy đoán vào dữ liệu | `cleaning.parse_salary` |
| Lương tới 500 triệu/tháng; 29 dòng trên ngưỡng | Giữ trong CSDL, chỉ dùng khoảng 1–150 triệu cho thống kê và huấn luyện | `analytics`, `train_salary` |
| Không có cột ngày | Không phân tích xu hướng theo thời gian | Giới hạn của dữ liệu |

Lương trung bình của một tin là trung bình cộng `salary_min` và `salary_max`. File gốc không bị sửa: bản chép ở `data/raw/` và mọi xử lý đều tái tạo được.

## 4. Lược đồ PostgreSQL

Định nghĩa đầy đủ ở [`database/schema.sql`](database/schema.sql) và [`database/pipeline_runs.sql`](database/pipeline_runs.sql). Tổng cộng 20 bảng, 4 view, 23 khoá ngoại. Sơ đồ ERD 19 bảng nghiệp vụ: [`docs/erd.png`](docs/erd.png). Bảng `pipeline_runs` đứng riêng, không có khoá ngoại.

### Dữ liệu tuyển dụng

| Bảng | Khoá chính | Nội dung | Số dòng |
|---|---|---|---:|
| `jobs` | `job_id` | Một tin duy nhất; lương NUMERIC, JSONB cho bằng cấp và phúc lợi | 36.585 |
| `provinces` | `province_id` | Tỉnh/thành và miền | 54 |
| `categories` | `category_id` | 16 ngành | 16 |
| `skills` | `skill_id` | `name`, `kind` (technical hoặc soft) | 37.193 |
| `languages` | `language_id` | Ngoại ngữ | 21 |
| `job_categories` | (`job_id`, `category_id`) | N–N, có cờ `is_primary` | 45.526 |
| `job_skills` | (`job_id`, `skill_id`) | N–N | 252.653 |
| `job_languages` | (`job_id`, `language_id`) | N–N | 11.180 |

Các cột dẫn xuất chính của `jobs`:

| Cột | Cách tính |
|---|---|
| `title_key` | Chức danh không dấu, chữ thường, dùng để tìm kiếm |
| `experience_years` | Số năm đổi từ chuỗi: "6 tháng" → 0,5, "Trên 5 năm" → 6 |
| `experience_bucket` | Không yêu cầu, Dưới 1 năm, 1-2 năm, 3-5 năm, Trên 5 năm, Không rõ |
| `salary_min`, `salary_max`, `salary_avg` | Triệu đồng/tháng; NULL khi thoả thuận |
| `is_negotiable` | Đúng khi `salary_avg` là NULL (ràng buộc CHECK) |
| `source_rows` | Số dòng CSV đã gộp; tổng trên toàn bảng phải bằng 48.092 |

### Máy học

| Bảng | Nội dung |
|---|---|
| `ml_training_runs` | Mỗi lần huấn luyện một bài toán, kèm báo cáo JSONB |
| `ml_models` | Các mô hình được so sánh; `is_best` đánh dấu mô hình triển khai |
| `model_metrics` | Chỉ số dạng dài (mô hình, tập, chỉ số, giá trị) |
| `predictions` | Lịch sử dự đoán từ giao diện |

### Khai phá dữ liệu

| Bảng | Nội dung |
|---|---|
| `mining_runs` | Mỗi lần chạy thuật toán, kèm tham số |
| `association_rules`, `rule_antecedents` | 431 luật FP-Growth, vế trái lưu N–N |
| `clusters`, `job_clusters`, `cluster_k_scores` | 40 cụm K-Means, gán từng tin, silhouette theo k |
| `skill_salary_stats` | Lương trung vị theo kỹ năng so với thị trường |

### Vận hành

| Bảng | Nội dung |
|---|---|
| `pipeline_runs` | Nhật ký từng bước: trạng thái, thời gian, dòng vào/ra, báo cáo JSONB. Không bị xoá khi chạy lại ETL |

### View

`v_job_facts`, `v_job_categories`, `v_job_skills`, `v_model_results`: đã JOIN sẵn danh mục, dùng cho Superset.

## 5. Các tầng Parquet (Spark)

Nằm ở `%LOCALAPPDATA%\VietJobs\lake` vì JVM trên Windows không xử lý được đường dẫn có dấu tiếng Việt. Bản JSON của bảng Gold và số đo được chép về `data/lake/` để API đọc.

| Tầng | Nội dung | Số dòng |
|---|---|---:|
| Bronze | 18 cột gốc dạng Parquet, thêm `row_no`; chuỗi thiếu chuẩn hoá thành NULL, không sửa nội dung | 48.092 |
| Silver | Mỗi tin một dòng, đã chuẩn hoá bằng đúng hàm của ETL | 36.585 |
| Gold | `salary_by_category`, `salary_by_experience`, `jobs_by_province`, `top_skills`, `skill_pairs` | 275 |

## 6. Quy ước thống kê

- Lương chỉ tính trên tin công bố lương và nằm trong khoảng 1–150 triệu/tháng.
- Tin thuộc nhiều ngành được tính ở mọi ngành của nó.
- Nhóm dưới 10 tin có lương không hiện trung vị. Kỹ năng dưới 15 tin có lương không tính chênh lệch.
- Chênh lệch lương theo kỹ năng là tương quan, không phải nhân quả.
