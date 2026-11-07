# Hướng dẫn trình diễn

Kịch bản khoảng 10 phút, có phương án dự phòng. Các con số bên dưới là kết quả thật trên dữ liệu VietJobs, dùng để đối chiếu khi demo.

## Chuẩn bị trước buổi bảo vệ

Làm trước ít nhất một ngày:

1. Bấm đúp `run.bat` (hoặc gõ `.\run.bat` trong PowerShell), đợi tới khi trình duyệt mở được http://localhost:8000.
2. Mở `/pipeline`, bấm **Kiểm tra lại**, xác nhận không có kiểm tra nào "Lệch".
3. Sao lưu dữ liệu demo:
   ```bat
   backend\.venv\Scripts\python scripts\local_db.py dump
   ```
   Rồi tạo gói dự phòng để chép sang USB hoặc gửi bạn cùng nhóm:
   ```bat
   backend\.venv\Scripts\python scripts\pack_data.py
   ```

Trước giờ trình bày 10 phút:

1. Tắt ứng dụng nặng để máy còn RAM. Spark dùng 3–4 GB.
2. Chạy `.\run.bat --no-open`, mở sẵn http://localhost:8000.
3. Không cần mạng: font, dữ liệu và mô hình đều nằm trên máy.
4. Nếu định chạy Spark trực tiếp, chạy thử một lần trước giờ trình bày. Máy vừa bật có thể mất tới 5 phút, các lần sau khoảng 1,5 phút.
5. Phóng trình duyệt ở mức 100–110% cho máy chiếu.

## Kịch bản

### 1. Mở đầu: bài toán (1 phút) — trang chủ `/`

- Nêu câu hỏi trên màn hình: một vị trí đáng giá bao nhiêu, cần kỹ năng gì.
- Chỉ dải số: 36.585 tin, trung vị 13,5 triệu, 29,4% tin không công khai lương. Con số 29,4% là lý do cần mô hình dự đoán.

### 2. Dashboard (2,5 phút) — `/dashboard`

1. Đọc phần **Dữ liệu đang cho thấy điều gì**: các nhận định được sinh tự động từ số liệu.
2. Chỉ biểu đồ kinh nghiệm: từ 1-2 năm lên 3-5 năm, trung vị tăng 44% (13,5 → 19,5 triệu).
3. Chọn **Kinh nghiệm = 3-5 năm**: mọi số đổi theo, trung vị thành 19,5 triệu.
4. Bấm dòng **Công nghệ thông tin kỹ thuật số** trong bảng ngành để lọc chéo.
5. Bấm **Xoá bộ lọc**.
6. Cuộn xuống ghi chú cuối trang, chủ động nói vì sao không có biểu đồ theo thời gian.

### 3. Máy học (2,5 phút)

**Dự đoán lương** `/predict/salary`

1. Bấm **Dự đoán lương** với ví dụ có sẵn (Chuyên viên phân tích dữ liệu, 2 năm, Hồ Chí Minh, sql, python): kết quả khoảng 23,1 triệu, khoảng 80% là 16,5–32,8 triệu.
2. Chỉ biểu đồ yếu tố: mô hình giải thích được lý do (kỹ năng, chức danh, kinh nghiệm).
3. Xoá kỹ năng `sql`, dự đoán lại để thấy mức lương đổi.

**Gợi ý kỹ năng** `/predict/skills`: bấm **Kế toán tổng hợp**.

**Đánh giá mô hình** `/models`: LightGBM đạt R² 0,546, MAE 3,41 triệu, baseline R² −0,06.

### 4. Tra cứu (30 giây) — `/jobs`

Gõ `ke toan` không dấu, bấm **Tìm**. Chọn **Lương = Thoả thuận**, mở một tin để thấy mức lương mô hình ước tính.

### 5. Pipeline Big Data (3 phút) — `/pipeline`

Đây là phần trọng tâm của môn học.

1. Giải thích hai luồng trên sơ đồ.
2. Bấm **Chạy: Spark batch**. Trong khi log chạy (khoảng 1,5 phút), nói tiếp bước 3 và 4. Các trang khác vẫn dùng được trong lúc này.
3. Kéo xuống **Đối soát dữ liệu**, nói: hai đường độc lập, ETL pandas và Spark, cho cùng 36.585 tin và 252.653 liên kết kỹ năng.
4. Cuộn tới **Hiệu năng đo được**: chủ động nói ở cỡ dữ liệu thật pandas nhanh hơn Spark, và vì sao vẫn có Spark.
5. Khi job xong, bấm **Kiểm tra lại**.

Nếu thiếu thời gian, chạy **Kiểm định chất lượng dữ liệu** thay cho Spark (khoảng 20 giây).

### 6. Kết (30 giây) — `/about`

Nêu giới hạn và hướng phát triển. Chủ động nêu giới hạn tốt hơn là chờ bị hỏi.

## Sự cố thường gặp

| Hiện tượng | Xử lý |
|---|---|
| Trang báo "Không kết nối được máy chủ API" | Chạy lại `.\run.bat` |
| PowerShell báo không nhận ra `run.bat` | Gõ `.\run.bat`, có `.\` ở đầu |
| Báo "Không kết nối được PostgreSQL" | `backend\.venv\Scripts\python scripts\local_db.py start` |
| Cổng 8000 đã bị chiếm | Trong cmd: `set VIETJOBS_PORT=8010` rồi `run.bat` |
| CSDL trống | `backend\.venv\Scripts\python scripts\local_db.py restore` |
| Nút Spark bị khoá | Chưa cài môi trường: `backend\.venv\Scripts\python scripts\setup_spark.py`. Có thể bỏ qua, kết quả lần chạy trước vẫn hiển thị |
| Spark chạy lỗi hoặc quá hạn lúc demo | Job tự dừng sau 10 phút. Nói rõ là lỗi, dùng kết quả lần chạy trước; nhật ký ghi lại lần lỗi đó |
| Máy chậm | Không chạy Spark, chỉ trình bày kết quả có sẵn |

Khi vẫn còn lỗi, xem log ở cửa sổ `run.bat`. Log CSDL ở `%LOCALAPPDATA%\VietJobs\postgres.log`.

## Không nên làm khi demo

- Không chạy `python -m pipeline.etl`: lệnh này xoá kết quả mô hình và khai phá.
- Không chạy Spark và mở nhiều tab nặng cùng lúc trên máy ít RAM.
- Không nói "xử lý phân tán" hay "thời gian thực". Hệ thống không có hai thứ đó.
