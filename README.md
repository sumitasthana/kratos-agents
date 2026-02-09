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

---

## How It Works

### Workflow 1: Spark Job Analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR SPARK JOB                              │
│                              ↓                                      │
│                      Event Log File                                 │
│                    (auto-generated)                                 │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    FINGERPRINT GENERATOR                            │
│  Creates a structured summary with three layers:                    │
│                                                                     │
│  📊 WHAT ran        → Query structure, data flow, transformations   │
│  ⚙️  HOW it ran      → Spark version, memory settings, cluster size │
│  📈 HOW WELL it ran → Task times, failures, memory usage, anomalies │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      AI ANALYSIS AGENTS                             │
│                                                                     │
│  🔍 Query Agent     → "This query joins sales data with customers   │
│                        and aggregates by region..."                 │
│                                                                     │
│  🔧 Root Cause Agent → "The job is slow because 8GB of data spilled │
│                         to disk. Increase executor memory to fix."  │
└─────────────────────────────────────────────────────────────────────┘
```

### Workflow 2: Git Repository Dataflow Analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                      YOUR GIT REPOSITORY                            │
│                              ↓                                      │
│                    Commit History + Diffs                           │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    GIT LOG EXTRACTOR                                │
│  Extracts code changes and analyzes patterns                        │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  GIT DATAFLOW AGENT                                 │
│                                                                     │
│  Identifies:                                                        │
│  • Data sources (reads from tables, files, APIs)                    │
│  • Data sinks (writes to tables, files, APIs)                       │
│  • Joins and transformations                                        │
│  • Process flows and data domains                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Workflow 3: Data Lineage Extraction

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ETL SCRIPTS (.py, .sql)                        │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  LINEAGE EXTRACTION AGENT                           │
│                                                                     │
│  Analyzes scripts to extract:                                       │
│  • Table-level dependencies                                         │
│  • Column-level lineage                                             │
│  • Transformation logic                                             │
│  • Upstream/downstream flows                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### All Results →

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ACTIONABLE INSIGHTS                             │
│                                                                     │
│  ✅ Plain English explanations                                      │
│  ✅ Root cause identification                                       │
│  ✅ Specific recommendations                                        │
│  ✅ Prioritized action items                                        │
│  ✅ Interactive dashboard visualization                             │
└─────────────────────────────────────────────────────────────────────┘
```

💡 **Tip**: Use the **Dashboard** (see below) to interactively explore results with graphs and visualizations!

---

## Dashboard - Visual Explorer for Results

The **Dashboard** is a local web UI that lets you visualize and explore agent outputs interactively. It provides:

- **Run History**: Browse all past analyses with timestamps and highlights
- **RCA Findings**: View root cause analysis results with confidence scores and recommendations
- **Lineage Graphs**: Interactive table and column-level lineage visualization
- **Git Dataflow**: Graph visualization showing code dataflow patterns from git history

### Quick Start

```bash
# Navigate to dashboard folder
cd dashboard/

# Install dependencies (first time only)
npm install

# Build the dashboard
npm run build

# Start the server
npm run server
```

Then visit **http://localhost:4173** in your browser.

The dashboard automatically:
- Shows your latest analysis run
- Selects the appropriate visualization tab based on the command type (RCA, Git Dataflow, or Lineage)
- Lets you browse and compare historical runs

### Development Mode

```bash
cd dashboard/
npm run dev  # Runs on port 5173 with hot reload
```

---

## Core Capabilities

Kratos provides three main analysis capabilities, each designed for different data engineering tasks:

### 1. 🔍 Spark Job Analysis

Analyze Apache Spark event logs to understand performance, diagnose issues, and explain query execution.

**Smart Orchestrator (Recommended):**
```bash
# Ask questions in plain English - automatically routes to the right agents
python -m src.cli orchestrate --from-log your_event_log.json --query "Why is my job failing?"
python -m src.cli orchestrate --from-log your_event_log.json --query "Explain what this query does"
python -m src.cli orchestrate --from-log your_event_log.json --query "What are the performance bottlenecks?"
```

**Direct Fingerprint Generation:**
```bash
# Generate a fingerprint only (for advanced use cases)
python -m src.cli fingerprint your_event_log.json
```

### 2. 🔄 Git Repository Dataflow Analysis

Extract dataflow patterns (reads, writes, joins, transformations) from git repository commit history.

```bash
# Clone a repository
python -m src.cli git-clone https://github.com/Byte-Farmer/kratos-v1.git --dest kratos-v1

# Extract git artifacts (commits + diffs)
python -m src.cli git-log ./runs/cloned_repos/kratos-v1

# Analyze dataflow patterns with AI
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm

# Optional: include documentation files (README.md, etc.) in analysis
python -m src.cli git-dataflow --latest --dir ./runs/git_artifacts --llm --include-docs
```

### 3. 🔗 Data Lineage Extraction

Extract table and column-level data lineage from Spark ETL scripts using AI.

