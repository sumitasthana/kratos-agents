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
# Ask a question about your Spark job
python demo_agentic.py "Why is my Spark job slow?"

# Or use your own event log
python demo_agentic.py --from-log your_event_log.json "What went wrong?"
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
python demo_agentic.py "Why is my job failing?"
python demo_agentic.py "Explain what this query does"
python demo_agentic.py "What are the performance bottlenecks?"
```

### 2. Individual Agents

Run specific agents directly for targeted analysis:

```bash
# Just explain the query
python demo.py --agent query

# Just analyze performance issues  
python demo.py --agent root-cause

# Run both
python demo.py --from-log data/event_logs_rca.json
```

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
├── demo_agentic.py          # 🚀 Main entry point - ask questions here
├── demo.py                  # Run individual agents
├── src/
│   ├── orchestrator.py      # Smart agent coordination
│   ├── agent_coordination.py # Agent communication system
│   ├── fingerprint.py       # Fingerprint generation
│   ├── parser.py            # Event log parsing
│   └── agents/
│       ├── query_understanding.py  # Explains queries
│       └── root_cause.py           # Finds problems
├── data/
│   └── event_logs_rca.json  # Sample event log for testing
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
