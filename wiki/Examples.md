# Examples and Use Cases

Real-world examples of using Kratos for data engineering analysis.

---

## Example 1: Diagnosing Slow Spark Job

### Scenario
A Spark job that processes daily sales data has been running increasingly slower. It used to complete in 10 minutes but now takes 45 minutes.

### Analysis Steps

**Step 1: Generate Fingerprint**
```bash
python -m src.cli fingerprint /path/to/sales_etl_event_log.json
```

**Step 2: Ask About Performance**
```bash
python -m src.cli orchestrate \
  --from-log /path/to/sales_etl_event_log.json \
  --query "Why is my job running slow?"
```

### Results

```
ROOT CAUSES IDENTIFIED:

1. DATA GROWTH (Critical)
   - Input data grew from 2.5GB to 18.3GB over 3 months
   - Executor memory still configured for original size (1GB)
   - Causing 12.4GB memory spill to disk

2. PARTITION SKEW (High)
   - Partition for store_id=1234 contains 45% of all data
   - Single partition: 8.2GB
   - Median partition: 180MB
   - Ratio: 45x

3. INEFFICIENT JOIN (Medium)
   - Joining 18GB sales with 450MB product catalog
   - Product catalog not broadcast (under 1GB threshold)
   - Generating unnecessary 18GB shuffle

RECOMMENDATIONS:

Priority 1: Increase executor memory
  spark.executor.memory=4g
  Expected improvement: -20 minutes

Priority 2: Fix partition skew  
  df.repartition(500, "store_id", "sale_date")
  # Add salt for large store_id
  Expected improvement: -12 minutes

Priority 3: Broadcast small table
  sales.join(broadcast(products), "product_id")
  Expected improvement: -3 minutes
```

### Implementation

Applied recommendations:
```python
# Updated Spark configuration
spark = SparkSession.builder \
    .config("spark.executor.memory", "4g") \
    .config("spark.sql.autoBroadcastJoinThreshold", "500000000") \
    .getOrCreate()

# Fixed data skew
sales_df = sales_df.withColumn(
    "partition_key",
    when(col("store_id") == 1234, 
         concat(lit("1234_"), (rand() * 10).cast("int")))
    .otherwise(col("store_id"))
)
sales_df = sales_df.repartition(500, "partition_key", "sale_date")

# Broadcast join
result = sales_df.join(broadcast(products_df), "product_id")
```

### Outcome
- Job duration reduced from 45 minutes to **8 minutes**
- No memory spills
- Even partition distribution
- 82% improvement in runtime

---

## Example 2: Understanding Complex Query

### Scenario
Inherited a complex Spark job with no documentation. Need to understand what it does before making changes.

### Analysis Steps

```bash
python -m src.cli orchestrate \
  --from-log /path/to/mystery_job.json \
  --query "Explain what this query does step by step"
```

### Results

```
QUERY EXPLANATION:

PURPOSE:
  Computes customer lifetime value (CLV) with cohort analysis
  for marketing segmentation and retention prediction.

DATA FLOW:

1. READ SOURCES (Stages 0-2)
   
   a) Customer Transactions (main fact table)
      • Source: data_warehouse.transactions
      • Size: 125M rows, 45GB
      • Columns: customer_id, transaction_date, amount, product_id
      • Date Range: Last 24 months
   
   b) Customer Demographics
      • Source: crm.customer_profiles  
      • Size: 3.2M rows, 890MB
      • Columns: customer_id, signup_date, region, segment
   
   c) Product Catalog
      • Source: product_db.products
      • Size: 45K rows, 12MB
      • Columns: product_id, category, margin_pct

2. TRANSFORMATIONS (Stages 3-7)
   
   Stage 3-4: Customer Enrichment
   • Join transactions with customer demographics
   • Add cohort labels based on signup_date
   • Calculate months_since_signup
   
   Stage 5: Product Classification  
   • Join with product catalog
   • Classify transactions by product category
   • Apply margin percentages
   
   Stage 6: Cohort Aggregation
   • Group by: cohort_month, customer_id
   • Calculate per customer:
     - Total revenue
     - Total transactions
     - Unique products purchased
     - Average order value
     - Margin contribution
   
   Stage 7: CLV Computation
   • Group by cohort_month
   • Calculate cohort metrics:
     - Cohort size (distinct customers)
     - Retention rate by month
     - Average revenue per customer
     - CLV (12-month projection)

3. OUTPUT (Stage 8)
   • Write to: analytics.customer_lifetime_value
   • Partitioned by: cohort_month
   • Format: Parquet with Snappy compression
   • Approx rows: 36 cohorts × detailed metrics

KEY BUSINESS LOGIC:
  [PASS] 24-month lookback for transaction history
  [PASS] Cohort = month of customer signup
  [PASS] CLV = (Avg monthly revenue × Retention rate × 12)
  [PASS] Includes margin-adjusted profitability
  [PASS] Used for customer segmentation and targeting
```