```bash
# Extract lineage from a single script
python -m src.cli lineage-extract --scripts etl_pipeline.py

# Extract lineage from ALL scripts in a folder
python -m src.cli lineage-extract --folder ./scripts/multi

# Trace column dependencies (upstream or downstream)
python -m src.cli lineage-extract --folder ./scripts/multi \
  --trace-table customers \
  --trace-column customer_id \
  --trace-direction upstream
```

**Output:** Lineage artifacts are saved to `runs/lineage/lineage_*.json`

**Note:** During `orchestrate`, `git-dataflow`, and `lineage-extract` commands, the tool prints each agent's planned steps to the console before execution.

---

## What Can Kratos Help You With?

### Spark Job Issues

| Problem | What You'll See | What It Means |
|---------|-----------------|---------------|
| **Memory Pressure** | "8GB spilled to disk" | Not enough memory for your data |
| **Data Skew** | "Partition 32x larger than median" | Uneven data distribution causing slow tasks |
| **Task Failures** | "23 tasks failed, 45 retries" | Something crashed during execution |
| **Shuffle Overhead** | "7.4GB shuffle volume" | Too much data moving between machines |
| **Slow Stages** | "Stage 4 took 15 minutes" | Bottleneck in your pipeline |

### Git Dataflow Insights

| Analysis | What It Identifies | Use Case |
|----------|-------------------|----------|
| **Data Sources** | Tables, files, APIs being read | Understand data dependencies |
| **Data Sinks** | Where data is written | Track data outputs |
| **Transformations** | Joins, filters, aggregations | Document business logic |
| **Process Flows** | Complete data pipeline flow | Architecture documentation |

### Data Lineage Capabilities

| Feature | What It Provides | Use Case |
|---------|-----------------|----------|
| **Table Dependencies** | Which tables depend on others | Impact analysis for changes |
| **Column Lineage** | Column-level data flow | Compliance and data governance |
| **Upstream Tracing** | Where data originates | Root cause analysis |
| **Downstream Tracing** | What depends on this data | Change impact assessment |

---

## Sample Output

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

## Project Structure

```
├── src/
│   ├── orchestrator.py      # Smart agent coordination
│   ├── agent_coordination.py # Agent communication system
│   ├── fingerprint.py       # Fingerprint generation
│   ├── parser.py            # Event log parsing
│   └── agents/
│       ├── query_understanding.py  # Explains queries
│       ├── root_cause.py           # Finds problems
│       ├── git_diff_dataflow.py    # Git diff dataflow analysis
│       └── lineage_extraction.py   # ETL script lineage extraction
├── dashboard/               # React-based web UI for visualizing results
│   ├── src/                 # React components (App.tsx, graphs, etc.)
│   ├── server.js            # Express backend serving artifacts
│   ├── package.json         # Node.js dependencies
│   └── dist/                # Built UI (generated via npm run build)
├── runs/                    # Generated outputs (ignored by git)
│   ├── spark_event_logs/    # Example/sample Spark event logs
│   ├── fingerprints/        # fingerprint_*.json
│   ├── orchestrator/        # orchestrator_*.json
│   ├── run_manifests/       # Metadata for each run (used by dashboard)
│   ├── cloned_repos/        # Local clones for git-log extraction
│   ├── git_artifacts/       # git_artifacts_*.json (from git-log)
│   ├── git_dataflow/        # git_dataflow_*.json (from git-dataflow)
│   └── lineage/             # lineage_*.json (from lineage-extract)
├── scripts/                 # Place ETL scripts you want lineage-extract to analyze
│   └── multi/               # Example multi-script folder (analyze via: lineage-extract --folder ./scripts/multi)
└── requirements.txt         # Python dependencies
```

---

## For Developers

### Architecture Overview

The system uses a **two-layer architecture**:

**Layer 1 - Infrastructure** (unchanged, stable):
- Event log parsing and indexing
- Three-layer fingerprint generation (Semantic, Context, Metrics)
- Individual analysis agents

**Layer 2 - Orchestration** (new, intelligent):
- Problem classification based on user query
- Agent selection and sequencing
- Context sharing between agents
- Result synthesis

### Extending with Custom Agents

```python
from src.agents.base import BaseAgent, AgentResponse

class MyCustomAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "My Custom Agent"
    
    async def analyze(self, fingerprint_data, context=None, **kwargs):
        # Your analysis logic here
        return AgentResponse(...)
```

### API Usage

```python
from src.fingerprint import generate_fingerprint
from src.orchestrator import SmartOrchestrator

# Generate fingerprint
fingerprint = generate_fingerprint("path/to/event_log.json")

# Create orchestrator and ask questions
orchestrator = SmartOrchestrator(fingerprint)
result = await orchestrator.solve_problem("Why is my job slow?")

print(result.executive_summary)
print(result.recommendations)
```

---

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

---

## Support

Having issues? Check the [troubleshooting guide](QUICKSTART.md#troubleshooting) or open an issue on GitHub.
