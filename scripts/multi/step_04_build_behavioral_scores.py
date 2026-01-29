"""Behavioral scoring build (Step 4).

Creates staging_db.customer_score_stage from enriched features.
"""

from datetime import datetime
from pyspark.sql import SparkSession

STEP_TAG = "[Step04]"
APP_NAME = "Lineage Step 04 - Build Behavioral Scores"
SOURCE_TABLE = "staging_db.customer_features_stage"
TARGET_TABLE = "staging_db.customer_score_stage"


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

    _log(f"Starting behavioral scoring for load_date={active_load_date}")
    _log(f"Reading source: {SOURCE_TABLE}")
    _log("Supplementing with: staging_db.account, staging_db.transaction")
    _log(f"Writing target: {TARGET_TABLE}")

    df_scores = spark.sql(f"""
        WITH feat AS (
            SELECT * FROM staging_db.customer_features_stage
        ),
        txn_90d AS (
            SELECT
                a.customer_id,
                COUNT(DISTINCT t.txn_id) AS txn_cnt_90d,
                SUM(CASE WHEN t.txn_type = 'DEBIT' THEN t.amount ELSE 0 END) AS debit_90d,
                SUM(CASE WHEN t.txn_type = 'CREDIT' THEN t.amount ELSE 0 END) AS credit_90d,
                MAX(t.txn_date) AS last_txn_date_90d
            FROM staging_db.account a
            JOIN staging_db.transaction t
                ON a.account_id = t.account_id
            WHERE t.load_date = '{active_load_date}'
              AND t.txn_date >= DATE_SUB(CURRENT_DATE(), 90)
            GROUP BY a.customer_id
        ),
        baseline AS (
            SELECT
                segment_name,
                region,
                AVG(total_debit) AS avg_debit_peer,
                STDDEV_SAMP(total_debit) AS std_debit_peer,
                AVG(txn_count) AS avg_txn_peer,
                STDDEV_SAMP(txn_count) AS std_txn_peer
            FROM feat
            GROUP BY segment_name, region
        )
        SELECT
            f.*,
            t.txn_cnt_90d,
            t.debit_90d,
            t.credit_90d,
            t.last_txn_date_90d,

            CASE
                WHEN b.std_debit_peer IS NULL OR b.std_debit_peer = 0 THEN 0
                WHEN (f.total_debit - b.avg_debit_peer) / b.std_debit_peer >= 3 THEN 1
                ELSE 0
            END AS debit_spike_flag,

            CASE
                WHEN b.std_txn_peer IS NULL OR b.std_txn_peer = 0 THEN 0
                WHEN (f.txn_count - b.avg_txn_peer) / b.std_txn_peer >= 3 THEN 1
                ELSE 0
            END AS txn_velocity_spike_flag,

            (
                10 * COALESCE(f.debit_limit_breach_flag,0) +
                10 * COALESCE(f.credit_limit_breach_flag,0) +
                15 * COALESCE(CASE WHEN f.merchant_risk_band = 'HIGH' THEN 1 ELSE 0 END,0) +
                20 * COALESCE(CASE WHEN f.activity_band = 'HIGH_ACTIVITY' THEN 1 ELSE 0 END,0) +
                25 * COALESCE(CASE
                    WHEN b.std_debit_peer IS NULL OR b.std_debit_peer = 0 THEN 0
                    WHEN (f.total_debit - b.avg_debit_peer) / b.std_debit_peer >= 3 THEN 1
                    ELSE 0
                END,0) +
                20 * COALESCE(CASE
                    WHEN b.std_txn_peer IS NULL OR b.std_txn_peer = 0 THEN 0
                    WHEN (f.txn_count - b.avg_txn_peer) / b.std_txn_peer >= 3 THEN 1
                    ELSE 0
                END,0)
            ) AS internal_behavior_score

        FROM feat f
        LEFT JOIN txn_90d t
            ON f.customer_id = t.customer_id
        LEFT JOIN baseline b
            ON f.segment_name = b.segment_name
           AND f.region = b.region
    """)

    df_scores.write.mode("overwrite").saveAsTable(TARGET_TABLE)

    _log("Completed successfully")


if __name__ == "__main__":
    run()
