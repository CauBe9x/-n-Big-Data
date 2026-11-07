"""Phiên bản xử lý phân tán bằng Apache Spark (PySpark) – minh hoạ khía cạnh Big Data của đồ án.

Cùng dữ liệu VietJobs.csv, Spark thực hiện:
  1. Đọc CSV nhiều dòng, làm sạch bằng Spark SQL (lương, kinh nghiệm, danh sách kỹ năng).
  2. Thống kê phân tán: số tin & lương trung vị (percentile_approx) theo ngành / kinh nghiệm, top kỹ năng.
  3. Spark MLlib:
       - Hồi quy lương: TF-IDF chức danh + one-hot (ngành, địa điểm, hợp đồng) + kinh nghiệm -> LinearRegression & GBTRegressor
       - Luật kết hợp kỹ năng: FPGrowth
  4. Ghi kết quả ra data/spark_output/ (Parquet + JSON số liệu).

Chạy (cần Java 8/11/17 và `pip install pyspark`), từ thư mục gốc dự án:
    python spark/spark_pipeline.py                     # chế độ local[*] – dùng mọi lõi CPU
    spark-submit --master yarn spark/spark_pipeline.py # trên cụm Hadoop/YARN
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import (HashingTF, IDF, OneHotEncoder, RegexTokenizer, StringIndexer, VectorAssembler)
from pyspark.ml.fpm import FPGrowth
from pyspark.ml.regression import GBTRegressor, LinearRegression
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[1]
CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw" / "VietJobs.csv"
OUT = ROOT / "data" / "spark_output"


def parse_list(col):
    """"['Excel', 'Word']" -> array('excel','word') (chuẩn hoá chữ thường, bỏ khoảng trắng)."""
    cleaned = F.regexp_replace(F.coalesce(col, F.lit("")), r"^\[|\]$", "")
    arr = F.split(cleaned, r"',\s*'|\",\s*\"|',\s*\"|\",\s*'")
    arr = F.transform(arr, lambda x: F.lower(F.trim(F.regexp_replace(x, r"^['\"\s]+|['\"\s]+$", ""))))
    return F.array_distinct(F.filter(arr, lambda x: F.length(x) > 1))


def main() -> None:
    t0 = time.time()
    spark = (SparkSession.builder.appName("VietJobs-BigData").master("local[*]")
             .config("spark.sql.shuffle.partitions", "16").config("spark.ui.showConsoleProgress", "false").config("spark.driver.memory", "2g").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    print(f"Spark {spark.version} – {spark.sparkContext.defaultParallelism} luồng song song")

    raw = (spark.read.option("header", True).option("multiLine", True).option("escape", '"')
           .csv(str(CSV)))
    print(f"[1] Đọc {raw.count():,} dòng, {len(raw.columns)} cột, {raw.rdd.getNumPartitions()} phân vùng")

    # ---------------------------------------------------------------- 1. Làm sạch
    smin, smax = F.col("salary_min").cast("double"), F.col("salary_max").cast("double")
    exp_txt = F.lower(F.coalesce(F.col("experience_required"), F.lit("")))
    exp_num = F.regexp_extract(exp_txt, r"(\d+(?:\.\d+)?)", 1).cast("double")
    exp_years = (F.when(exp_txt.contains("không"), 0.0)
                 .when(exp_txt.contains("tháng"), exp_num / 12)
                 .when(exp_txt.contains("dưới"), exp_num / 2)
                 .when(exp_txt.contains("trên"), exp_num + 1)
                 .otherwise(exp_num))
    # Cùng một tin được đăng dưới nhiều ngành -> gộp lại, giữ mảng ngành (Spark groupBy + collect_set)
    key = ["job_title", "location", "description"]
    cats = raw.groupBy(*key).agg(F.collect_set(F.coalesce("category", F.lit("chưa_phân_loại"))).alias("categories"))
    df = (raw.dropDuplicates(key).drop("category").join(cats, key)
          .withColumn("category", F.col("categories")[0])
          .withColumn("salary", F.when((smin > 0) & (smax > 0), (smin + smax) / 2)
                      .when(smax > 0, smax).when(smin > 0, smin))
          .withColumn("exp_years", exp_years)
          .withColumn("exp_bucket", F.when(F.col("exp_years").isNull(), "Không rõ")
                      .when(F.col("exp_years") == 0, "Không yêu cầu").when(F.col("exp_years") < 1, "Dưới 1 năm")
                      .when(F.col("exp_years") <= 2, "1-2 năm").when(F.col("exp_years") <= 5, "3-5 năm")
                      .otherwise("Trên 5 năm"))
          .withColumn("province", F.trim(F.split(F.lower(F.coalesce("location", F.lit("khác"))), ",")[0]))
          .withColumn("tech_skills", parse_list(F.col("technical_skills")))
          .withColumn("soft", parse_list(F.col("soft_skills")))
          .withColumn("contract_type", F.coalesce("contract_type", F.lit("Không rõ")))
          .cache())
    n = df.count()
    print(f"    Sau khi gộp tin trùng: {n:,} tin ({df.where(F.size('categories') > 1).count():,} tin thuộc >1 ngành)")

    # ---------------------------------------------------------------- 2. Thống kê phân tán
    paid = df.where(F.col("salary").between(1, 150))
    per_cat = df.withColumn("category", F.explode("categories"))   # một tin tính ở mọi ngành của nó
    paid_cat = per_cat.where(F.col("salary").between(1, 150))
    by_cat = (per_cat.groupBy("category").agg(F.count("*").alias("n_jobs"))
              .join(paid_cat.groupBy("category").agg(F.percentile_approx("salary", 0.5).alias("median_salary"),
                                                  F.round(F.avg("salary"), 1).alias("mean_salary")), "category", "left")
              .orderBy(F.desc("n_jobs")))
    by_exp = paid.groupBy("exp_bucket").agg(F.count("*").alias("n"), F.percentile_approx("salary", 0.5).alias("median_salary"))
    top_skills = (df.select(F.explode("tech_skills").alias("skill")).groupBy("skill").count()
                  .orderBy(F.desc("count")).limit(50))
    print("[2] Lương trung vị theo ngành (Spark percentile_approx):")
    by_cat.show(16, truncate=45)
    by_exp.orderBy("median_salary").show()
    top_skills.show(10, truncate=False)

    OUT.mkdir(parents=True, exist_ok=True)
    by_cat.write.mode("overwrite").parquet(str(OUT / "salary_by_category.parquet"))
    by_exp.write.mode("overwrite").parquet(str(OUT / "salary_by_experience.parquet"))
    top_skills.write.mode("overwrite").parquet(str(OUT / "top_skills.parquet"))

    # ---------------------------------------------------------------- 3a. MLlib – hồi quy lương
    data = paid.select("job_title", "category", "province", "contract_type", "tech_skills",
                       F.coalesce("exp_years", F.lit(1.0)).alias("exp_years"),
                       F.log1p("salary").alias("label"), "salary")
    train, test = data.randomSplit([0.8, 0.2], seed=42)
    stages = [
        RegexTokenizer(inputCol="job_title", outputCol="title_tokens", pattern=r"[\s\-/(),.]+", toLowercase=True),
        HashingTF(inputCol="title_tokens", outputCol="title_tf", numFeatures=1 << 14),
        IDF(inputCol="title_tf", outputCol="title_tfidf", minDocFreq=3),
        HashingTF(inputCol="tech_skills", outputCol="skills_tf", numFeatures=1 << 12, binary=True),
    ]
    for c in ("category", "province", "contract_type"):
        stages += [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep"),
                   OneHotEncoder(inputCol=f"{c}_idx", outputCol=f"{c}_ohe")]
    stages.append(VectorAssembler(inputCols=["title_tfidf", "skills_tf", "category_ohe", "province_ohe",
                                             "contract_type_ohe", "exp_years"], outputCol="features"))

    metrics = {}
    for name, reg in (("Spark LinearRegression (ElasticNet)", LinearRegression(maxIter=100, regParam=0.01, elasticNetParam=0.1)),
                      ("Spark GBTRegressor", GBTRegressor(maxIter=40, maxDepth=6, seed=42))):
        t = time.time()
        model = Pipeline(stages=stages + [reg]).fit(train)
        pred = model.transform(test).withColumn("pred_salary", F.expm1("prediction"))
        ev = lambda m: RegressionEvaluator(labelCol="salary", predictionCol="pred_salary", metricName=m).evaluate(pred)  # noqa: E731
        metrics[name] = {"RMSE": ev("rmse"), "MAE": ev("mae"), "R2": ev("r2"), "seconds": round(time.time() - t, 1)}
        print(f"[3a] {name:38s} RMSE={metrics[name]['RMSE']:.2f}  MAE={metrics[name]['MAE']:.2f}  R2={metrics[name]['R2']:.3f}"
              f"  ({metrics[name]['seconds']}s)")

    # ---------------------------------------------------------------- 3b. MLlib – FP-Growth
    baskets = df.select(F.array_distinct(F.concat("tech_skills", "soft")).alias("items")).where(F.size("items") > 1)
    fp = FPGrowth(itemsCol="items", minSupport=0.01 if n > 20000 else 0.02, minConfidence=0.3).fit(baskets)
    rules = fp.associationRules.orderBy(F.desc("lift")).limit(30)
    print("[3b] Luật kết hợp kỹ năng (FP-Growth phân tán):")
    rules.select("antecedent", "consequent", F.round("confidence", 3).alias("conf"), F.round("lift", 2).alias("lift")).show(15, truncate=60)
    rules.write.mode("overwrite").parquet(str(OUT / "association_rules.parquet"))

    with open(OUT / "spark_metrics.json", "w", encoding="utf-8") as f:
        json.dump({"n_jobs": n, "regression_test_metrics": metrics, "spark_version": spark.version,
                   "seconds_total": round(time.time() - t0, 1)}, f, ensure_ascii=False, indent=2)
    print(f"Xong trong {time.time() - t0:.0f}s – kết quả trong {OUT}")
    spark.stop()


if __name__ == "__main__":
    main()
