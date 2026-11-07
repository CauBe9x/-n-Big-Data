# Ghi chú thuyết trình

Toàn bộ số liệu dưới đây lấy từ lần chạy thật của hệ thống.

## 1. Bài toán

Tin tuyển dụng ghi lương, địa điểm và kỹ năng theo nhiều cách, và 29,4% số tin không công khai lương. Người tìm việc khó biết một vị trí đáng giá bao nhiêu và cần học gì.

Đề bài yêu cầu: có bộ dữ liệu về lương, vị trí, kỹ năng từ trang tuyển dụng; dùng máy học dự đoán lương và kỹ năng; có giao diện minh chứng.

## 2. Giải pháp

Một hệ thống batch gồm: làm sạch, lưu trữ chuẩn hoá, dashboard phân tích, ba mô hình máy học, khai phá dữ liệu. Dữ liệu đi qua hai đường độc lập rồi được đối soát.

Điểm khác biệt: **mọi số liệu đều kiểm chứng được**. Trang Pipeline chạy đối soát trực tiếp; 24/24 kiểm tra đạt.

## 3. Kiến trúc

Nguồn CSV đi hai luồng:

- **Luồng phục vụ:** pandas → PostgreSQL → máy học, khai phá → FastAPI → React.
- **Luồng Spark:** Bronze → Silver → Gold → đối soát với PostgreSQL.

Chi tiết ở [ARCHITECTURE.md](ARCHITECTURE.md).

## 4. Công nghệ và vì sao chọn

| Công nghệ | Lý do |
|---|---|
| PostgreSQL | 3NF, khoá ngoại, lọc và gom nhóm tức thời cho dashboard |
| pandas, scikit-learn, LightGBM | Dữ liệu vừa RAM; ở cỡ này pandas nhanh hơn Spark |
| Spark, Parquet | Trọng tâm môn học; đối soát độc lập với ETL; chuẩn bị cho dữ liệu lớn hơn |
| FastAPI | Cùng ngôn ngữ với pipeline, dùng lại mã đặc trưng khi suy luận |
| React | Nền tảng có sẵn của nhóm |

**Không dùng** Kafka, HDFS, YARN, Airflow vì dữ liệu là file tĩnh trên một máy. Thêm vào chỉ để có tên trong danh sách.

## 5. Quy trình Big Data

| Bước | Làm gì | Kết quả đo được |
|---|---|---|
| Ingestion | Đọc CSV nhiều dòng | 48.092 dòng, 18 cột, 103 MB |
| Cleaning | Gộp trùng, chuẩn hoá | 36.585 tin; 984 cách ghi địa điểm còn 54; 30.426 tên kỹ năng chuyên môn còn 22.445 |
| Transformation | Lương, kinh nghiệm, kỹ năng, ngành | 252.653 liên kết tin–kỹ năng; 7.588 tin đa ngành |
| Processing | ETL pandas, Spark 8 partition | Hai đường cho cùng kết quả |
| Storage | PostgreSQL, Parquet | 20 bảng; 3 tầng Bronze, Silver, Gold |
| Analysis | SQL, FP-Growth, K-Means, 3 mô hình | 431 luật, 40 cụm |
| Visualization | Dashboard lọc 5 chiều | Tính trực tiếp từ PostgreSQL |

**Câu chuyện Spark nên kể:**

- Silver chạy đúng các hàm làm sạch của ETL trong Python worker, song song theo partition. Hai đường cho cùng 36.585 tin, 7.588 tin đa ngành, 25.819 tin có lương, 252.653 liên kết kỹ năng.
- CSV nhiều dòng không chia nhỏ khi đọc (1 partition), nên phải `repartition(8)` mới song song được.
- Benchmark đo thật, 3 lần lấy trung vị:

| Dữ liệu | Spark 4 lõi | pandas |
|---|---:|---:|
| Thật, 36.585 dòng | 1,14 s | 0,10 s |
| ×5, 182.925 dòng | 1,02 s | 0,52 s |
| ×20, 731.700 dòng | 1,47 s | 2,03 s |
| ×50, 1.829.250 dòng | 2,81 s | 4,63 s |

Trên dữ liệu ×20, số lõi 1 / 2 / 4 cho 2,32 / 1,75 / 1,27 giây, tức nhanh gấp 1,8 lần ở 4 lõi, không phải gấp 4, vì có chi phí điều phối và shuffle.

