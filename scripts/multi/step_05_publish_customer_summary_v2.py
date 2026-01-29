"""Customer summary publishing v2 with alerts (Step 5).

Creates final_db.customer_summary_v2 and alert outputs from behavioral scores.
"""

from datetime import datetime
from pyspark.sql import SparkSession

STEP_TAG = "[Step05]"
APP_NAME = "Lineage Step 05 - Publish Summary V2"
SOURCE_TABLE = "staging_db.customer_score_stage"
SUMMARY_TARGET = "final_db.customer_summary_v2"
ALERT_TARGET = "final_db.customer_alerts"


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

    _log(f"Starting publish v2 for load_date={active_load_date}")
    _log(f"Reading source: {SOURCE_TABLE}")
    _log(f"Writing summary target: {SUMMARY_TARGET}")
    _log(f"Writing alert target: {ALERT_TARGET}")

    df_summary_v2 = spark.sql(f"""
        WITH src AS (
            SELECT
                s.*,
                '{active_load_date}' AS load_date
            FROM staging_db.customer_score_stage s
        ),
        cust AS (
            SELECT
                customer_id,
                kyc_status,
                customer_type,
                pep_flag,
                aml_risk_rating
            FROM core_db.customer_master
            WHERE active_flag = 'Y'
        ),
        risk_ref AS (
            SELECT
                customer_id,
                AVG(score) AS official_risk_score
            FROM core_db.risk_assessment
            WHERE as_of_date = '{active_load_date}'
            GROUP BY customer_id
        )
        SELECT
            src.customer_id,
            COUNT(DISTINCT src.account_id) AS total_accounts,
            SUM(src.total_debit) AS total_debit,
            SUM(src.total_credit) AS total_credit,
            MAX(src.last_txn_date) AS last_txn_date,

            src.segment_name,
            src.region,
            src.product_name,
            src.product_category,
            src.branch_name,
            src.branch_region,
            src.merchant_category,

            MAX(src.debit_limit_breach_flag) AS debit_limit_breach_flag,
            MAX(src.credit_limit_breach_flag) AS credit_limit_breach_flag,
            MAX(src.debit_spike_flag) AS debit_spike_flag,
            MAX(src.txn_velocity_spike_flag) AS txn_velocity_spike_flag,

            MAX(src.internal_behavior_score) AS internal_behavior_score,
            MAX(src.risk_score) AS risk_score,
            MAX(r.official_risk_score) AS official_risk_score,

            MAX(c.kyc_status) AS kyc_status,
            MAX(c.customer_type) AS customer_type,
            MAX(c.pep_flag) AS pep_flag,
            MAX(c.aml_risk_rating) AS aml_risk_rating,

            '{active_load_date}' AS load_date
        FROM src
        LEFT JOIN cust c
            ON src.customer_id = c.customer_id
        LEFT JOIN risk_ref r
            ON src.customer_id = r.customer_id
        GROUP BY
            src.customer_id, src.segment_name, src.region, src.product_name,
            src.product_category, src.branch_name, src.branch_region, src.merchant_category
    """)

    df_summary_v2.write.mode("overwrite").saveAsTable(SUMMARY_TARGET)

    df_alerts = spark.sql(f"""
        SELECT
            customer_id,
            internal_behavior_score,
            risk_score,
            official_risk_score,
            pep_flag,
            aml_risk_rating,
            debit_limit_breach_flag,
            credit_limit_breach_flag,
            debit_spike_flag,
            txn_velocity_spike_flag,
            load_date,
            CASE
                WHEN pep_flag = 'Y' THEN 'PEP_FLAGGED'
                WHEN aml_risk_rating IN ('HIGH','VERY_HIGH') THEN 'AML_HIGH_RISK'
                WHEN internal_behavior_score >= 60 THEN 'BEHAVIORAL_SCORE_HIGH'
                WHEN debit_spike_flag = 1 OR txn_velocity_spike_flag = 1 THEN 'TRANSACTION_SPIKE'
                ELSE 'REVIEW'
            END AS alert_reason
        FROM final_db.customer_summary_v2
        WHERE pep_flag = 'Y'
           OR aml_risk_rating IN ('HIGH','VERY_HIGH')
           OR internal_behavior_score >= 60
           OR debit_spike_flag = 1
           OR txn_velocity_spike_flag = 1
    """)

    df_alerts.write.mode("overwrite").saveAsTable(ALERT_TARGET)

    _log("Completed successfully")


if __name__ == "__main__":
    run()
