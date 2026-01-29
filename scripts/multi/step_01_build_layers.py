"""Customer and account layer ingestion (Step 1).

Builds staging_db.nested_layer_stage as the foundation for downstream lineage steps.
"""

from datetime import datetime
from pyspark.sql import SparkSession

STEP_TAG = "[Step01]"
APP_NAME = "Lineage Step 01 - Build Layers"
TARGET_TABLE = "staging_db.nested_layer_stage"


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

    _log(f"Starting build for load_date={active_load_date}")
    _log("Reading sources: staging_db.customer, staging_db.account, staging_db.transaction, core_db archival tables")
    _log(f"Writing target: {TARGET_TABLE}")

    df_base = spark.sql(f"""
        SELECT DISTINCT
            c.customer_id,
            c.name,
            a.account_id,
            a.account_type,
            a.status,
            t.txn_id,
            t.amount,
            t.txn_type,
            t.txn_date,
            COALESCE(c.segment, 'UNKNOWN') AS segment,
            '{active_load_date}' AS load_date
        FROM staging_db.customer c
        LEFT JOIN staging_db.account a
            ON c.customer_id = a.customer_id
           AND a.load_date = '{active_load_date}'
        LEFT JOIN (
            SELECT account_id, txn_id, amount, txn_type, txn_date, merchant_id
            FROM staging_db.transaction
            WHERE load_date = '{active_load_date}'
              AND txn_date >= DATE_SUB(CURRENT_DATE(), 30)
        ) t
            ON a.account_id = t.account_id
    """)
    df_base.createOrReplaceTempView("base_layer")

    df_union = spark.sql(f"""
        SELECT * FROM base_layer
        UNION
        SELECT
            c.customer_id,
            c.name,
            a.account_id,
            a.account_type,
            a.status,
            tx.txn_id,
            tx.amount,
            tx.txn_type,
            tx.txn_date,
            COALESCE(c.segment, 'UNKNOWN') AS segment,
            '{active_load_date}' AS load_date
        FROM core_db.archived_customer c
        INNER JOIN core_db.archived_account a
            ON c.customer_id = a.customer_id
        LEFT JOIN core_db.archived_transaction tx
            ON a.account_id = tx.account_id
           AND tx.txn_date > '2023-01-01'
    """)
    df_union.createOrReplaceTempView("union_layer")

    df_nested = spark.sql(f"""
        SELECT
            u.customer_id,
            u.account_id,
            u.account_type,
            SUM(CASE WHEN u.txn_type = 'DEBIT' THEN u.amount ELSE 0 END) AS total_debit,
            SUM(CASE WHEN u.txn_type = 'CREDIT' THEN u.amount ELSE 0 END) AS total_credit,
            COUNT(DISTINCT u.txn_id) AS txn_count,
            seg.segment_name,
            COALESCE(r.region, 'UNKNOWN') AS region,
            MAX(u.txn_date) AS last_txn_date,
            prod.product_name,
            prod.product_category,
            br.branch_name,
            br.branch_region,
            merch.merchant_category
        FROM union_layer u
        LEFT JOIN (
            SELECT DISTINCT customer_id, segment_name
            FROM core_db.segmentation_rules
        ) seg
            ON u.customer_id = seg.customer_id
        LEFT JOIN (
            SELECT cust_id, region
            FROM core_db.customer_region
            WHERE active_flag = 'Y'
        ) r
            ON u.customer_id = r.cust_id
        LEFT JOIN (
            SELECT account_id, product_name, product_category
            FROM core_db.product_dim
        ) prod
            ON u.account_id = prod.account_id
        LEFT JOIN (
            SELECT account_id, branch_name, branch_region
            FROM core_db.branch_dim
        ) br
            ON u.account_id = br.account_id
        LEFT JOIN (
            SELECT merchant_id, merchant_category
            FROM core_db.merchant_dim
        ) merch
            ON u.txn_id IS NOT NULL AND u.txn_id = merch.merchant_id
        GROUP BY
            u.customer_id, u.account_id, u.account_type,
            seg.segment_name, r.region,
            prod.product_name, prod.product_category,
            br.branch_name, br.branch_region,
            merch.merchant_category
    """)

    df_nested.write.mode("overwrite").saveAsTable(TARGET_TABLE)

    _log("Completed successfully")


if __name__ == "__main__":
    run()
