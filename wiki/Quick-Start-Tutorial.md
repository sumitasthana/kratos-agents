# Quick Start Tutorial

Get started with Kratos in 5 minutes! This tutorial walks you through your first analysis.

---

## What You'll Learn

In this tutorial, you'll:
1. Generate a Spark job fingerprint
2. Ask questions using the orchestrator
3. Analyze git dataflow patterns
4. Extract data lineage from ETL scripts
5. View results in the dashboard

---

## Prerequisites

- Kratos installed ([Installation Guide](Installation-Guide))
- OpenAI API key configured
- Sample Spark event log (provided in `runs/spark_event_logs/` or use your own)

---

## Tutorial 1: Analyze a Spark Job

### Step 1: Generate a Fingerprint

A fingerprint is a structured summary of your Spark job execution.

```bash
# Generate fingerprint from a sample event log
python -m src.cli fingerprint runs/spark_event_logs/sample_log.json
```

**What happens:**
- Parses the Spark event log
- Creates a three-layer fingerprint (Semantic, Context, Metrics)
- Saves to `runs/fingerprints/fingerprint_TIMESTAMP.json`

**Output:**
```
✓ Parsed 1,234 events
✓ Generated fingerprint: fingerprint_20260209_014530.json
  - Semantic Hash: abc123def456
  - Query Stages: 5
  - Total Duration: 125.4s
  - Tasks: 450 (448 succeeded, 2 failed)
```

### Step 2: Ask Questions with the Orchestrator

The orchestrator uses AI agents to answer questions about your Spark job.

```bash
# Ask: Why is my job slow?
python -m src.cli orchestrate --from-log runs/spark_event_logs/sample_log.json \
  --query "Why is my Spark job slow?"
```

**What happens:**
1. Generates fingerprint (if not already done)
2. Analyzes your question
3. Routes to appropriate agents (Root Cause Agent)
4. Returns insights and recommendations

**Sample Output:**
```
═══════════════════════════════════════════════════════════════════════
  ANALYSIS RESULT [PERFORMANCE]
═══════════════════════════════════════════════════════════════════════

Query: Why is my Spark job slow?
Problem Type: performance
Confidence: 87%
Agents Used: Root Cause Agent

───────────────────────────────────────────────────────────────────────
  EXECUTIVE SUMMARY
───────────────────────────────────────────────────────────────────────

Your job is experiencing memory pressure with 6.2GB of data spilled to
disk during Stage 3. This is causing significant slowdown. Additionally,
data skew is detected in Stage 4 where partition 42 is 28x larger than
the median partition size.

───────────────────────────────────────────────────────────────────────
  ROOT CAUSES
───────────────────────────────────────────────────────────────────────

1. MEMORY SPILL (Critical)
   - 6.2GB spilled to disk in Stage 3
   - Executor memory: 1GB (insufficient)
   - Recommendation: Increase to 2GB

2. DATA SKEW (High)
   - Partition 42: 2.8GB (28x median)
   - Median partition: 100MB
   - Recommendation: Repartition by a different key

3. SHUFFLE OVERHEAD (Medium)
   - 4.5GB shuffle volume
   - 890 shuffle partitions
   - Recommendation: Optimize shuffle partitions

───────────────────────────────────────────────────────────────────────
  RECOMMENDATIONS
───────────────────────────────────────────────────────────────────────

Priority 1: Increase executor memory
  spark.executor.memory=2g

Priority 2: Fix data skew
  df.repartition(200, "better_key_column")

Priority 3: Optimize shuffle
  spark.sql.shuffle.partitions=200
```

### Step 3: Understand What the Query Does

```bash
# Ask: What does this query do?
python -m src.cli orchestrate --from-log runs/spark_event_logs/sample_log.json \
  --query "Explain what this query does"
```

