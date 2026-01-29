"""Customer summary publishing (Step 2).

Creates final_db.customer_summary from the nested staging layer.
"""

from datetime import datetime
from pyspark.sql import SparkSession

STEP_TAG = "[Step02]"
APP_NAME = "Lineage Step 02 - Publish Summary V1"
SOURCE_TABLE = "staging_db.nested_layer_stage"
TARGET_TABLE = "final_db.customer_summary"


def _log(message: str) -> None:
    print(f"{STEP_TAG} {message}")


def _build_spark_session() -> SparkSession:
    return (
        SparkSession.builder
        .appName(APP_NAME)
        .enableHiveSupport()
        .getOrCreate()
    )


def _current_load_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def run(load_date: str | None = None) -> None:
    spark = _build_spark_session()
    active_load_date = load_date or _current_load_date()

    _log(f"Starting publish for load_date={active_load_date}")
    _log(f"Reading source: {SOURCE_TABLE}")
    _log(f"Writing target: {TARGET_TABLE}")

    df_final = spark.sql(f"""
        SELECT
            n.customer_id,
            COUNT(DISTINCT n.account_id) AS total_accounts,
            SUM(n.total_debit) AS total_debit,
            SUM(n.total_credit) AS total_credit,
            MAX(n.last_txn_date) AS last_txn_date,
            n.segment_name,
            n.region,
            n.product_name,
            n.product_category,
            n.branch_name,
            n.branch_region,
            n.merchant_category,
            risk.risk_score
        FROM staging_db.nested_layer_stage n
        LEFT JOIN (
            SELECT customer_id, AVG(score) AS risk_score
            FROM core_db.risk_assessment
            WHERE as_of_date = '{active_load_date}'
            GROUP BY customer_id
        ) risk
            ON n.customer_id = risk.customer_id
        GROUP BY
            n.customer_id, n.segment_name, n.region, n.product_name,
            n.product_category, n.branch_name, n.branch_region,
            n.merchant_category, risk.risk_score
    """)

    df_final.write.mode("overwrite").saveAsTable(TARGET_TABLE)

    _log("Completed successfully")


if __name__ == "__main__":
    run()
