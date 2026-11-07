"""Tầng xử lý batch bằng Apache Spark: CSV -> Bronze -> Silver -> Gold (Parquet) + Spark MLlib (tuỳ chọn).

Vai trò trong đồ án: một đường xử lý độc lập với ETL pandas, dùng CHÍNH các hàm làm sạch của ETL (pipeline/cleaning.py),
chạy song song theo partition. Kết quả được đối soát với PostgreSQL, nên hai đường phải cho cùng số liệu.

Chế độ chạy là local[*]: mỗi lõi CPU một executor trong MỘT máy. Đây KHÔNG phải cụm phân tán; mã này chạy được trên cụm
vì không phụ thuộc đường dẫn cục bộ nào ngoài --lake, nhưng điều đó chưa được kiểm chứng trong đồ án.

Không chạy file này trực tiếp trên Windows. Dùng:  cd backend && python -m pipeline.spark_job [--ml]
Lý do: JVM treo khi đường dẫn có dấu tiếng Việt, nên spark_job chép mã vào thư mục ASCII rồi mới gọi file này.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

SAL_LO, SAL_HI = 1, 150
# Các chuỗi pandas.read_csv coi là thiếu. Áp dụng y hệt để hai đường xử lý thấy cùng một dữ liệu đầu vào.
NA_VALUES = ["", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A",
             "NA", "NULL", "NaN", "None", "n/a", "nan", "null"]
DUP_KEY = ["job_title", "location", "description"]
CLEAN_SCHEMA = T.StructType([
    T.StructField("job_key", T.LongType()), T.StructField("title", T.StringType()),
    T.StructField("province", T.StringType()), T.StructField("region", T.StringType()),
    T.StructField("contract_type", T.StringType()), T.StructField("experience_years", T.DoubleType()),
    T.StructField("experience_bucket", T.StringType()), T.StructField("sal_min", T.DoubleType()),
    T.StructField("sal_max", T.DoubleType()), T.StructField("sal_avg", T.DoubleType()),
    T.StructField("is_negotiable", T.BooleanType()), T.StructField("source_rows", T.IntegerType()),
    T.StructField("categories", T.ArrayType(T.StringType())), T.StructField("tech_skills", T.ArrayType(T.StringType())),
    T.StructField("soft_skills", T.ArrayType(T.StringType())), T.StructField("languages", T.ArrayType(T.StringType())),
])


def log(msg: str) -> None:
    print(msg, flush=True)


def write_parquet(df, path: str) -> int:
    """Ghi Parquet song song. Trả về số file.

    Trên Linux/cụm dùng df.write như bình thường. Trên Windows, df.write cần winutils.exe của Hadoop; thay vì tải binary
    bên thứ ba, mỗi Python worker tự ghi partition của mình bằng pyarrow qua mapInArrow, việc ghi vẫn song song.
    """
    if os.name != "nt":
        df.write.mode("overwrite").parquet(path)
        return len(list(Path(path).glob("*.parquet")))
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)

    def writer(batches):
        import uuid

        import pyarrow as pa
        import pyarrow.parquet as pq
        file, out, rows = os.path.join(path, f"part-{uuid.uuid4().hex}.parquet"), None, 0
        for batch in batches:
            out = out or pq.ParquetWriter(file, batch.schema, compression="snappy")
            out.write_batch(batch)
            rows += batch.num_rows
        if out:
            out.close()
            yield pa.RecordBatch.from_pylist([{"file": file, "rows": rows}])

    return len(df.mapInArrow(writer, "file string, rows long").collect())


def write_table(rows: list[dict], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def clean_partition(batches):
    """Chạy trên từng partition, ở Python worker. Dùng lại đúng các hàm của pipeline/cleaning.py (gửi sang bằng addPyFile)."""
    import pandas as pd
    import vj_cleaning as C

    for pdf in batches:
        loc = [C.normalize_location(l, c) for l, c in zip(pdf["location"], pdf["country"])]
        sal = [C.parse_salary(a, b, c) for a, b, c in zip(pdf["salary_min"], pdf["salary_max"], pdf["salary_avg"])]
        years = pdf["experience_required"].map(C.parse_experience)
        province = [p for p, _ in loc]
        yield pd.DataFrame({
            "job_key": pdf["job_key"], "title": pdf["job_title"].astype(str).str.strip(), "province": province,
            "region": [C.province_region(p) for p in province],
            "contract_type": pdf["contract_type"].fillna("Không rõ").astype(str).str.strip(),
            "experience_years": pd.to_numeric(years, errors="coerce"),
            "experience_bucket": [C.experience_bucket(None if pd.isna(v) else v) for v in years],
            "sal_min": [s[0] for s in sal], "sal_max": [s[1] for s in sal], "sal_avg": [s[2] for s in sal],
            "is_negotiable": [s[2] is None for s in sal], "source_rows": pdf["source_rows"],
            "categories": [list(c) for c in pdf["categories"]],
            "tech_skills": [C.normalize_skills(C.parse_list(v)) for v in pdf["technical_skills"]],
            "soft_skills": [C.normalize_skills(C.parse_list(v)) for v in pdf["soft_skills"]],
            "languages": [C.parse_languages(v) for v in pdf["languages_required"]],
        })


class Stages:
    """Đo thời gian từng tầng để hiển thị trên trang Pipeline."""

    def __init__(self):
        self.items: list[dict] = []

    def add(self, name: str, t0: float, **info) -> None:
        row = {"stage": name, "seconds": round(time.time() - t0, 2), **info}
        self.items.append(row)
        log(f"[{name}] {row['seconds']}s  " + "  ".join(f"{k}={v}" for k, v in info.items()))


def build_gold(silver) -> dict:
    """Các phép tổng hợp cần shuffle. Trả về dict tên bảng -> DataFrame."""
    paid = silver.where(F.col("sal_avg").between(SAL_LO, SAL_HI))
    median = F.percentile_approx("sal_avg", 0.5, 100000).alias("median_salary")
    per_cat = silver.withColumn("category", F.explode("categories"))
    by_category = (per_cat.groupBy("category").agg(F.count("*").alias("jobs"))
                   .join(per_cat.where(F.col("sal_avg").between(SAL_LO, SAL_HI)).groupBy("category")
                         .agg(median, F.round(F.avg("sal_avg"), 2).alias("mean_salary")), "category", "left"))
    by_experience = paid.groupBy("experience_bucket").agg(F.count("*").alias("jobs"), median)
    by_province = silver.groupBy("province", "region").agg(F.count("*").alias("jobs"))
    skills = silver.select(F.explode("tech_skills").alias("skill")).groupBy("skill").count()
    skill_pairs = (silver.select(F.col("job_key"), F.explode("tech_skills").alias("a"))
                   .join(silver.select(F.col("job_key"), F.explode("tech_skills").alias("b")), "job_key")
                   .where(F.col("a") < F.col("b")).groupBy("a", "b").count())
    return {"salary_by_category": by_category.orderBy(F.desc("jobs")),
            "salary_by_experience": by_experience.orderBy("median_salary"),
            "jobs_by_province": by_province.orderBy(F.desc("jobs")),
            "top_skills": skills.orderBy(F.desc("count"), "skill").limit(100),
            "skill_pairs": skill_pairs.orderBy(F.desc("count"), "a", "b").limit(100)}


def run_mllib(silver) -> dict:
    """Đối chứng bằng Spark MLlib trên cùng dữ liệu Silver."""
    from pyspark.ml import Pipeline
    from pyspark.ml.evaluation import RegressionEvaluator
    from pyspark.ml.feature import HashingTF, IDF, OneHotEncoder, RegexTokenizer, StringIndexer, VectorAssembler
    from pyspark.ml.fpm import FPGrowth
    from pyspark.ml.regression import GBTRegressor, LinearRegression

    paid = silver.where(F.col("sal_avg").between(SAL_LO, SAL_HI))
    data = paid.select("title", F.col("categories")[0].alias("category"), "province", "contract_type", "tech_skills",
                       F.coalesce("experience_years", F.lit(1.0)).alias("exp_years"),
                       F.log1p("sal_avg").alias("label"), F.col("sal_avg").alias("salary"))
    train, test = data.randomSplit([0.8, 0.2], seed=42)
    stages = [
        RegexTokenizer(inputCol="title", outputCol="tokens", pattern=r"[\s\-/(),.]+", toLowercase=True),
        HashingTF(inputCol="tokens", outputCol="title_tf", numFeatures=1 << 14),
        IDF(inputCol="title_tf", outputCol="title_tfidf", minDocFreq=3),
        HashingTF(inputCol="tech_skills", outputCol="skills_tf", numFeatures=1 << 12, binary=True),
    ]
    for c in ("category", "province", "contract_type"):
        stages += [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep"),
                   OneHotEncoder(inputCol=f"{c}_idx", outputCol=f"{c}_ohe")]
    stages.append(VectorAssembler(inputCols=["title_tfidf", "skills_tf", "category_ohe", "province_ohe",
                                             "contract_type_ohe", "exp_years"], outputCol="features"))
    regression = {}
    for name, reg in (("Spark LinearRegression (ElasticNet)", LinearRegression(maxIter=100, regParam=0.01, elasticNetParam=0.1)),
                      ("Spark GBTRegressor", GBTRegressor(maxIter=20, maxDepth=5, seed=42))):
        t = time.time()
        pred = Pipeline(stages=stages + [reg]).fit(train).transform(test).withColumn("pred_salary", F.expm1("prediction"))
        ev = lambda m: RegressionEvaluator(labelCol="salary", predictionCol="pred_salary", metricName=m).evaluate(pred)  # noqa: E731,B023
        regression[name] = {"RMSE": round(ev("rmse"), 3), "MAE": round(ev("mae"), 3), "R2": round(ev("r2"), 3),
                            "seconds": round(time.time() - t, 1)}
        log(f"[MLlib] {name}: {regression[name]}")

    t = time.time()
    baskets = silver.select(F.array_distinct(F.concat("tech_skills", "soft_skills")).alias("items")).where(F.size("items") > 1)
    n_baskets = baskets.count()
    fp = FPGrowth(itemsCol="items", minSupport=0.008, minConfidence=0.25).fit(baskets)
    rules = fp.associationRules.orderBy(F.desc("lift"))
    n_rules = rules.count()
    top = [{"antecedent": r["antecedent"], "consequent": r["consequent"], "confidence": round(r["confidence"], 3),
            "lift": round(r["lift"], 2)} for r in rules.limit(15).collect()]
    log(f"[MLlib] FP-Growth: {n_baskets} giao dịch, {n_rules} luật")
    return {"regression": regression, "split": "80/20 ngẫu nhiên theo tin (khác cách chia 80/10/10 của mô hình chính)",
            "fp_growth": {"transactions": n_baskets, "min_support": 0.008, "min_confidence": 0.25, "rules": n_rules,
                          "top_rules": top, "seconds": round(time.time() - t, 1)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--lake", required=True, help="Thư mục Parquet (đường dẫn ASCII)")
    ap.add_argument("--export", required=True, help="Thư mục ghi JSON kết quả cho API")
    ap.add_argument("--cleaning", required=True, help="Bản chép của pipeline/cleaning.py, tên vj_cleaning.py")
    # local[*,8]: dùng mọi lõi CPU, mỗi task được thử lại tối đa 8 lần (mặc định local mode không thử lại)
    ap.add_argument("--master", default="local[*,8]")
    ap.add_argument("--partitions", type=int, default=8)
    ap.add_argument("--ml", action="store_true")
    args = ap.parse_args()

    t_all = time.time()
    spark = (SparkSession.builder.appName("VietJobs-Lakehouse").master(args.master)
             .config("spark.sql.shuffle.partitions", str(args.partitions)).config("spark.driver.memory", "4g")
             .config("spark.sql.execution.arrow.pyspark.enabled", "true").config("spark.ui.showConsoleProgress", "false")
             # Windows không có daemon Python: mỗi task khởi động worker mới, khi máy bận có thể chậm hơn mức mặc định
             .config("spark.python.authenticate.socketTimeout", "180s")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    if os.name != "nt":  # addPyFile cần winutils trên Windows; ở local mode worker đã thấy module qua PYTHONPATH
        spark.sparkContext.addPyFile(args.cleaning)
    parallelism = spark.sparkContext.defaultParallelism
    log(f"Spark {spark.version}, master={args.master}, {parallelism} luồng song song, {args.partitions} partition")
    st = Stages()
    lake = Path(args.lake)
    export = Path(args.export)
    (export / "gold").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ Bronze: dữ liệu gốc dạng cột, chưa sửa nội dung
    t = time.time()
    raw = (spark.read.option("header", True).option("multiLine", True).option("escape", '"').option("quote", '"')
           .csv(args.csv))
    for c in raw.columns:
        raw = raw.withColumn(c, F.when(F.col(c).isin(NA_VALUES), None).otherwise(F.col(c)))
    raw = (raw.withColumn("salary_min", F.col("salary_min").cast("int")).withColumn("salary_max", F.col("salary_max").cast("int"))
           .withColumn("row_no", F.monotonically_increasing_id()))
    # CSV nhiều dòng không chia nhỏ được khi đọc (chỉ 1 partition), nên phải chia lại để các bước sau chạy song song
    input_partitions = raw.rdd.getNumPartitions()
    bronze = raw.repartition(args.partitions).cache()
    n_raw = bronze.count()
    files = write_parquet(bronze, str(lake / "bronze"))
    st.add("Bronze", t, rows_in=n_raw, rows_out=n_raw, input_partitions=input_partitions, partitions=args.partitions, files=files)

    # ------------------------------------------------------------ Silver: gộp tin trùng, chuẩn hoá theo đúng luật ETL
    t = time.time()
    base = bronze.where(F.col("job_title").isNotNull()).withColumn(
        "category", F.lower(F.trim(F.coalesce("category", F.lit("chưa_phân_loại")))))
    other = [c for c in base.columns if c not in DUP_KEY + ["row_no", "category"]]
    # min_by(row_no): giữ dòng xuất hiện đầu tiên trong file, giống drop_duplicates của pandas, kết quả ổn định giữa các lần chạy
    grouped = base.groupBy(*DUP_KEY).agg(
        F.collect_set("category").alias("categories"), F.count("*").alias("source_rows"),
        F.min("row_no").alias("job_key"), *[F.min_by(c, "row_no").alias(c) for c in other])
    silver = grouped.mapInPandas(clean_partition, CLEAN_SCHEMA).cache()
    n_jobs = silver.count()
    files = write_parquet(silver, str(lake / "silver"))
    st.add("Silver", t, rows_in=n_raw, rows_out=n_jobs, partitions=silver.rdd.getNumPartitions(), files=files)

    # ------------------------------------------------------------ Gold: bảng tổng hợp phục vụ phân tích
    t = time.time()
    gold = build_gold(silver)
    exported = {}
    for name, df in gold.items():
        rows = [r.asDict(recursive=True) for r in df.collect()]
        exported[name] = len(rows)
        write_table(rows, lake / "gold" / f"{name}.parquet")   # bảng Gold nhỏ, đã thu về driver, ghi một file là đủ
        (export / "gold" / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    st.add("Gold", t, rows_in=n_jobs, rows_out=sum(exported.values()), tables=exported)

    # ------------------------------------------------------------ Số liệu đối soát với PostgreSQL
    median_exp = {r["experience_bucket"]: r["median_salary"]
                  for r in gold["salary_by_experience"].collect()}
    agg = silver.agg(F.sum(F.when(F.size("categories") > 1, 1).otherwise(0)).alias("multi"),
                     F.sum(F.when(F.col("sal_avg").between(SAL_LO, SAL_HI), 1).otherwise(0)).alias("paid"),
                     F.sum(F.size("tech_skills") + F.size("soft_skills")).alias("links"),
                     F.sum("source_rows").alias("rows")).first()
    reconcile = {"n_rows": n_raw, "n_jobs": n_jobs, "n_multi_category": agg["multi"], "n_salary": agg["paid"],
                 "n_skill_links": agg["links"], "source_rows_sum": agg["rows"], "median_by_experience": median_exp}

    # ------------------------------------------------------------ Spark MLlib (tuỳ chọn, vài phút)
    previous = {}
    metrics_file = export / "spark_metrics.json"
    if metrics_file.exists():
        previous = json.loads(metrics_file.read_text(encoding="utf-8"))
    mllib = previous.get("mllib")
    if args.ml:
        t = time.time()
        # GBT tự cache rất nhiều block. Giữ thêm Bronze, Silver trong cache làm bộ nhớ căng và task có thể kẹt vĩnh viễn ở
        # khoá block, nên giải phóng hết và đọc lại Silver từ Parquet (liệt kê file vì lý do winutils).
        spark.catalog.clearCache()
        mllib = run_mllib(spark.read.parquet(*[p.as_uri() for p in sorted((lake / "silver").glob("*.parquet"))]))
        st.add("MLlib", t, rows_in=n_jobs)

    metrics = {"spark_version": spark.version, "master": args.master, "parallelism": parallelism,
               "shuffle_partitions": args.partitions, "input_bytes": os.path.getsize(args.csv),
               "stages": st.items, "reconcile": reconcile, "mllib": mllib, "seconds_total": round(time.time() - t_all, 1),
               "lake_path": str(lake), "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    metrics_file.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Xong trong {metrics['seconds_total']}s. Bronze/Silver/Gold ở {lake}")
    spark.stop()


if __name__ == "__main__":
    main()
