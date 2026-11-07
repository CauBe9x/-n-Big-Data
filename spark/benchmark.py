"""Đo hiệu năng thực tế của tầng Spark để trả lời hai câu hỏi một cách trung thực:
  1. Thêm lõi CPU có giúp Spark nhanh hơn không? (cố định dữ liệu ×20, đổi local[1|2|4])
  2. Khi nào Spark đáng dùng hơn pandas? (cố định 4 lõi, nhân bản dữ liệu ×1, ×5, ×20, ×50)

Đo số lõi trên ×20 vì ở cỡ dữ liệu gốc phần lớn thời gian là chi phí điều phối, kết quả chỉ phản ánh nhiễu.
Dữ liệu nhân bản là bản sao của Silver, chỉ tồn tại trong bộ nhớ khi đo, không đi vào bất kỳ phân tích nào.
Tải đo: lương trung vị theo ngành, đếm tin theo tỉnh, đếm kỹ năng. Mỗi cấu hình đo 3 lần, lấy trung vị.

Chạy qua: cd backend && python -m pipeline.spark_job --benchmark
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

REPEATS = 3
CORE_FACTOR = 20
COLUMNS = ["categories", "province", "sal_avg", "tech_skills"]


def log(msg: str) -> None:
    print(msg, flush=True)


def session(master: str) -> SparkSession:
    spark = (SparkSession.builder.appName("VietJobs-Benchmark").master(master)
             .config("spark.sql.shuffle.partitions", "8").config("spark.driver.memory", "4g")
             .config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def spark_workload(df) -> None:
    paid = df.where(F.col("sal_avg").between(1, 150))
    paid.withColumn("c", F.explode("categories")).groupBy("c").agg(F.percentile_approx("sal_avg", 0.5)).collect()
    df.groupBy("province").count().collect()
    df.select(F.explode("tech_skills").alias("s")).groupBy("s").count().orderBy(F.desc("count")).limit(50).collect()


def pandas_workload(df: pd.DataFrame) -> None:
    paid = df[df["sal_avg"].between(1, 150)]
    paid[["categories", "sal_avg"]].explode("categories").groupby("categories")["sal_avg"].median()
    df.groupby("province").size()
    df["tech_skills"].explode().value_counts().head(50)


def timed(fn, *args) -> float:
    samples = []
    for _ in range(REPEATS):
        t = time.perf_counter()
        fn(*args)
        samples.append(time.perf_counter() - t)
    return round(statistics.median(samples), 3)


def replicate(df, factor: int):
    copies = df.sparkSession.range(factor).withColumnRenamed("id", "copy")
    return df.crossJoin(F.broadcast(copies)).drop("copy")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", required=True)
    ap.add_argument("--export", required=True)
    args = ap.parse_args()
    # Liệt kê file tường minh: trên Windows, đọc cả thư mục cần thư viện native của Hadoop (winutils), đọc từng file thì không
    files = [p.as_uri() for p in sorted(Path(args.silver).glob("*.parquet"))]

    cores = []
    for n in (1, 2, 4):
        spark = session(f"local[{n}]")
        df = replicate(spark.read.parquet(*files).select(*COLUMNS), CORE_FACTOR).repartition(8).cache()
        rows = df.count()
        spark_workload(df)  # lượt khởi động: nạp cache, biên dịch JIT
        sec = timed(spark_workload, df)
        cores.append({"cores": n, "seconds": sec, "rows": rows})
        log(f"[lõi] local[{n}]: {sec}s")
        spark.stop()
    for c in cores:
        c["speedup"] = round(cores[0]["seconds"] / c["seconds"], 2)

    base = pd.concat([pq.read_table(p, columns=COLUMNS).to_pandas() for p in sorted(Path(args.silver).glob("*.parquet"))],
                     ignore_index=True)
    sizes = []
    spark = session("local[4]")
    source = spark.read.parquet(*files).select(*COLUMNS)
    for factor in (1, 5, 20, 50):
        df = replicate(source, factor).repartition(8).cache()
        rows = df.count()
        spark_workload(df)
        spark_sec = timed(spark_workload, df)
        df.unpersist()
        big = pd.concat([base] * factor, ignore_index=True)
        pandas_sec = timed(pandas_workload, big)
        del big
        sizes.append({"factor": factor, "rows": rows, "spark_seconds": spark_sec, "pandas_seconds": pandas_sec})
        log(f"[cỡ] ×{factor} ({rows} dòng): Spark {spark_sec}s, pandas {pandas_sec}s")
    spark.stop()

    result = {"repeats": REPEATS, "workload": "Lương trung vị theo ngành, đếm tin theo tỉnh, top 50 kỹ năng",
              "core_factor": CORE_FACTOR, "note": "Dữ liệu nhân bản là bản sao của Silver, chỉ dùng để đo tốc độ.",
              "cores": cores, "sizes": sizes, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    out = Path(args.export)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Xong benchmark")


if __name__ == "__main__":
    main()
