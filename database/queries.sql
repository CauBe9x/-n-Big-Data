-- =============================================================================
--  Một số truy vấn mẫu trên CSDL VietJobs (minh hoạ JOIN qua khoá ngoại)
--  psql postgresql://vietjobs:vietjobs@localhost:5432/vietjobs -f database/queries.sql
-- =============================================================================

-- 1. Lương trung vị theo ngành (một tin đa ngành được tính ở mỗi ngành – qua bảng nối job_categories)
SELECT c.name AS nganh, count(*) AS so_tin,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY j.salary_avg) AS luong_trung_vi
FROM job_categories jc
JOIN categories c ON c.category_id = jc.category_id
JOIN jobs j       ON j.job_id = jc.job_id
WHERE j.salary_avg BETWEEN 1 AND 150
GROUP BY c.name
ORDER BY luong_trung_vi DESC;

-- 2. Top 10 kỹ năng chuyên môn của ngành Công nghệ thông tin
SELECT s.name AS ky_nang, count(*) AS so_tin
FROM job_skills js
JOIN skills s          ON s.skill_id = js.skill_id AND s.kind = 'technical'
JOIN job_categories jc ON jc.job_id = js.job_id
JOIN categories c      ON c.category_id = jc.category_id
WHERE c.slug = 'công_nghệ_thông_tin_kỹ_thuật_số'
GROUP BY s.name
ORDER BY so_tin DESC
LIMIT 10;

-- 3. Lương trung vị theo miền và nhóm kinh nghiệm
SELECT p.region AS mien, j.experience_bucket AS kinh_nghiem, count(*) AS so_tin,
       round(CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY j.salary_avg) AS numeric), 1) AS luong_trung_vi
FROM jobs j
JOIN provinces p ON p.province_id = j.province_id
WHERE j.salary_avg BETWEEN 1 AND 150
GROUP BY ROLLUP (p.region, j.experience_bucket)
ORDER BY 1, 2;

-- 4. Luật kết hợp dẫn tới "Lương=Cao", hiển thị vế trái dạng chuỗi
SELECT string_agg(s.name, ', ' ORDER BY s.name) AS neu_tin_yeu_cau, r.consequent_label AS thi,
       round(CAST(r.confidence AS numeric), 3) AS do_tin_cay, round(CAST(r.lift AS numeric), 2) AS lift
FROM association_rules r
JOIN rule_antecedents a USING (rule_id)
JOIN skills s USING (skill_id)
WHERE r.consequent_type = 'salary' AND r.consequent_label = 'Lương=Cao'
GROUP BY r.rule_id
ORDER BY r.lift DESC
LIMIT 10;

-- 5. Mỗi cụm công việc: số tin, lương trung vị, tỉnh tuyển nhiều nhất (JOIN job_clusters -> jobs -> provinces)
SELECT cl.label AS cum, cl.size AS so_tin, cl.median_salary AS luong_trung_vi,
       (SELECT p.name FROM job_clusters jc JOIN jobs j USING (job_id) JOIN provinces p USING (province_id)
         WHERE jc.cluster_id = cl.cluster_id GROUP BY p.name ORDER BY count(*) DESC LIMIT 1) AS tinh_nhieu_nhat
FROM clusters cl
ORDER BY cl.size DESC
LIMIT 15;

-- 6. So sánh các mô hình của lần huấn luyện mới nhất (bảng chỉ số dạng dài -> pivot)
SELECT task, model, is_best,
       max(value) FILTER (WHERE metric = 'RMSE')        AS rmse,
       max(value) FILTER (WHERE metric = 'R2')          AS r2,
       max(value) FILTER (WHERE metric = 'Accuracy')    AS accuracy,
       max(value) FILTER (WHERE metric = 'Macro_F1')    AS macro_f1,
       max(value) FILTER (WHERE metric = 'Precision@5') AS precision_at_5
FROM v_model_results
WHERE split = 'test'
GROUP BY task, model, is_best
ORDER BY task, model;

-- 7. Lịch sử dự đoán từ giao diện kèm tên mô hình đã dùng
SELECT p.created_at, p.task, m.name AS mo_hinh, p.input ->> 'title' AS chuc_danh, p.output
FROM predictions p
LEFT JOIN ml_models m ON m.model_id = p.model_id
ORDER BY p.created_at DESC
LIMIT 20;
