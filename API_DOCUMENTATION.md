# Tài liệu API

Địa chỉ gốc: `http://localhost:8000`. Tài liệu tương tác (Swagger) ở `/docs`. Mọi phản hồi là JSON.

## Quy ước lỗi

| Mã | Khi nào | Nội dung |
|---|---|---|
| 404 | Không có tài nguyên hoặc đường dẫn API | `{"detail": "…"}` |
| 409 | Đang có job chạy, hoặc Spark chưa cài | `{"detail": "…"}` |
| 422 | Tham số không hợp lệ | `{"detail": […]}` hoặc `{"detail": "…"}` |
| 503 | Không kết nối được CSDL, thiếu bảng, chưa có mô hình hoặc kết quả | `{"detail": "hướng dẫn khắc phục"}` |

## Hệ thống

### `GET /api/health`

Trạng thái CSDL, số tin, mô hình và Superset.

```json
{"status": "ok", "database": "PostgreSQL 18.3", "jobs": 36585,
 "models": {"salary": true, "skills": true, "category": true},
 "dashboard_url": "http://localhost:8088/superset/dashboard/vietjobs/", "dashboard_online": false}
```

### `GET /api/meta`

Danh mục cho bộ lọc: `categories`, `provinces`, `contract_types`, `experience_buckets`, `skills`, `languages`.

## Dashboard

### `GET /api/dashboard`

Toàn bộ số liệu của một trạng thái bộ lọc. Tính bằng SQL trên PostgreSQL, cache 10 phút theo bộ lọc.

| Tham số | Kiểu | Mô tả |
|---|---|---|
| `region` | enum | `Miền Bắc`, `Miền Trung`, `Miền Nam`, `Khác` |
| `province` | chuỗi | Tên tỉnh, từ `/api/meta` |
| `category` | chuỗi | Slug ngành, từ `/api/meta` |
| `experience` | enum | `Không yêu cầu`, `Dưới 1 năm`, `1-2 năm`, `3-5 năm`, `Trên 5 năm`, `Không rõ` |
| `contract_type` | chuỗi | Loại hợp đồng |

| Trường trả về | Nội dung |
|---|---|
| `kpi`, `market` | Số tin, số tin có lương, P25, trung vị, P75, trung bình, % thoả thuận, % yêu cầu ngoại ngữ; `market` là toàn bộ dữ liệu để so sánh |
| `histogram` | Số tin theo khoảng 2 triệu, gộp từ 60 triệu trở lên |
| `experience`, `regions`, `provinces`, `languages`, `contracts` | Số tin và P25, trung vị, P75 từng nhóm |
| `categories` | Như trên, thêm `negotiable_pct`. Luôn đủ các ngành, không áp dụng bộ lọc ngành |
| `heatmap` | Trung vị ngành × kinh nghiệm; ô dưới 10 tin có `median: null` |
| `skills` | `technical`, `soft`: tỷ lệ yêu cầu và `premium_pct` so với nhóm đang lọc |
| `insights` | Nhận định sinh từ chính số liệu trên |
| `rules` | Ngưỡng thống kê đang áp dụng |

Bộ lọc không khớp tin nào trả về 200 với `kpi.jobs = 0`.

## Tin tuyển dụng

### `GET /api/jobs`

| Tham số | Mô tả |
|---|---|
| `q` | Tìm trong chức danh, không phân biệt dấu |
| `category`, `province`, `experience`, `contract_type`, `skill` | Lọc |
| `min_salary`, `max_salary` | Lọc theo lương; min lớn hơn max trả về 422 |
| `has_salary` | `true` hoặc `false` |
| `sort` | `relevance`, `salary_desc`, `salary_asc` |
| `page`, `size` | Phân trang; `size` tối đa 100 |

### `GET /api/jobs/{id}`

Chi tiết một tin. Tin thoả thuận có thêm `estimated_salary` do mô hình ước tính.

## Dự đoán

### `POST /api/predict/salary`

```json
{"title": "Kế toán tổng hợp", "province": "Hà Nội", "experience_years": 3,
 "contract_type": "Toàn thời gian", "category": null, "skills": ["excel", "misa"], "languages": []}
```

`title` dài 2–300 ký tự, `experience_years` từ 0 đến 40. `category` để trống thì hệ thống tự phân loại từ chức danh.

Trả về `predicted`, `low`, `high` (khoảng 80%), `factors` và `top_features` (giải thích bằng SHAP của LightGBM), `auto_category`.

### `POST /api/predict/skills`

```json
{"title": "Data Analyst", "top_k": 15}
```

Trả về `technical`, `soft`: mỗi kỹ năng có `probability` và `recommended` (vượt ngưỡng chọn trên tập validation).

### `POST /api/predict/category`

```json
{"title": "Dược sĩ", "description": "Tư vấn thuốc cho khách hàng", "top_k": 5}
```

Trả về `predictions` gồm ngành và `score`. Với Linear SVM, `score` là softmax của khoảng cách, là điểm tương đối, không phải xác suất đã hiệu chỉnh.

### `GET /api/predict/history`

Tham số `task`, `limit` (tối đa 200). Lịch sử từ bảng `predictions`.

## Khai phá dữ liệu và đánh giá

| Đường dẫn | Tham số | Nội dung |
|---|---|---|
| `GET /api/mining/rules` | `type`, `skill`, `consequent`, `min_lift`, `min_confidence`, `limit` | Luật kết hợp |
| `GET /api/mining/clusters` | | Các cụm, silhouette theo k, toạ độ PCA |
| `GET /api/mining/clusters/{id}/jobs` | `limit` | Tin thuộc cụm |
| `GET /api/mining/skill-value` | `kind`, `sort`, `min_jobs`, `limit` | Kỹ năng và lương |
| `GET /api/models/reports` | | Chỉ số mô hình và báo cáo chi tiết |

## Pipeline

| Đường dẫn | Nội dung |
|---|---|
| `GET /api/pipeline/overview` | Các bước với lần chạy gần nhất, số đếm, job chạy được |
| `GET /api/pipeline/runs?job=&limit=` | Nhật ký chạy |
| `GET /api/pipeline/quality` | Hồ sơ chất lượng dữ liệu mới nhất |
| `GET /api/pipeline/spark` | Số đo Spark, bảng Gold, benchmark |
| `POST /api/pipeline/reconcile` | Chạy lại toàn bộ đối soát, trả về kỳ vọng và thực tế từng kiểm tra |
| `POST /api/pipeline/jobs` | Chạy job `{"job": "quality"}` hoặc `{"job": "spark"}`, trả về 202; job thứ hai đồng thời bị từ chối bằng 409 |
| `GET /api/pipeline/jobs/current` | Trạng thái và log của job hiện tại |

Chỉ hai job trên được chạy từ API. Tên job được kiểm tra theo danh sách cố định, không nhận lệnh tuỳ ý. API không có xác thực, nên chỉ lắng nghe ở `127.0.0.1` và không dành cho môi trường công khai.

## API thống kê có sẵn

Nhóm `GET /api/stats/*` (`overview`, `categories`, `provinces`, `experience`, `salary-distribution`, `top-skills`, `contract-types`, `languages`) được giữ nguyên từ bản gốc. Trang dự đoán lương dùng `salary-distribution`.