Kết luận trung thực: **với dữ liệu thật, pandas nhanh hơn. Spark vượt ở khoảng vài trăm nghìn dòng trở lên.** Vì vậy ETL phục vụ dùng pandas. Dữ liệu ×5 trở lên là bản sao chỉ để đo tốc độ. Số ở ×1 cao hơn ×5 một chút vì Spark còn đang khởi động JIT, không phải vì ít dữ liệu lại chậm hơn. Các số đo cỡ giây nên dao động giữa các lần chạy; xu hướng thì ổn định qua nhiều lần đo.

Spark MLlib đối chứng (chia 80/20 ngẫu nhiên, khác mô hình chính nên chỉ so sánh tương đối): LinearRegression RMSE 7,35, R² 0,36; GBT RMSE 7,53, R² 0,33. FP-Growth phân tán tìm được 566 luật trên 35.743 giao dịch. Spark batch từ CSV tới Gold mất khoảng 76 giây khi máy rảnh.

Sự cố đáng kể khi làm: GBT từng treo vì tranh chấp bộ nhớ cache, nên pipeline giải phóng cache trước MLlib và mọi job Spark đều có thời hạn. Có thể nêu đây là bài học vận hành thật.

## 6. Kết quả

| Bài toán | Mô hình | Kết quả test | Baseline |
|---|---|---|---|
| Dự đoán lương | LightGBM | RMSE 5,76; MAE 3,41 triệu; R² 0,546; khoảng 80% phủ 80,2% | Trung vị ngành: R² −0,06 |
| Gợi ý kỹ năng | OvR LogReg, chỉ chức danh | P@5 0,333; R@10 0,534 | Phổ biến theo ngành: P@5 0,277 |
| Phân loại ngành | Linear SVM cân bằng lớp | Accuracy 0,719; Macro-F1 0,676 | Bài báo: 0,47 và 0,42 |

Phát hiện từ dữ liệu:

- Từ 1-2 năm lên 3-5 năm, lương trung vị tăng 44% (13,5 → 19,5 triệu).
- Lương trung vị cao nhất ở Xây dựng kiến trúc bất động sản và Công nghệ thông tin (16 triệu).
- Công nghệ thông tin có 39,9% tin ghi thoả thuận, cao nhất trong các ngành.

## 7. Điểm nổi bật

1. Hai đường xử lý độc lập, đối soát tự động, chạy lại được ngay trước mặt giảng viên.
2. Benchmark trả lời thẳng câu hỏi "khi nào cần Spark".
3. Dự đoán có giải thích (SHAP) và có khoảng tin cậy được kiểm định.
4. Nhận định trên dashboard sinh từ số liệu, nhóm ít mẫu được để trống.
5. Chạy một lệnh, không cần Docker, không cần cloud, không cần mạng.

## 8. Giới hạn

- Spark chạy một máy (`local[*,8]`): song song theo lõi, không phân tán nhiều máy.
- Batch, không có thời gian thực.
- Dữ liệu 100 MB, chưa phải Big Data đúng nghĩa về kích thước.
- Không có ngày đăng tin, nên không phân tích xu hướng theo thời gian.
- Chỉ một nguồn (TopCV). 29,4% tin không có lương nên kết quả lệch về nhóm công bố.
- Kỹ năng do LLM trích xuất, còn nhiễu.
- Mô hình: sai số vẫn lớn với lương cao; 56,5% dự đoán sai dưới 20%.

## 9. Hướng phát triển

1. Thu thập định kỳ để có dữ liệu theo thời gian, khi đó xu hướng mới có ý nghĩa, và Airflow mới có việc để làm.
2. Thêm nguồn tuyển dụng khác để giảm thiên lệch một nguồn.
3. Chạy Spark trên cụm thật để kiểm chứng khả năng mở rộng.
4. Dùng embedding tiếng Việt cho chức danh thay TF-IDF.
5. Chuẩn hoá kỹ năng theo một danh mục chuẩn.

## 10. Câu hỏi giảng viên có thể hỏi

