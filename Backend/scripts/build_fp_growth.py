from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
from pyspark.ml.fpm import FPGrowth
from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build laptop specification association rules.")
    parser.add_argument("--catalog", type=Path, default=project_root / "Dataset" / "imputed_dataset.csv")
    parser.add_argument("--output", type=Path, default=project_root / "Backend" / "artifacts")
    parser.add_argument("--min-support", type=float, default=0.02)
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--max-rules", type=int, default=500)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spark = SparkSession.builder.appName("LaptopSpecificationFPGrowth").getOrCreate()
    catalog = spark.read.csv(str(args.catalog), header=True, inferSchema=True, multiLine=True, escape='"')

    ram = F.regexp_extract(F.lower(F.coalesce(F.col("ram_full"), F.lit(""))), r"(\d+(?:\.\d+)?)\s*gb", 1)
    refresh = F.regexp_extract(F.lower(F.coalesce(F.col("display_full"), F.lit(""))), r"(\d{2,3})\s*hz", 1)
    brand = F.regexp_replace(F.lower(F.trim(F.col("brand"))), r"[^a-z0-9]+", "_")
    os_name = F.regexp_extract(F.lower(F.coalesce(F.col("os"), F.lit(""))), r"(windows|linux|macos|chrome)", 1)
    storage = F.lower(F.coalesce(F.col("storage"), F.lit("")))
    gpu = F.lower(F.coalesce(F.col("gpu_full"), F.lit("")))
    empty = F.lit(None).cast("string")
    item_columns = [
        F.when(F.length(brand) > 0, F.concat(F.lit("brand_"), brand)).otherwise(empty),
        F.when(F.length(ram) > 0, F.concat(F.lit("ram_"), ram, F.lit("gb"))).otherwise(empty),
        F.when(storage.contains("ssd"), F.lit("storage_ssd")).otherwise(empty),
        F.when(storage.contains("nvme"), F.lit("storage_nvme")).otherwise(empty),
        F.when(storage.contains("hdd"), F.lit("storage_hdd")).otherwise(empty),
        F.when(gpu.rlike(r"\brtx\b"), F.lit("gpu_rtx")).otherwise(empty),
        F.when(gpu.rlike(r"\bgtx\b"), F.lit("gpu_gtx")).otherwise(empty),
        F.when(gpu.rlike(r"\bradeon\b"), F.lit("gpu_radeon")).otherwise(empty),
        F.when(gpu.rlike(r"\barc\b"), F.lit("gpu_arc")).otherwise(empty),
        F.when(F.length(refresh) > 0, F.concat(F.lit("display_"), refresh, F.lit("hz"))).otherwise(empty),
        F.when(F.length(os_name) > 0, F.concat(F.lit("os_"), os_name)).otherwise(empty),
    ]
    transactions = catalog.select(
        F.col("id"),
        F.array_distinct(F.array_compact(F.array(*item_columns))).alias("items"),
    ).filter(F.size("items") >= 2)
    model = FPGrowth(
        itemsCol="items",
        minSupport=args.min_support,
        minConfidence=args.min_confidence,
    ).fit(transactions)
    itemsets = [
        {"items": row.items, "frequency": int(row.freq)}
        for row in model.freqItemsets.collect()
    ]
    rows = model.associationRules.orderBy(F.desc("lift"), F.desc("confidence")).limit(args.max_rules).collect()
    rules = [
        {
            "antecedent": row.antecedent,
            "consequent": row.consequent,
            "confidence": round(float(row.confidence), 6),
            "lift": round(float(row.lift), 6),
            "support": round(float(row.support), 6),
        }
        for row in rows
    ]
    itemsets_path = args.output / "frequent_itemsets.parquet"
    rules_path = args.output / "association_rules.parquet"
    for path in (itemsets_path, rules_path):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    pd.DataFrame(itemsets).to_parquet(itemsets_path, index=False)
    pd.DataFrame(rules).to_parquet(rules_path, index=False)
    with (args.output / "association_rules.json").open("w", encoding="utf-8") as output:
        json.dump(rules, output, indent=2)
    spark.stop()
if __name__ == "__main__":
    main()
