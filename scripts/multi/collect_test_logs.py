# scripts/collect_test_logs.py
"""
Collect comprehensive test logs for Kratos Agent Platform
Populates logs/raw/ with diverse data sources
"""

import logging
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestLogCollector:
    """Collects and generates test logs for Kratos platform testing."""
    
    def __init__(self, base_dir: str = "logs"):
        self.base_dir = Path(base_dir)
        self.raw_dir = self.base_dir / "raw"
        
        # Validate structure exists
        if not self.raw_dir.exists():
            logger.error(f"Log structure not found at {self.base_dir}")
            logger.error("Please run: python scripts/setup_log_storage.py first")
            sys.exit(1)
    
    def collect_all(self) -> None:
        """Run all collection tasks."""
        logger.info("="*70)
        logger.info("KRATOS LOG COLLECTION STARTED")
        logger.info("="*70)
        
        tasks = [
            ("Adding existing financial ETL log", self.add_financial_etl_log),
            ("Generating synthetic OpenLineage logs", self.generate_synthetic_openlineage),
            ("Creating sample ETL scripts", self.create_etl_samples),
            ("Cloning reference repositories", self.clone_reference_repos),
            ("Downloading public Spark logs", self.download_public_spark_logs),
        ]
        
        results = []
        for task_name, task_func in tasks:
            logger.info(f"\nTask: {task_name}")
            logger.info("-" * 70)
            try:
                task_func()
                results.append((task_name, "SUCCESS"))
                logger.info(f"Completed: {task_name}")
            except Exception as e:
                results.append((task_name, f"FAILED: {e}"))
                logger.error(f"Failed: {task_name} - {e}")
        
        self.print_summary(results)
    
    def add_financial_etl_log(self) -> None:
        """Add the existing financial ETL OpenLineage log."""
        output_file = self.raw_dir / "openlineage" / "financial_etl_demo.json"
        
        # Your actual log content (abbreviated for brevity - use full log)
        log_lines = [
            {
                "eventTime": "2026-01-28T16:43:25.779Z",
                "producer": "https://github.com/OpenLineage/OpenLineage/tree/1.15.0/integration/spark",
                "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent",
                "eventType": "START",
                "run": {
                    "runId": "019c057d-1347-738e-acaa-5391c7099076",
                    "facets": {
                        "spark_properties": {
                            "properties": {
                                "spark.master": "local[*]",
                                "spark.app.name": "Demo_Financial_ETL_PoC"
                            }
                        },
                        "processing_engine": {
                            "version": "3.5.3",
                            "name": "spark"
                        }
                    }
                },
                "job": {
                    "namespace": "my_local_poc_namespace",
                    "name": "demo_financial_et_l_po_c"
                },
                "inputs": [],
                "outputs": []
            },
            {
                "eventTime": "2026-01-28T16:43:47.614Z",
                "eventType": "COMPLETE",
                "run": {
                    "runId": "019c057d-5799-789e-8f5f-f1e1e5426bab"
                },
                "job": {
                    "namespace": "my_local_poc_namespace",
                    "name": "demo_financial_et_l_po_c.execute_insert_into_hadoop_fs_relation_command.Demo_demo_gold_users"
                },
                "inputs": [{
                    "namespace": "file",
                    "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_raw_users",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "user_id", "type": "long"},
                                {"name": "name", "type": "string"},
                                {"name": "raw_salary", "type": "long"},
                                {"name": "country", "type": "string"}
                            ]
                        }
                    }
                }],
                "outputs": [{
                    "namespace": "file",
                    "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_gold_users",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "user_id", "type": "long"},
                                {"name": "name", "type": "string"},
                                {"name": "annual_income", "type": "long"},
                                {"name": "country", "type": "string"},
                                {"name": "tax_rate", "type": "double"},
                                {"name": "tax_amount", "type": "double"},
                                {"name": "processed_at", "type": "timestamp"}
                            ]
                        },
                        "columnLineage": {
                            "fields": {
                                "user_id": {
                                    "inputFields": [{
                                        "namespace": "file",
                                        "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_raw_users",
                                        "field": "user_id"
                                    }]
                                },
                                "annual_income": {
                                    "inputFields": [{
                                        "namespace": "file",
                                        "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_raw_users",
                                        "field": "raw_salary"
                                    }]
                                },
                                "tax_amount": {
                                    "inputFields": [
                                        {
                                            "namespace": "file",
                                            "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_raw_users",
                                            "field": "raw_salary"
                                        },
                                        {
                                            "namespace": "file",
                                            "name": "/C:/Users/aruneshkumar.lal/Secret_project/Demo/demo_raw_users",
                                            "field": "country"
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }]
            }
        ]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in log_lines:
                f.write(json.dumps(line) + '\n')
        
        logger.info(f"Created: {output_file}")
        logger.info(f"Events: {len(log_lines)}")
    
    def generate_synthetic_openlineage(self) -> None:
        """Generate synthetic OpenLineage logs for testing edge cases."""
        scenarios = [
            ("success_simple", self._create_success_log()),
            ("multi_join", self._create_multi_join_log()),
            ("failed_pipeline", self._create_failed_log())
        ]
        
        for name, log_data in scenarios:
            output_file = self.raw_dir / "openlineage" / f"synthetic_{name}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                for event in log_data:
                    f.write(json.dumps(event) + '\n')
            
            logger.info(f"Generated: {output_file} ({len(log_data)} events)")
    
    def _create_success_log(self) -> list:
        """Create a simple successful pipeline log."""
        return [
            {
                "eventTime": "2026-02-10T10:00:00.000Z",
                "eventType": "START",
                "run": {"runId": "synthetic-success-001"},
                "job": {
                    "namespace": "test",
                    "name": "customer_etl_pipeline"
                },
                "inputs": [],
                "outputs": []
            },
            {
                "eventTime": "2026-02-10T10:05:30.000Z",
                "eventType": "COMPLETE",
                "run": {"runId": "synthetic-success-001"},
                "job": {
                    "namespace": "test",
                    "name": "customer_etl_pipeline"
                },
                "inputs": [{
                    "namespace": "s3",
                    "name": "s3://data/bronze/customers",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "customer_id", "type": "bigint"},
                                {"name": "name", "type": "string"},
                                {"name": "email", "type": "string"}
                            ]
                        }
                    }
                }],
                "outputs": [{
                    "namespace": "s3",
                    "name": "s3://data/gold/customer_summary",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "customer_id", "type": "bigint"},
                                {"name": "total_orders", "type": "bigint"},
                                {"name": "total_revenue", "type": "double"}
                            ]
                        }
                    },
                    "outputFacets": {
                        "outputStatistics": {"rowCount": 1500, "size": 45000}
                    }
                }]
            }
        ]
    
    def _create_multi_join_log(self) -> list:
        """Create a complex multi-join pipeline log."""
        return [
            {
                "eventTime": "2026-02-10T11:00:00.000Z",
                "eventType": "START",
                "run": {"runId": "synthetic-join-001"},
                "job": {
                    "namespace": "test",
                    "name": "multi_source_join_pipeline"
                },
                "inputs": [],
                "outputs": []
            },
            {
                "eventTime": "2026-02-10T11:15:45.000Z",
                "eventType": "COMPLETE",
                "run": {"runId": "synthetic-join-001"},
                "job": {
                    "namespace": "test",
                    "name": "multi_source_join_pipeline"
                },
                "inputs": [
                    {
                        "namespace": "s3",
                        "name": "s3://data/bronze/customers",
                        "facets": {"schema": {"fields": [
                            {"name": "customer_id", "type": "bigint"},
                            {"name": "name", "type": "string"}
                        ]}}
                    },
                    {
                        "namespace": "s3",
                        "name": "s3://data/bronze/orders",
                        "facets": {"schema": {"fields": [
                            {"name": "order_id", "type": "bigint"},
                            {"name": "customer_id", "type": "bigint"},
                            {"name": "amount", "type": "double"}
                        ]}}
                    },
                    {
                        "namespace": "s3",
                        "name": "s3://data/bronze/products",
                        "facets": {"schema": {"fields": [
                            {"name": "product_id", "type": "bigint"},
                            {"name": "product_name", "type": "string"}
                        ]}}
                    }
                ],
                "outputs": [{
                    "namespace": "s3",
                    "name": "s3://data/gold/order_analytics",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "customer_id", "type": "bigint"},
                                {"name": "customer_name", "type": "string"},
                                {"name": "total_orders", "type": "bigint"},
                                {"name": "total_amount", "type": "double"}
                            ]
                        }
                    },
                    "outputFacets": {
                        "outputStatistics": {"rowCount": 5000, "size": 150000}
                    }
                }]
            }
        ]
    
    def _create_failed_log(self) -> list:
        """Create a failed pipeline log."""
        return [
            {
                "eventTime": "2026-02-10T12:00:00.000Z",
                "eventType": "START",
                "run": {"runId": "synthetic-failed-001"},
                "job": {
                    "namespace": "test",
                    "name": "failing_pipeline"
                },
                "inputs": [],
                "outputs": []
            },
            {
                "eventTime": "2026-02-10T12:02:15.000Z",
                "eventType": "FAIL",
                "run": {
                    "runId": "synthetic-failed-001",
                    "facets": {
                        "errorMessage": {
                            "message": "FileNotFoundException: s3://data/bronze/missing_file.parquet",
                            "programmingLanguage": "python",
                            "stackTrace": "..."
                        }
                    }
                },
                "job": {
                    "namespace": "test",
                    "name": "failing_pipeline"
                },
                "inputs": [],
                "outputs": []
            }
        ]
    
    def create_etl_samples(self) -> None:
        """Create sample ETL scripts for lineage extraction testing."""
        
        # PySpark ETL script
        pyspark_script = '''"""
Customer Revenue Analysis Pipeline
Demonstrates medallion architecture with clear lineage
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, count, avg, current_timestamp

def main():
    spark = SparkSession.builder.appName("CustomerRevenue").getOrCreate()
    
    # Bronze Layer - Raw data
    customers = spark.read.parquet("s3://bronze/customers/")
    orders = spark.read.parquet("s3://bronze/orders/")
    products = spark.read.parquet("s3://bronze/products/")
    
    # Silver Layer - Cleaned and joined
    customer_orders = customers.join(orders, "customer_id") \\
        .select(
            col("customer_id"),
            col("customer_name"),
            col("order_id"),
            col("order_amount"),
            col("order_date")
        )
    
    customer_orders.write.mode("overwrite") \\
        .partitionBy("order_date") \\
        .parquet("s3://silver/customer_orders/")
    
    # Gold Layer - Business metrics
    customer_summary = spark.read.parquet("s3://silver/customer_orders/") \\
        .groupBy("customer_id", "customer_name") \\
        .agg(
            count("order_id").alias("total_orders"),
            sum("order_amount").alias("total_revenue"),
            avg("order_amount").alias("avg_order_value")
        ) \\
        .withColumn("computed_at", current_timestamp())
    
    customer_summary.write.mode("overwrite") \\
        .parquet("s3://gold/customer_summary/")
    
    spark.stop()

if __name__ == "__main__":
    main()
'''
        
        # SQL ETL script
        sql_script = '''-- Daily Sales Report ETL
-- Aggregates order data from multiple sources

CREATE OR REPLACE TABLE gold.daily_sales AS
SELECT 
    DATE(o.order_timestamp) AS sale_date,
    p.product_category,
    p.product_name,
    c.customer_segment,
    c.customer_region,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(o.order_amount) AS total_revenue,
    AVG(o.order_amount) AS avg_order_value,
    SUM(o.order_amount * 0.08) AS estimated_tax
FROM bronze.orders o
INNER JOIN bronze.products p 
    ON o.product_id = p.product_id
LEFT JOIN bronze.customers c 
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'completed'
  AND o.order_date >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY 
    sale_date, 
    p.product_category, 
    p.product_name,
    c.customer_segment,
    c.customer_region;
'''
        
        # Complex PySpark with UDFs
        complex_script = '''"""
Advanced Analytics Pipeline with UDFs and Window Functions
"""
from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import col, udf, row_number, lag, lead
from pyspark.sql.types import StringType

@udf(returnType=StringType())
def categorize_customer(total_spend):
    """Categorize customers by spend."""
    if total_spend > 10000:
        return "VIP"
    elif total_spend > 5000:
        return "Premium"
    else:
        return "Standard"

def main():
    spark = SparkSession.builder.appName("AdvancedAnalytics").getOrCreate()
    
    # Load data
    customers = spark.table("silver.customers")
    orders = spark.table("silver.orders")
    
    # Calculate customer metrics
    customer_metrics = orders.groupBy("customer_id") \\
        .agg(
            sum("order_amount").alias("total_spend"),
            count("order_id").alias("order_count")
        )
    
    # Apply categorization
    categorized = customer_metrics \\
        .withColumn("customer_tier", categorize_customer(col("total_spend")))
    
    # Window function for ranking
    window_spec = Window.partitionBy("customer_tier").orderBy(col("total_spend").desc())
    
    ranked = categorized \\
        .withColumn("rank_in_tier", row_number().over(window_spec)) \\
        .withColumn("prev_spend", lag("total_spend").over(window_spec)) \\
        .withColumn("next_spend", lead("total_spend").over(window_spec))
    
    # Write to gold
    ranked.write.mode("overwrite").saveAsTable("gold.customer_analytics")
    
    spark.stop()

if __name__ == "__main__":
    main()
'''
        
        scripts = [
            ("customer_revenue_pipeline.py", pyspark_script),
            ("daily_sales_report.sql", sql_script),
            ("advanced_analytics.py", complex_script)
        ]
        
        for filename, content in scripts:
            output_file = self.raw_dir / "etl_scripts" / filename
            output_file.write_text(content, encoding='utf-8')
            logger.info(f"Created: {output_file}")
    
    def clone_reference_repos(self) -> None:
        """Clone reference git repositories for dataflow analysis."""
        repos = [
            ("https://github.com/lykmapipo/Python-Spark-Log-Analysis.git", "Python-Spark-Log-Analysis"),
        ]
        
        for repo_url, repo_name in repos:
            dest = self.raw_dir / "git_repos" / repo_name
            
            if dest.exists():
                logger.info(f"Already exists: {dest}")
                continue
            
            try:
                logger.info(f"Cloning: {repo_name}")
                result = subprocess.run(
                    ["git", "clone", "--depth", "5", repo_url, str(dest)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    logger.info(f"Successfully cloned: {repo_name}")
                else:
                    logger.warning(f"Failed to clone {repo_name}: {result.stderr}")
            
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout cloning {repo_name}")
            except FileNotFoundError:
                logger.warning("Git not found. Install git to clone repositories.")
                break
            except Exception as e:
                logger.warning(f"Error cloning {repo_name}: {e}")
    
    def download_public_spark_logs(self) -> None:
        """Download public Spark event logs if available."""
        logger.info("Public Spark logs collection skipped (manual step)")
        logger.info("You can add Spark event logs manually to logs/raw/spark_events/")
    
    def print_summary(self, results: list) -> None:
        """Print collection summary."""
        logger.info("\n" + "="*70)
        logger.info("COLLECTION SUMMARY")
        logger.info("="*70)
        
        for task, status in results:
            status_symbol = "[OK]" if status == "SUCCESS" else "[FAIL]"
            logger.info(f"{status_symbol} {task}")
        
        # Count files
        stats = {}
        for subdir in ["openlineage", "etl_scripts", "git_repos"]:
            path = self.raw_dir / subdir
            if path.exists():
                count = sum(1 for _ in path.rglob("*") if _.is_file() and _.name != "README.md")
                stats[subdir] = count
        
        logger.info("\n" + "-"*70)
        logger.info("FILES COLLECTED:")
        for category, count in stats.items():
            logger.info(f"  {category}: {count} files")
        
        logger.info("="*70)
        logger.info("Next step: Test your parsers with these logs")
        logger.info("="*70 + "\n")


def main():
    """Main entry point."""
    collector = TestLogCollector()
    collector.collect_all()


if __name__ == "__main__":
    main()