### Outcome
- Understood business logic in 30 seconds
- Identified key data sources and transformations
- Created documentation for future reference
- Confident to make safe modifications

---

## Example 3: Extracting Data Lineage

### Scenario
Need to understand data dependencies before migrating tables to new schema.

### Analysis Steps

**Step 1: Extract Lineage**
```bash
python -m src.cli lineage-extract \
  --folder /path/to/etl/scripts \
  --output lineage_report.json
```

**Step 2: Trace Specific Column**
```bash
python -m src.cli lineage-extract \
  --folder /path/to/etl/scripts \
  --trace-table analytics.customer_revenue \
  --trace-column annual_revenue \
  --trace-direction upstream
```

### Results

```
UPSTREAM LINEAGE: analytics.customer_revenue.annual_revenue

Dependency Chain:
  
  analytics.customer_revenue.annual_revenue (Target Column)
    ↑
    ├─ Transformation: SUM(monthly_rev.revenue)
    │  WHERE month BETWEEN start_of_year AND end_of_year
    ↑
  staging.monthly_customer_revenue.revenue
    ↑
    ├─ Transformation: SUM(daily_rev.amount)
    │  GROUP BY customer_id, MONTH(transaction_date)
    ↑
  staging.daily_transactions.amount
    ↑
    ├─ Transformation: CAST(raw_amount AS DECIMAL(10,2))
    │  WHERE status = 'completed'
    ↑
  raw.payment_events.raw_amount
    ↑
    └─ Source: External payment system (via Kafka)

AFFECTED TABLES (if raw.payment_events.raw_amount changes):
  [FAIL] staging.daily_transactions (2.3M rows daily)
  [FAIL] staging.monthly_customer_revenue (450K rows monthly)
  [FAIL] analytics.customer_revenue (3.2M rows)
  [FAIL] dashboard.revenue_dashboard (aggregated view)
  [FAIL] ml_features.revenue_predictions (ML pipeline)

BUSINESS IMPACT:
  - 5 downstream tables affected
  - 2 dashboards depend on this data
  - 1 ML pipeline consumes this feature
  
RECOMMENDATION:
  Create compatibility view during migration to avoid breaking changes.
```

### Outcome
- Full understanding of data dependencies
- Identified 5 affected downstream tables
- Created migration plan with compatibility layer
- No disruption to existing dashboards or ML pipelines

---

## Example 4: Git Repository Dataflow Analysis

### Scenario
Taking over a data pipeline project. Need to understand data sources, transformations, and outputs from code.

### Analysis Steps

**Step 1: Clone and Extract**
```bash
# Clone repository
python -m src.cli git-clone \
  https://github.com/company/data-pipeline.git \
  --dest data-pipeline

# Extract git artifacts  
python -m src.cli git-log \
  ./runs/cloned_repos/data-pipeline

# Analyze dataflow
python -m src.cli git-dataflow \
  --latest \
  --dir ./runs/git_artifacts \
  --llm
```

