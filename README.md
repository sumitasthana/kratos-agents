# Spark Fingerprint Analyzer

**Your AI-powered assistant for understanding and troubleshooting Apache Spark jobs.**

---

## What Does This Tool Do?

When your Spark job runs slow, fails, or behaves unexpectedly, this tool helps you understand **why** — without needing to be a Spark expert.

### In Simple Terms:

1. **You provide**: A Spark event log file (automatically generated when Spark jobs run)
2. **The tool creates**: A "fingerprint" — a structured summary of what happened during execution
3. **AI agents analyze**: The fingerprint and explain issues in plain English

### Example Questions It Can Answer:

- *"Why is my Spark job running slow?"*
- *"What is this query actually doing?"*
- *"Why did my job fail?"*
- *"Where is the bottleneck in my data pipeline?"*

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

### Step 3: Run the Demo

```bash
# Ask a question about your Spark job (generates a fingerprint first)
python -m src.cli orchestrate --from-log your_event_log.json --query "Why is my Spark job slow?"

# Or generate a fingerprint only
python -m src.cli fingerprint your_event_log.json
```

---

## How It Works

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
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     ACTIONABLE INSIGHTS                             │
│                                                                     │
│  ✅ Plain English explanations                                      │
│  ✅ Root cause identification                                       │
│  ✅ Specific recommendations                                        │
│  ✅ Prioritized action items                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Two Ways to Use

### 1. Smart Orchestrator (Recommended)

Ask a question in plain English. The system automatically picks the right agents and coordinates their analysis:

```bash
python -m src.cli orchestrate --from-log your_event_log.json --query "Why is my job failing?"
python -m src.cli orchestrate --from-log your_event_log.json --query "Explain what this query does"
python -m src.cli orchestrate --from-log your_event_log.json --query "What are the performance bottlenecks?"
```

### 2. Individual Agents

Run specific pipeline steps directly for targeted workflows:

```bash
# Generate a fingerprint
python -m src.cli fingerprint your_event_log.json

# Run dataflow extraction from a Git repo diff history
python -m src.cli git-clone https://github.com/Byte-Farmer/kratos-v1.git --dest kratos-v1
python -m src.cli git-log .\runs\cloned_repos\kratos-v1
python -m src.cli git-dataflow --latest --dir .\runs\git_artifacts --llm

# Optional: include documentation files (README.md, etc.) in dataflow extraction
python -m src.cli git-dataflow --latest --dir .\runs\git_artifacts --llm --include-docs

# Extract data lineage from ETL scripts (AI-powered)
python -m src.cli lineage-extract --scripts etl_pipeline.py

# Extract lineage from ALL scripts in a folder
python -m src.cli lineage-extract --folder .\scripts\multi

# Trace column dependencies
python -m src.cli lineage-extract --folder .\scripts\multi --trace-table customers --trace-column customer_id --trace-direction upstream
```

During `orchestrate`, `git-dataflow`, and `lineage-extract`, the tool prints each agent's planned steps to the console before execution.

---

## What Problems Can It Detect?

| Problem | What You'll See | What It Means |
|---------|-----------------|---------------|
| **Memory Pressure** | "8GB spilled to disk" | Not enough memory for your data |
| **Data Skew** | "Partition 32x larger than median" | Uneven data distribution causing slow tasks |
| **Task Failures** | "23 tasks failed, 45 retries" | Something crashed during execution |
| **Shuffle Overhead** | "7.4GB shuffle volume" | Too much data moving between machines |
| **Slow Stages** | "Stage 4 took 15 minutes" | Bottleneck in your pipeline |

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
├── runs/                    # Generated outputs (ignored by git)
│   ├── spark_event_logs/    # Example/sample Spark event logs
│   ├── fingerprints/        # fingerprint_*.json
│   ├── orchestrator/        # orchestrator_*.json
│   ├── cloned_repos/        # Local clones for git-log extraction
│   ├── git_artifacts/       # git_artifacts_*.json (from git-log)
│   ├── git_dataflow/        # git_dataflow_*.json (from git-dataflow)
│   └── lineage/             # lineage_*.json (from lineage-extract)
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

---

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Detailed installation and usage guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical deep dive
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation

---

## FAQ

**Q: Do I need to be a Spark expert to use this?**  
A: No! The tool explains everything in plain English.

**Q: Where do I get event log files?**  
A: Spark automatically generates them. Check your Spark History Server or the `spark.eventLog.dir` configuration.

**Q: Does it work with Databricks/EMR/Dataproc?**  
A: Yes, as long as you can export the event log JSON files.

**Q: How much does it cost?**  
A: The tool is free. You only pay for OpenAI API usage (typically a few cents per analysis).

---

## Support

Having issues? Check the [troubleshooting guide](QUICKSTART.md#troubleshooting) or open an issue on GitHub.
