# Kratos Agents

## Multi-Agent Root Cause Analysis for Modern Data Platforms

> Intelligent, multi-agent RCA system for Spark, Airflow, code changes, data quality, and infrastructure — with a production-ready React dashboard.

---

## 🚀 Overview

Kratos is a **multi-agent orchestration system** that performs automated root cause analysis (RCA) across distributed data platforms.

It ingests:

* Spark execution logs
* Airflow task logs
* Dataset snapshots
* Git commit history
* Infrastructure / observability metrics

It then:

1. Routes inputs to specialized analyzers
2. Triangulates cross-domain signals
3. Generates structured `IssueProfile` objects
4. Produces prioritized `RecommendationReport` objects
5. Renders results in a React dashboard

This is not a single-agent LLM wrapper.
It is a **deterministic orchestration layer coordinating multiple analyzers**.
# Kratos

**Your AI-powered assistant for understanding Spark jobs, data pipelines, and code dataflow — all in plain English.**

[![GitHub Wiki](https://img.shields.io/badge/documentation-wiki-blue)](https://github.com/sumitasthana/kratos-agents/wiki)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

📚 **[Complete Documentation Available in Wiki](https://github.com/sumitasthana/kratos-agents/wiki)** - Installation guides, tutorials, examples, troubleshooting, and more!

---

## What Does This Tool Do?

Kratos is a comprehensive data engineering analysis platform that helps you understand and troubleshoot your data pipelines without needing to be an expert. It provides three main capabilities:

### 1. **Spark Job Analysis** 📊
Analyzes Apache Spark event logs to diagnose performance issues, explain query execution, and identify root causes of failures.

**You provide**: A Spark event log file (automatically generated when Spark jobs run)  
**Kratos creates**: A "fingerprint" — a structured summary of what happened during execution  
**AI agents analyze**: The fingerprint and explain issues in plain English

### 2. **Git Repository Dataflow Analysis** 🔄
Extracts data flow patterns from your git repository's commit history to understand how data moves through your codebase.

**You provide**: A git repository URL or local path  
**Kratos extracts**: Commit diffs and code changes  
**AI agents identify**: Data reads, writes, joins, transformations, and dataflow patterns

### 3. **Data Lineage Extraction** 🔗
Analyzes ETL scripts to extract table and column-level data lineage, helping you understand data dependencies.

**You provide**: Spark ETL scripts (.py, .sql)  
**Kratos extracts**: Table and column dependencies  
**AI agents trace**: Upstream and downstream data flows

### Example Questions It Can Answer:

- *"Why is my Spark job running slow?"* (Spark Analysis)
- *"What is this query actually doing?"* (Spark Analysis)
- *"Why did my job fail?"* (Spark Analysis)
- *"Where is the bottleneck in my data pipeline?"* (Spark Analysis)
- *"What data sources does this code read from?"* (Git Dataflow)
- *"Where does this table come from?"* (Lineage Extraction)
- *"What columns depend on customer_id?"* (Lineage Extraction)

---

## Quick Start (5 Minutes)

### Step 1: Install

```bash
pip install -r requirements.txt
```

### Step 2: Set Up Your API Key

Create a `.env` file with your OpenAI API key:
```
OPENAI_API_KEY=your-api-key-here
```

### Step 3: Choose Your Analysis Type

**Option A: Analyze a Spark Job**
```bash
# Ask a question about your Spark job (generates a fingerprint first)
python -m src.cli orchestrate --from-log your_event_log.json --query "Why is my Spark job slow?"

# Or generate a fingerprint only
python -m src.cli fingerprint your_event_log.json
```

**Option B: Analyze Git Repository Dataflow**
```bash
# Clone a repository and analyze dataflow patterns
python -m src.cli git-clone https://github.com/your-org/your-repo.git --dest your-repo
python -m src.cli git-log ./runs/cloned_repos/your-repo
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm
```

**Option C: Extract Data Lineage from ETL Scripts**
```bash
# Extract lineage from your ETL scripts
python -m src.cli lineage-extract --folder ./path/to/etl/scripts
```
# Kratos Agents — Spark Execution Analyzer

> Intelligent multi-agent system for automated Spark job analysis, root cause identification, and actionable performance recommendations.

---

## What It Does

Kratos ingests Spark execution logs, generates an **ExecutionFingerprint**, and routes it through a two-layer agent orchestration pipeline. The result is a structured RCA report surfaced in a React dashboard — with health scoring, severity-ranked findings, and green fix blocks attached directly to each issue.

---

# 🧠 What Kratos Analyzes

| Domain | Input            | Agent                                    | Output                        |
|--------|------------------|------------------------------------------|-------------------------------|
| Spark  | Event logs       | RootCauseAgent + QueryUnderstandingAgent | ExecutionFingerprint + RCA    |
| Airflow| Task logs        | AirflowLogAnalyzerAgent                  | Task health & workload summary|
| Data   | Dataset snapshot | DataProfilerAgent                        | Null spikes, schema drift     |
| Code   | Git history      | ChangeAnalyzerAgent                      | Churn risk, contributor silo  |
| Infra  | Cluster metrics  | InfraAnalyzerAgent                       | Resource pressure patterns    |

Each agent emits an `AgentResponse` which is transformed into an `AnalysisResult` for triangulation.

---

# 🏗 Architecture

```text
KratosOrchestrator
    │
    ▼
RoutingAgent
    │
    ├── SparkOrchestrator
    ├── AirflowLogAnalyzerOrchestrator
    ├── CodeAnalyzerOrchestrator
    ├── DataProfilerOrchestrator
    ├── ChangeAnalyzerOrchestrator
    └── InfraAnalyzerOrchestrator
           │
           ▼
    TriangulationAgent
           │
           ▼
    RecommendationAgent
           │
           ▼
    RecommendationReport
           │
           ▼
    React Dashboard (RCAFindings)
```

Each analyzer produces an `AnalysisResult`.

The **TriangulationAgent** merges results into a unified `IssueProfile`:

* `dominant_problem_type`
* `overall_health_score`
* `overall_confidence`
* `log_analysis`, `code_analysis`, `data_analysis`, `change_analysis`, `infra_analysis`
* `correlations` (cross-agent patterns)

The **RecommendationAgent** turns the `IssueProfile` into a `RecommendationReport`
with:

* `executive_summary`
* `prioritized_fixes`
* `ontology_update`
* `feedback_loop_signal`

---

# 📊 Dashboard

The Vite + React dashboard provides:

* Run history sidebar
* Health score visualization
* Analyzer status strip (Spark / Airflow / Code / Data / Change / Infra)
* Expandable findings per analyzer
* Cross-agent correlations
* Executive summary
* Prioritized fixes

The backend is UI-agnostic.
All visual interpretation is handled by React.

---

# 🏷 Problem Types

Kratos uses standardized classifications across agents:

| Type               | Description                                |
|--------------------|--------------------------------------------|
| HEALTHY            | No anomalies detected                      |
| EXECUTION_FAILURE  | Spark task failures dominate               |
| MEMORY_PRESSURE    | Spill or OOM patterns                      |
| SHUFFLE_OVERHEAD   | Excessive shuffle                          |
| DATA_SKEW          | Skew penalties dominate                    |
| NULL_SPIKE         | Data profiler detected null increase       |
| SCHEMA_DRIFT       | Column or type drift                       |
| CHURN_SPIKE        | Large change window in Git                 |
| CONTRIBUTOR_SILO   | Single-author dominance                    |
| REGRESSION_RISK    | Risky change before failure                |
| CORRELATED_FAILURE | Multi-agent pattern detected               |
| GENERAL            | No dominant issue                          |

Infra-specific labels (e.g. resource pressure) are expressed either as dedicated
problem types or via the text in `infra_analysis.problem_type` and correlations.

---

# 📐 Confidence Scoring (Spark Path)

Confidence for Spark RCA is derived from:

| Signal            | Max Points |
|-------------------|-----------:|
| Data completeness | 30         |
| Signal dominance  | 30         |
| Agent agreement   | 20         |
| Cause clarity     | 20         |

Minimum floor: **0.40**

No hardcoded confidence values.

---

# 🔗 Cross-Agent Correlation

The triangulation layer detects patterns such as:

* Churn spike + Spark failure
* Compliance gap + null spike
* Infra resource saturation + execution failure / memory pressure
* Schema drift + ETL regression

These are rendered as `CrossAgentCorrelation` objects in the dashboard, with:

* Pattern description
* Severity
* Contributing agents
* Confidence

---

# 📂 Project Structure

```text
kratos-agents/
├── src/
│   ├── orchestrator.py          # KratosOrchestrator, SparkOrchestrator, routing
│   ├── schemas.py               # Pydantic models (fingerprints, IssueProfile…)
│   ├── agent_coordination.py    # AgentContext, SharedFinding
│   ├── agents/
│   │   ├── base.py              # BaseAgent, AgentType
│   │   ├── root_cause.py        # Spark RCA
│   │   ├── query_understanding.py
│   │   ├── airflow_log_analyzer.py
│   │   ├── data_profiler_agent.py
│   │   ├── change_analyzer_agent.py
│   │   └── infra_analyzer_agent.py
│   ├── cli.py                   # CLI entry points
│   ├── context_generator.py     # Builds LLM context from fingerprints
│   └── semantic_generator.py    # DAG semantic layer
│
├── dashboard/
│   ├── src/
│   │   ├── App.tsx              # App shell, runs sidebar
│   │   └── RCAFindings.tsx      # RCA findings view (analyzers, correlations)
│   ├── server.js                # Static server + runs API
│   └── package.json
│
├── scripts/
│   └── multi/                   # Log generation / collection utilities
│
├── logs/                        # Raw + processed logs (gitignored)
├── screenshots/                 # Dashboard screenshots
├── requirements.txt
└── README.md
```

---

# ⚙ Setup

## Backend

```bash
git clone https://github.com/sumitasthana/kratos-agents.git
cd kratos-agents

python -m venv venv
# Mac/Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

---

## Dashboard

```bash
cd dashboard
npm install

npm run dev    # http://localhost:5173
npm run build
npm start      # http://localhost:4173
```

The dashboard server reads run artifacts from `logs/` by default (see console output).

---

# ▶ Running Kratos

## Spark
## Requirements

- Python 3.10+
- OpenAI API key (for AI analysis)
- Spark event log files (JSON format from Spark History Server)
- Node.js 16+ and npm (for the optional dashboard UI)

---

## Documentation

### 📚 Comprehensive Wiki
Visit our **[GitHub Wiki](https://github.com/sumitasthana/kratos-agents/wiki)** for complete documentation:

- **[Home](https://github.com/sumitasthana/kratos-agents/wiki/Home)** - Overview and navigation
- **[Installation Guide](https://github.com/sumitasthana/kratos-agents/wiki/Installation-Guide)** - Platform-specific installation
- **[Quick Start Tutorial](https://github.com/sumitasthana/kratos-agents/wiki/Quick-Start-Tutorial)** - Step-by-step getting started
- **[Spark Job Analysis](https://github.com/sumitasthana/kratos-agents/wiki/Spark-Job-Analysis)** - Performance troubleshooting guide
- **[Troubleshooting](https://github.com/sumitasthana/kratos-agents/wiki/Troubleshooting)** - Common issues and solutions
- **[FAQ](https://github.com/sumitasthana/kratos-agents/wiki/FAQ)** - Frequently asked questions (40+)
- **[Examples](https://github.com/sumitasthana/kratos-agents/wiki/Examples)** - Real-world use cases

### 📖 Additional Documentation
- [QUICKSTART.md](QUICKSTART.md) - Detailed installation and usage guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical deep dive
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation
- [WIKI_DEPLOYMENT.md](WIKI_DEPLOYMENT.md) - Instructions for deploying the wiki

---

## FAQ

**Q: Do I need to be a Spark expert to use this?**  
A: No! The tool explains everything in plain English.

**Q: What can Kratos analyze?**  
A: Kratos can analyze three types of data engineering artifacts:
1. **Spark event logs** - for performance troubleshooting and query understanding
2. **Git repositories** - for extracting dataflow patterns from code changes
3. **ETL scripts** - for extracting table and column-level data lineage

**Q: Where do I get Spark event log files?**  
A: Spark automatically generates them. Check your Spark History Server or the `spark.eventLog.dir` configuration.

**Q: Does it work with Databricks/EMR/Dataproc?**  
A: Yes, as long as you can export the event log JSON files.

**Q: How much does it cost?**  
A: The tool is free. You only pay for OpenAI API usage (typically a few cents per analysis).

**Q: Can I visualize the results?**  
A: Yes! Use the **Dashboard** web UI to interactively explore results with graphs, lineage diagrams, and formatted findings. See the Dashboard section above for setup instructions.

**Q: What's the difference between git-dataflow and lineage-extract?**  
A: 
- **git-dataflow**: Analyzes git commit history to extract dataflow patterns from code changes (great for understanding how data flows evolved)
- **lineage-extract**: Analyzes current ETL scripts to extract detailed table/column lineage (great for data governance and compliance)
## Running

```bash
python -m src.cli orchestrate \
  --log-path logs/raw/spark_events/log.json
```

## With Question

```bash
python -m src.cli orchestrate \
  --log-path logs/raw/spark_events/log.json \
  --query "Why is my job slow?"
```

## Airflow

```bash
python -m src.smoke_test_airflow
```

## With Data + Git

```bash
python -m src.smoke_test \
  --dataset-path dataset.parquet \
  --git-log-path change_fingerprint.json
```

## (Example) With Infra Metrics

Once you have an `infra_fingerprint` JSON (cluster metrics snapshot), you can
call `KratosOrchestrator.run(user_query, infra_fingerprint=...)` from Python,
or add a dedicated smoke test to generate a run the dashboard can visualize.

After running any of these commands, open the dashboard and inspect analyzer
cards and correlations.

---

# 🧩 Design Principles

* Deterministic orchestration over single-LLM reasoning
* Separation of analysis and presentation
* Negation-aware severity detection
* Two-phase classification logic (routing vs. health-derived override)
* Explicit schemas via Pydantic
* Expandable multi-agent architecture (Spark, Airflow, Data, Code, Infra)

---

# 🛠 Contributing

```bash
git checkout -b arunesh/<feature-name>

git commit -m "feat(orchestrator): add infra analyzer wiring

- describe change
- keep scope focused"
```

Open a pull request after pushing.

---

# 👥 Authors

* **sumitasthana** — Project Lead
* **AruneshDev** — Orchestration Engine, Multi-Agent RCA, Dashboard