### Results

```
GIT DATAFLOW ANALYSIS

IDENTIFIED DATA SOURCES (9 sources):

1. PostgreSQL Databases:
   • customers_db.customers (read in: src/extract/customer_extractor.py)
   • orders_db.orders (read in: src/extract/order_extractor.py)
   • inventory_db.products (read in: src/extract/product_extractor.py)

2. Cloud Storage:
   • S3: s3://raw-data/clickstream/*.json (read in: src/extract/events_reader.py)
   • S3: s3://uploads/vendor-data/*.csv (read in: src/extract/vendor_loader.py)

3. APIs:
   • Stripe API: /v1/charges (read in: src/integrations/stripe_client.py)
   • Salesforce API: /services/data/v52.0/query (read in: src/integrations/sf_client.py)

4. Message Queues:
   • Kafka: user-events-topic (consumed in: src/streaming/event_consumer.py)
   • Kafka: inventory-updates (consumed in: src/streaming/inventory_sync.py)

DATA SINKS (7 destinations):

1. Data Warehouse (Redshift):
   • analytics.fact_orders (written in: src/load/order_loader.py)
   • analytics.dim_customers (written in: src/load/customer_loader.py)
   • analytics.fact_revenue (written in: src/transform/revenue_aggregator.py)

2. Data Lake (S3):
   • s3://processed/events/parquet/ (written in: src/streaming/event_writer.py)
   • s3://metrics/daily/ (written in: src/reporting/metrics_export.py)

3. Search & Cache:
   • Elasticsearch: product-catalog-index (written in: src/search/product_indexer.py)
   • Redis: customer-cache (written in: src/cache/customer_cache.py)

KEY TRANSFORMATIONS (identified from commits):

1. Customer Enrichment Pipeline:
   customers → join(orders) → aggregate(lifetime_value) → dim_customers
   
2. Revenue Attribution:
   orders → join(products, customers) → apply_margin → fact_revenue
   
3. Event Processing:
   kafka_events → validate → enrich → partition_by_date → S3

4. Search Indexing:
   products → transform_schema → add_search_fields → elasticsearch

PROCESS FLOWS (4 major pipelines):

Pipeline 1: Batch ETL (Daily at 2 AM)
  Extract: PostgreSQL → Transform: Spark → Load: Redshift
  
Pipeline 2: Streaming Events (Real-time)
  Consume: Kafka → Process: Flink → Write: S3 + Elasticsearch
  
Pipeline 3: API Integration (Hourly)
  Fetch: Stripe + Salesforce → Transform: pandas → Load: Redshift
  
Pipeline 4: Vendor Data (On upload)
  Trigger: S3 upload → Validate → Transform → Load: Redshift

DATA DOMAINS IDENTIFIED:
  • Customer Domain (3 sources, 2 sinks)
  • Order & Revenue Domain (4 sources, 3 sinks)
  • Product Catalog (2 sources, 2 sinks)
  • Events & Analytics (2 sources, 2 sinks)
```

### Outcome
- Complete understanding of data architecture in minutes
- Identified all data sources and destinations
- Mapped key transformations and pipelines
- Created architecture diagram from findings
- Ready to onboard and make contributions

---

## Example 5: Continuous Performance Monitoring

### Scenario
Set up automated performance monitoring in CI/CD pipeline to detect regressions early.

### Implementation