**Sample Output:**
```
═══════════════════════════════════════════════════════════════════════
  QUERY EXPLANATION
═══════════════════════════════════════════════════════════════════════

This Spark job performs a sales analytics pipeline:

1. DATA SOURCES (Stage 0-1):
   - Reads sales transactions from "sales_db.transactions" (2.3M rows)
   - Reads customer data from "crm_db.customers" (450K rows)

2. TRANSFORMATIONS (Stage 2-3):
   - Joins sales with customers on customer_id
   - Filters transactions from last 30 days
   - Aggregates by region and product category

3. OUTPUT (Stage 4):
   - Computes total revenue, order count, avg order value per region
   - Writes results to "analytics.regional_sales_summary"

KEY OPERATIONS:
  • Hash Join (customers ⋈ transactions)
  • Filter (date >= current_date - 30)
  • GroupBy (region, category)
  • Aggregations (sum, count, avg)
```

---

## Tutorial 2: Analyze Git Dataflow

Extract dataflow patterns from a git repository's commit history.

### Step 1: Clone a Repository

```bash
# Clone a repository for analysis
python -m src.cli git-clone https://github.com/your-org/data-pipeline.git \
  --dest data-pipeline
```

**What happens:**
- Clones repository to `runs/cloned_repos/data-pipeline/`
- Preserves full git history

### Step 2: Extract Git Artifacts

```bash
# Extract commit diffs and metadata
python -m src.cli git-log ./runs/cloned_repos/data-pipeline
```

**What happens:**
- Extracts commit history
- Captures code diffs
- Saves to `runs/git_artifacts/git_artifacts_TIMESTAMP.json`

**Output:**
```
✓ Extracted 234 commits
✓ Analyzed 1,456 file changes
✓ Saved to: git_artifacts_20260209_015030.json
```

### Step 3: Analyze Dataflow Patterns

```bash
# Analyze with AI
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm
```

**What happens:**
1. Reads latest git artifacts
2. AI agents analyze code changes
3. Identifies data sources, sinks, joins, transformations
4. Saves results to `runs/git_dataflow/`

**Sample Output:**
```
═══════════════════════════════════════════════════════════════════════
  GIT DATAFLOW ANALYSIS
═══════════════════════════════════════════════════════════════════════

IDENTIFIED DATA SOURCES:
  • PostgreSQL: customers, orders, products
  • S3: s3://data-lake/raw/events/*.parquet
  • Kafka: user-events-topic

DATA SINKS:
  • Redshift: analytics.sales_summary
  • S3: s3://data-lake/processed/metrics/
  • Elasticsearch: customer-search-index

KEY TRANSFORMATIONS:
  1. orders ⋈ customers → enriched_orders
  2. enriched_orders.groupBy(region) → regional_metrics
  3. regional_metrics.window(7 days) → weekly_trends

PROCESS FLOWS:
  Raw Events → Validation → Enrichment → Aggregation → Storage
```

---

## Tutorial 3: Extract Data Lineage

Analyze ETL scripts to extract table and column-level lineage.

### Step 1: Prepare ETL Scripts

Place your ETL scripts in a folder (or use examples in `scripts/multi/`):

```
scripts/multi/
├── extract_customer_data.py
├── transform_sales.py
└── load_analytics.sql
```

### Step 2: Extract Lineage

```bash
# Extract lineage from all scripts in folder
python -m src.cli lineage-extract --folder ./scripts/multi
```

**What happens:**
1. Reads all .py and .sql files
2. AI agents extract table dependencies
3. Identifies column-level lineage
4. Saves to `runs/lineage/lineage_TIMESTAMP.json`

**Sample Output:**
```
═══════════════════════════════════════════════════════════════════════
  DATA LINEAGE EXTRACTION
═══════════════════════════════════════════════════════════════════════

TABLE DEPENDENCIES:
  source_db.customers → staging.customers_cleaned
  source_db.orders → staging.orders_validated
  staging.customers_cleaned + staging.orders_validated → analytics.customer_orders

COLUMN LINEAGE (analytics.customer_orders):
  • customer_id ← source_db.customers.id
  • customer_name ← source_db.customers.name
  • total_revenue ← SUM(source_db.orders.amount)
  • order_count ← COUNT(source_db.orders.id)
  • first_order_date ← MIN(source_db.orders.date)

TRANSFORMATION LOGIC:
  • Join customers and orders on customer_id
  • Filter orders where status = 'completed'
  • Aggregate by customer_id
```

