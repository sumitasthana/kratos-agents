# scripts/generate_spark_event_logs.py
# scripts/multi/generate_spark_event_logs.py
"""
Generate real Spark event logs for Kratos CLI testing
"""



import sys
import os

# Force PySpark to use the venv Python
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# Now import PySpark
# from pyspark.sql import SparkSession



# # Fix for Python 3.13 compatibility
# os.environ['PYSPARK_PYTHON'] = sys.executable
# os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, count, avg, when
from pathlib import Path

# Rest of your code...

"""
Generate real Spark event logs for Kratos CLI testing
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, count, avg, when
from pathlib import Path

# Ensure spark_events directory exists
spark_events_dir = Path('logs/raw/spark_events')
spark_events_dir.mkdir(parents=True, exist_ok=True)

print('Generating Spark event logs...')
print(f'Output directory: {spark_events_dir.absolute()}')

# Job 1: Financial ETL with aggregations
print('\n[1/3] Running: Financial ETL Job...')
spark = SparkSession.builder \
    .appName('FinancialETL_Demo') \
    .master('local[2]') \
    .config('spark.eventLog.enabled', 'true') \
    .config('spark.eventLog.dir', str(spark_events_dir)) \
    .getOrCreate()

# Create sample financial data
data = [
    (1, 'Alice', 50000, 'US'),
    (2, 'Bob', 60000, 'UK'),
    (3, 'Charlie', 70000, 'US'),
    (4, 'David', 55000, 'UK'),
    (5, 'Eve', 80000, 'US'),
    (6, 'Frank', 65000, 'CA'),
    (7, 'Grace', 75000, 'US'),
    (8, 'Henry', 58000, 'UK'),
] * 50

df = spark.createDataFrame(data, ['user_id', 'name', 'salary', 'country'])

# Perform aggregation
result = df.groupBy('country').agg(
    count('user_id').alias('total_users'),
    sum('salary').alias('total_salary'),
    avg('salary').alias('avg_salary')
).orderBy('total_salary', ascending=False)

print('Results:')
result.show()

spark.stop()
print('Job 1 complete')

# Job 2: Customer analytics with joins
print('\n[2/3] Running: Customer Analytics Job...')
spark = SparkSession.builder \
    .appName('CustomerAnalytics_Demo') \
    .master('local[2]') \
    .config('spark.eventLog.enabled', 'true') \
    .config('spark.eventLog.dir', str(spark_events_dir)) \
    .getOrCreate()

# Customers
customers = spark.createDataFrame([
    (1, 'Alice', 'Premium'),
    (2, 'Bob', 'Standard'),
    (3, 'Charlie', 'Premium'),
    (4, 'David', 'Standard'),
    (5, 'Eve', 'VIP'),
] * 20, ['customer_id', 'name', 'tier'])

# Orders
orders = spark.createDataFrame([
    (1, 1, 100.0),
    (2, 1, 150.0),
    (3, 2, 200.0),
    (4, 3, 300.0),
    (5, 4, 50.0),
    (6, 5, 500.0),
] * 30, ['order_id', 'customer_id', 'amount'])

# Join and aggregate
customer_summary = customers.join(orders, 'customer_id').groupBy('customer_id', 'name', 'tier').agg(
    count('order_id').alias('total_orders'),
    sum('amount').alias('total_spent'),
    avg('amount').alias('avg_order_value')
)

print('Customer Summary:')
customer_summary.show()

spark.stop()
print('Job 2 complete')

# Job 3: Complex transformation
print('\n[3/3] Running: Complex Pipeline Job...')
spark = SparkSession.builder \
    .appName('ComplexPipeline_Demo') \
    .master('local[2]') \
    .config('spark.eventLog.enabled', 'true') \
    .config('spark.eventLog.dir', str(spark_events_dir)) \
    .getOrCreate()

# Sales data
sales = spark.createDataFrame([
    (1, 'Product_A', 100, 'Q1'),
    (2, 'Product_B', 150, 'Q1'),
    (3, 'Product_A', 200, 'Q2'),
    (4, 'Product_C', 250, 'Q2'),
    (5, 'Product_B', 300, 'Q3'),
] * 40, ['sale_id', 'product', 'revenue', 'quarter'])

# Complex transformations
result = sales.groupBy('product', 'quarter').agg(sum('revenue').alias('total_revenue')).withColumn(
    'revenue_category',
    when(col('total_revenue') > 5000, 'High').when(col('total_revenue') > 2000, 'Medium').otherwise('Low')
)

print('Sales Analysis:')
result.show()

spark.stop()
print('Job 3 complete')

print('\n' + '='*70)
print('SUCCESS: All Spark jobs completed!')
print('='*70)
print(f'\nEvent logs saved to: {spark_events_dir.absolute()}')
print('\nGenerated logs:')

# List generated event logs
for log_file in spark_events_dir.glob('*'):
    if log_file.is_file():
        print(f'  - {log_file.name}')

print('\nNext step: Test with Kratos CLI')
for log_file in list(spark_events_dir.glob('*'))[:1]:
    if log_file.is_file():
        print(f'Example: python -m src.cli {log_file}')
