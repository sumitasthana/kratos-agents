"""Customer feature enrichment (Step 3).

Materializes staging_db.customer_features_stage with behavioral metrics.
"""

from datetime import datetime
from pyspark.sql import SparkSession

STEP_TAG = "[Step03]"
APP_NAME = "Lineage Step 03 - Enrich Customer Features"
SOURCE_TABLE = "staging_db.nested_layer_stage"
TARGET_TABLE = "staging_db.customer_features_stage"


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

    _log(f"Starting feature enrichment for load_date={active_load_date}")
    _log(f"Reading source: {SOURCE_TABLE}")
    _log("Augmenting with: core_db.account_limits, core_db.region_currency_map, core_db.fx_rates, core_db.merchant_category_risk_map")
    _log(f"Writing target: {TARGET_TABLE}")

    df_enriched = spark.sql(f"""
        WITH base AS (
            SELECT
                n.*,
                (n.total_credit - n.total_debit) AS net_flow,
                CASE
                    WHEN n.txn_count = 0 THEN 0
                    ELSE (n.total_debit + n.total_credit) / n.txn_count
                END AS avg_txn_amount,
                CASE
                    WHEN n.total_debit = 0 THEN NULL
                    ELSE n.total_credit / n.total_debit
                END AS credit_to_debit_ratio
            FROM staging_db.nested_layer_stage n
        ),
        lim AS (
            SELECT
                account_id,
                MAX(daily_debit_limit) AS daily_debit_limit,
                MAX(daily_credit_limit) AS daily_credit_limit
            FROM core_db.account_limits
            WHERE active_flag = 'Y'
            GROUP BY account_id
        ),
        fx AS (
            SELECT region, currency_code
            FROM core_db.region_currency_map
            WHERE active_flag = 'Y'
        ),
        fx_rate AS (
            SELECT currency_code, rate_to_usd
            FROM core_db.fx_rates
            WHERE as_of_date = '{active_load_date}'
        ),
        merch_risk AS (
            SELECT
                merchant_category,
                CASE
                    WHEN merchant_category IN ('GAMBLING','CRYPTO','HIGH_RISK_SERVICES') THEN 'HIGH'
                    WHEN merchant_category IN ('TRAVEL','LUXURY_RETAIL') THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS merchant_risk_band
            FROM core_db.merchant_category_risk_map
        )
        SELECT
            b.*,

            lim.daily_debit_limit,
            lim.daily_credit_limit,
            CASE WHEN lim.daily_debit_limit IS NOT NULL AND b.total_debit > lim.daily_debit_limit THEN 1 ELSE 0 END AS debit_limit_breach_flag,
            CASE WHEN lim.daily_credit_limit IS NOT NULL AND b.total_credit > lim.daily_credit_limit THEN 1 ELSE 0 END AS credit_limit_breach_flag,

            fx.currency_code,
            fxr.rate_to_usd,
            CASE
                WHEN fxr.rate_to_usd IS NULL THEN NULL
                ELSE b.net_flow * fxr.rate_to_usd
            END AS net_flow_usd,

            mr.merchant_risk_band,

            CASE
                WHEN b.txn_count >= 50 AND b.total_debit >= 5000 THEN 'HIGH_ACTIVITY'
                WHEN b.txn_count >= 15 THEN 'MEDIUM_ACTIVITY'
                ELSE 'LOW_ACTIVITY'
            END AS activity_band
        FROM base b
        LEFT JOIN lim
            ON b.account_id = lim.account_id
        LEFT JOIN fx
            ON b.region = fx.region
        LEFT JOIN fx_rate fxr
            ON fx.currency_code = fxr.currency_code
        LEFT JOIN merch_risk mr
            ON b.merchant_category = mr.merchant_category
    """)

    df_enriched.write.mode("overwrite").saveAsTable(TARGET_TABLE)

    _log("Completed successfully")


if __name__ == "__main__":
    run()