### Step 3: Trace Column Dependencies

```bash
# Trace upstream dependencies for a specific column
python -m src.cli lineage-extract --folder ./scripts/multi \
  --trace-table analytics.customer_orders \
  --trace-column total_revenue \
  --trace-direction upstream
```

**Output:**
```
UPSTREAM LINEAGE: analytics.customer_orders.total_revenue

Path 1:
  analytics.customer_orders.total_revenue
    ← SUM(staging.orders_validated.amount)
      ← source_db.orders.amount
        ← raw_db.transactions.transaction_amount

Transformations Applied:
  1. CAST(transaction_amount AS DECIMAL) → orders.amount
  2. FILTER(status = 'completed') → orders_validated.amount
  3. SUM(amount) GROUP BY customer_id → customer_orders.total_revenue
```

---

## Tutorial 4: Explore Results in Dashboard

The dashboard provides interactive visualization of all analysis results.

### Step 1: Start the Dashboard

```bash
cd dashboard
npm run server
```

Visit **http://localhost:4173**

### Step 2: Browse Run History

The dashboard automatically:
- Shows your latest analysis run
- Lists all historical runs with timestamps
- Highlights key findings

### Step 3: Explore Visualizations

**For Spark Analysis:**
- View execution timeline
- See task distribution charts
- Review performance metrics
- Read AI-generated insights

**For Git Dataflow:**
- Interactive graph of data flows
- Source and sink nodes
- Transformation pipelines
- Code references

**For Lineage:**
- Table dependency graph
- Column-level lineage diagrams
- Upstream/downstream tracing
- Impact analysis visualization

---

## Common Commands Cheat Sheet

### Spark Job Analysis
```bash
# Generate fingerprint only
python -m src.cli fingerprint <event_log.json>

# Ask any question
python -m src.cli orchestrate --from-log <event_log.json> --query "<your question>"

# Performance analysis
python -m src.cli orchestrate --from-log <event_log.json> --query "Why is my job slow?"

# Query understanding
python -m src.cli orchestrate --from-log <event_log.json> --query "What does this query do?"

# Failure diagnosis
python -m src.cli orchestrate --from-log <event_log.json> --query "Why did my job fail?"
```

### Git Dataflow Analysis
```bash
# Clone and analyze
python -m src.cli git-clone <repo_url> --dest <folder_name>
python -m src.cli git-log ./runs/cloned_repos/<folder_name>
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm

# Include documentation files
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm --include-docs
```

### Data Lineage Extraction
```bash
# Extract from folder
python -m src.cli lineage-extract --folder <path/to/scripts>

# Extract from single file
python -m src.cli lineage-extract --scripts <script.py>

# Trace column dependencies
python -m src.cli lineage-extract --folder <path> \
  --trace-table <table_name> \
  --trace-column <column_name> \
  --trace-direction upstream
```

### Dashboard
```bash
# Development mode
cd dashboard && npm run dev  # Port 5173 with hot reload

# Production mode
cd dashboard && npm run build && npm run server  # Port 4173
```

---

## What's Next?

Now that you've completed the quick start tutorial:

1. **[Spark Job Analysis Guide](Spark-Job-Analysis)** - Deep dive into performance troubleshooting
2. **[Git Dataflow Guide](Git-Dataflow-Analysis)** - Advanced dataflow pattern extraction
3. **[Lineage Extraction Guide](Data-Lineage-Extraction)** - Complete lineage analysis
4. **[Dashboard Guide](Dashboard-Guide)** - Master the interactive UI
5. **[Agent System](Agent-System)** - Understand how AI agents work
6. **[Custom Agents](Custom-Agents)** - Build your own analysis agents

---

## Getting Help

- **[Troubleshooting](Troubleshooting)** - Common issues and solutions
- **[FAQ](FAQ)** - Frequently asked questions
- **[Examples](Examples)** - More real-world examples
- **[API Reference](API-Reference)** - Complete API documentation

---

**Last Updated**: February 2026  
**Estimated Time**: 15-20 minutes
