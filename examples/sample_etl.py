# Sample ETL script for testing lineage extraction
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("SampleETL").getOrCreate()

# Read from source tables
customers_df = spark.read.table("raw_customers")
orders_df = spark.read.table("raw_orders")

# Join and transform
result_df = customers_df.join(
    orders_df,
    customers_df.customer_id == orders_df.customer_id,
    "inner"
).select(
    customers_df.customer_id,
    customers_df.customer_name,
    orders_df.order_id,
    orders_df.order_amount
)

# Write to target table
result_df.write.mode("overwrite").saveAsTable("reporting_customer_orders")