**GitHub Actions Workflow**
```yaml
name: Spark Job Performance Check

on:
  pull_request:
    paths:
      - 'spark_jobs/**'

jobs:
  performance-test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install Kratos
        run: |
          pip install -r requirements.txt
        working-directory: ./kratos
      
      - name: Run Spark Job (Test Dataset)
        run: |
          spark-submit \
            --conf spark.eventLog.enabled=true \
            --conf spark.eventLog.dir=/tmp/spark-logs \
            spark_jobs/sales_etl.py \
            --input test_data/sales_sample.parquet \
            --output /tmp/output
      
      - name: Analyze Performance
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          # Find latest event log
          LOG_FILE=$(ls -t /tmp/spark-logs/*.json | head -1)
          
          # Analyze with Kratos
          python -m src.cli orchestrate \
            --from-log $LOG_FILE \
            --query "Are there any performance issues or regressions?" \
            --output /tmp/kratos_analysis.json
        working-directory: ./kratos
      
      - name: Check for Regressions
        run: |
          # Parse Kratos output
          python scripts/check_regression.py \
            /tmp/kratos_analysis.json \
            performance_baseline.json
      
      - name: Comment on PR
        if: failure()
        uses: actions/github-script@v5
        with:
          script: |
            const fs = require('fs');
            const analysis = JSON.parse(
              fs.readFileSync('/tmp/kratos_analysis.json', 'utf8')
            );
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## [WARN] Performance Regression Detected\n\n${analysis.summary}`
            });
```

**Regression Check Script** (`scripts/check_regression.py`):
```python
import json
import sys

def check_regression(current_file, baseline_file):
    with open(current_file) as f:
        current = json.load(f)
    
    with open(baseline_file) as f:
        baseline = json.load(f)
    
    # Extract key metrics
    current_duration = current['metrics']['total_duration_ms']
    baseline_duration = baseline['metrics']['total_duration_ms']
    
    # Calculate regression percentage
    regression_pct = (
        (current_duration - baseline_duration) / baseline_duration * 100
    )
    
    # Threshold: 20% regression
    if regression_pct > 20:
        print(f"FAIL: Performance regression of {regression_pct:.1f}%")
        print(f"  Baseline: {baseline_duration}ms")
        print(f"  Current:  {current_duration}ms")
        sys.exit(1)
    else:
        print(f"PASS: Performance within acceptable range ({regression_pct:.1f}%)")
        sys.exit(0)

if __name__ == "__main__":
    check_regression(sys.argv[1], sys.argv[2])
```

### Outcome
- Automated performance checks on every PR
- Early detection of regressions
- Actionable feedback in PR comments
- Prevents performance issues from reaching production

---

## Tips and Best Practices

### 1. Start with Minimal Detail
```bash
# Faster analysis, lower API costs
python -m src.cli orchestrate \
  --from-log event.json \
  --query "your question" \
  --level minimal
```

### 2. Reuse Fingerprints
```bash
# Generate once
python -m src.cli fingerprint event.json

# Ask multiple questions
python -m src.cli orchestrate \
  --from-fingerprint runs/fingerprints/fingerprint_*.json \
  --query "Question 1"

python -m src.cli orchestrate \
  --from-fingerprint runs/fingerprints/fingerprint_*.json \
  --query "Question 2"
```

### 3. Use Dashboard for Exploration
```bash
# Run analysis
python -m src.cli orchestrate --from-log event.json --query "..."

# Explore interactively
cd dashboard && npm run server
# Visit http://localhost:4173
```

### 4. Combine Multiple Analyses
```python
# Performance + Understanding
orchestrator = SmartOrchestrator(fingerprint)

perf_result = await orchestrator.solve_problem(
    "Why is my job slow?"
)

understanding = await orchestrator.solve_problem(
    "What does this query do?"
)

# Combine insights
print(understanding.explanation)
print(perf_result.recommendations)
```

---

## Next Steps

- **[Spark Job Analysis](Spark-Job-Analysis)** - Deep dive into Spark analysis
- **[Git Dataflow Analysis](Git-Dataflow-Analysis)** - Git dataflow extraction
- **[Data Lineage Extraction](Data-Lineage-Extraction)** - Lineage tracing
- **[API Reference](API-Reference)** - Complete API documentation

---

**Last Updated**: February 2026  
**Examples**: 5 real-world scenarios
