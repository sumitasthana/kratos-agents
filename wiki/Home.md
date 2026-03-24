# Welcome to Kratos Wiki

**Your AI-powered assistant for understanding Spark jobs, data pipelines, and code dataflow — all in plain English.**

[![GitHub stars](https://img.shields.io/github/stars/sumitasthana/kratos-agents?style=social)](https://github.com/sumitasthana/kratos-agents)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

---

## [DOCS] Quick Navigation

### Getting Started
- **[Installation Guide](Installation-Guide)** - Set up Kratos in 5 minutes
- **[Quick Start Tutorial](Quick-Start-Tutorial)** - Your first analysis
- **[Configuration](Configuration)** - Configure OpenAI API and settings

### Core Features
- **[Spark Job Analysis](Spark-Job-Analysis)** - Performance troubleshooting and diagnostics
- **[Git Dataflow Analysis](Git-Dataflow-Analysis)** - Extract data patterns from git history
- **[Data Lineage Extraction](Data-Lineage-Extraction)** - Table and column-level lineage

### Advanced Usage
- **[Dashboard Guide](Dashboard-Guide)** - Interactive visualization and exploration
- **[Agent System](Agent-System)** - Understanding AI agents and orchestration
- **[Custom Agents](Custom-Agents)** - Build your own analysis agents
- **[API Reference](API-Reference)** - Complete API documentation

### Help & Support
- **[Troubleshooting](Troubleshooting)** - Common issues and solutions
- **[FAQ](FAQ)** - Frequently asked questions
- **[Examples](Examples)** - Real-world use cases
- **[Contributing](Contributing)** - How to contribute to Kratos

---

## [TARGET] What is Kratos?

Kratos is a comprehensive **data engineering analysis platform** that helps you understand and troubleshoot your data pipelines without needing to be an expert. It provides three main capabilities:

### 1. [CHART] Spark Job Analysis
Analyzes Apache Spark event logs to diagnose performance issues, explain query execution, and identify root causes of failures.

**Example Questions:**
- "Why is my Spark job running slow?"
- "What is this query actually doing?"
- "Why did my job fail?"
- "Where is the bottleneck in my data pipeline?"

### 2. [SYNC] Git Repository Dataflow Analysis
Extracts data flow patterns from your git repository's commit history to understand how data moves through your codebase.

**What It Identifies:**
- Data sources (reads from tables, files, APIs)
- Data sinks (writes to tables, files, APIs)
- Joins and transformations
- Process flows and data domains

### 3. [LINK] Data Lineage Extraction
Analyzes ETL scripts to extract table and column-level data lineage, helping you understand data dependencies.

**Capabilities:**
- Table-level dependencies
- Column-level lineage
- Upstream/downstream tracing
- Impact analysis

---

## [LAUNCH] Quick Start

### Step 1: Install
```bash
pip install -r requirements.txt
```

### Step 2: Set Up API Key
Create a `.env` file with your OpenAI API key:
```
OPENAI_API_KEY=your-api-key-here
```

### Step 3: Run Your First Analysis

**Analyze a Spark Job:**
```bash
python -m src.cli orchestrate --from-log your_event_log.json --query "Why is my Spark job slow?"
```

**Extract Git Dataflow:**
```bash
python -m src.cli git-clone https://github.com/your-org/your-repo.git --dest your-repo
python -m src.cli git-log ./runs/cloned_repos/your-repo
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm
```

**Extract Data Lineage:**
```bash
python -m src.cli lineage-extract --folder ./path/to/etl/scripts
```

---

## [GUIDE] Key Concepts

### The Fingerprint System
Kratos generates a **three-layer fingerprint** from Spark event logs:

1. **Semantic Layer** - WHAT ran (query structure, data flow)
2. **Context Layer** - HOW it ran (Spark config, cluster setup)
3. **Metrics Layer** - HOW WELL it ran (performance, failures, anomalies)

### AI Agent System
Kratos uses specialized AI agents to analyze fingerprints:

- **Query Understanding Agent** - Explains what queries do in plain English
- **Root Cause Agent** - Diagnoses performance issues and failures
- **Git Dataflow Agent** - Identifies data patterns from code changes
- **Lineage Extraction Agent** - Traces table and column dependencies

### Smart Orchestrator
Automatically routes user questions to the right agents and synthesizes results.

---

##  Interactive Dashboard

Kratos includes a **React-based dashboard** for visual exploration:

- Browse analysis run history
- View root cause analysis findings
- Explore interactive lineage graphs
- Visualize git dataflow patterns

**Start the dashboard:**
```bash
cd dashboard/
npm install
npm run build
npm run server
```

Visit **http://localhost:4173** in your browser.

---

## [CHART] Sample Output

```
═══════════════════════════════════════════════════════════════════════
  ANALYSIS RESULT [PERFORMANCE]
═══════════════════════════════════════════════════════════════════════

  Query: Why is my Spark job slow?
  Problem Type: performance
  Confidence: 85%

───────────────────────────────────────────────────────────────────────
  EXECUTIVE SUMMARY
───────────────────────────────────────────────────────────────────────

  The job is experiencing memory pressure causing 8GB of data to spill
  to disk. This is the primary cause of slow performance. Additionally,
  6 tasks failed and required retries.

───────────────────────────────────────────────────────────────────────
  RECOMMENDATIONS
───────────────────────────────────────────────────────────────────────

  1. Increase executor memory from 1GB to 2GB
  2. Review data partitioning strategy
  3. Consider using broadcast joins for small tables
```

---

## [TOOLS] Use Cases

### Performance Troubleshooting
- Identify memory pressure and spill
- Detect data skew
- Find slow stages and bottlenecks
- Diagnose shuffle overhead

### Query Understanding
- Explain complex Spark queries
- Document data transformations
- Understand job logic

### Data Governance
- Track table and column lineage
- Impact analysis for schema changes
- Compliance and auditing

### Code Analysis
- Extract dataflow from git history
- Understand data pipeline evolution
- Document data sources and sinks

---

## [DOCS] Documentation Structure

This wiki is organized into the following sections:

###  Getting Started
Introduction, installation, and first steps with Kratos.

###  User Guides
Step-by-step guides for each major feature.

###  Advanced Topics
In-depth coverage of advanced features and customization.

###  Reference
Complete API documentation and technical specifications.

###  Help & Support
Troubleshooting, FAQ, and community resources.

---

##  Community & Support

- **Issues**: [GitHub Issues](https://github.com/sumitasthana/kratos-agents/issues)
- **Discussions**: [GitHub Discussions](https://github.com/sumitasthana/kratos-agents/discussions)
- **Contributing**: See [Contributing Guide](Contributing)

---

##  License

Kratos is open source software licensed under the MIT License.

---

## [LINK] External Resources

- [Apache Spark Documentation](https://spark.apache.org/docs/latest/)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Data Lineage Best Practices](https://en.wikipedia.org/wiki/Data_lineage)

---

**Last Updated**: February 2026  
**Version**: 3.0.0  
**Status**: [PASS] Production Ready