**"Dữ liệu này có phải Big Data không?"**
Không theo kích thước: 103 MB nằm gọn trong RAM, và benchmark cho thấy pandas nhanh hơn. Nhóm dùng Spark để học quy trình, đối soát, và đo xem khi nào cần nó. Về độ đa dạng (variety) thì có: văn bản tự do, kỹ năng do LLM trích xuất, nhiều định dạng.

**"Spark ở đây có chạy phân tán không?"**
Không. `local[*,8]` là một máy, mỗi lõi một luồng thực thi. Có song song, có shuffle, có partition, nhưng không có nhiều máy.

**"Sao không dùng Spark cho toàn bộ?"**
Vì ở cỡ dữ liệu này nó chậm hơn pandas khoảng 10 lần, và làm chậm việc đó chỉ để có chữ Spark thì không hợp lý.

**"Kafka đâu?"**
Dữ liệu là file tĩnh, không có luồng sự kiện.

**"Sao không có biểu đồ xu hướng theo thời gian?"**
File không có cột ngày nào. Vẽ theo thời gian tức là phải bịa dữ liệu.

**"Dữ liệu thu thập khi nào?"**
Repo chính thức ghi tháng 7–10/2025, bài báo ghi tháng 7/2025 trong khoảng một tuần. Hai nguồn của chính tác giả không khớp và file không có ngày để kiểm chứng. Nhóm ghi theo repo và nêu rõ điểm này.

**"Vì sao RMSE của nhóm tốt hơn bài báo nhiều vậy?"**
Không nên kết luận mô hình giỏi hơn. Bài báo không gộp tin trùng và chia tập khác, nên hai số chỉ so sánh tương đối. Con số 10,24 của bài báo là dòng "Fine-tuned on Both" trong Bảng 4. Bài báo dùng LLM sinh số từ prompt; nhóm dùng mô hình dạng bảng có thêm đặc trưng kỹ năng, nên bài toán cũng khác.

**"Sao RMSE trên validation là 7,95 mà test là 5,76?"**
RMSE nhạy với ngoại lai: tập validation có 9 tin lương từ 100 triệu trở lên, tập test chỉ có 1. Bỏ 5 sai số lớn nhất thì RMSE validation giảm còn 6,53. MAE ổn định hơn nhiều (3,81 và 3,41). Vì vậy nên đọc MAE cùng RMSE, và R² 0,546 phụ thuộc khá nhiều vào cách chia tập (trên validation là 0,438).

**"Accuracy phân loại 0,719 tính thế nào?"**
Tin đa ngành được tính đúng nếu ngành dự đoán thuộc tập ngành của tin. So chặt với ngành chính thì Accuracy là 0,658. Nên nêu cả hai.

**"Vì sao chọn k = 40?"**
Silhouette tăng đều và đạt cao nhất ở biên khoảng tìm kiếm (0,246), nên k = 40 không phải điểm tối ưu thật. Nhóm giới hạn k để cụm còn đủ lớn và giải thích được. Giá trị silhouette thấp là bình thường với dữ liệu văn bản.

**"Kỹ năng X làm tăng lương Y% đúng không?"**
Không. Đó là tương quan: kỹ năng đàm phán đi kèm vị trí cấp cao, không chứng minh học đàm phán sẽ tăng lương.

**"Có rò rỉ dữ liệu không?"**
Chia theo tin sau khi gộp trùng, nên một tin không thể vừa ở train vừa ở test. Chữ số trong chức danh bị xoá để mô hình không đọc lương từ tiêu đề kiểu "Lương 15 triệu". Tin gần giống nhau ở địa điểm khác vẫn có thể nằm ở hai tập, đây là rủi ro chưa xử lý.

**"Làm sao biết số trên dashboard đúng?"**
Đối soát: truy vấn trực tiếp, view BI, Spark độc lập và dashboard Superset của nhóm đều cho cùng kết quả.

**"Chạy lại pipeline có ra kết quả như cũ không?"**
Có, các bước dùng seed cố định. Đã chạy lại toàn bộ từ CSV gốc hai lần trên máy này: chỉ số giống hệt nhau và khớp báo cáo cũ của nhóm.

## 11. Thông tin cần kiểm tra lại trước khi nộp

- Tên môn học, trường trong README lấy từ tài liệu cũ của nhóm.
- Superset chưa được chạy lại trong đợt nâng cấp này. Nếu muốn demo Superset, cần thử trước trên máy trình bày.
