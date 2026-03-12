# Frequently Asked Questions (FAQ)

Quick answers to common questions about Kratos.

---

## General Questions

### What is Kratos?

Kratos is an AI-powered data engineering analysis platform that helps you:
- Understand and troubleshoot Apache Spark jobs
- Extract dataflow patterns from git repositories
- Trace table and column-level data lineage from ETL scripts

All analysis is explained in plain English, so you don't need to be an expert.

---

### Do I need to be a Spark expert to use Kratos?

**No!** That's the whole point. Kratos explains everything in plain English. You can ask questions like "Why is my job slow?" and get actionable answers without needing to understand Spark internals.

---

### What can Kratos analyze?

Kratos can analyze three types of data engineering artifacts:

1. **Spark Event Logs** - For performance troubleshooting and query understanding
2. **Git Repositories** - For extracting dataflow patterns from code changes
3. **ETL Scripts** - For extracting table and column-level data lineage

---

### Is Kratos free?

Kratos is **open source** (MIT License) and free to use. However, it uses OpenAI's API for AI-powered analysis, which has usage costs:
- Typical cost: **$0.05 - $0.25 per analysis**
- Costs vary based on model and complexity
- You only pay for what you use

---

### What are the system requirements?

- **Python**: 3.10 or higher
- **RAM**: 4GB minimum, 8GB+ recommended
- **Disk**: 500MB for software, plus space for event logs and results
- **OS**: Linux, macOS, or Windows
- **Network**: Internet connection for OpenAI API
- **Optional**: Node.js 16+ for dashboard

---

## Spark Analysis Questions

### Where do I get Spark event log files?

Spark automatically generates event logs when enabled. Check:

1. **Spark History Server**: Usually http://localhost:18080
2. **Configuration**: `spark.eventLog.dir` setting
3. **Default location**: Often `/tmp/spark-events/`

To enable event logging:
```python
spark = SparkSession.builder \
    .config("spark.eventLog.enabled", "true") \
    .config("spark.eventLog.dir", "/path/to/logs") \
    .getOrCreate()
```

---

### Does Kratos work with Databricks/EMR/Dataproc?

**Yes!** As long as you can export the event log JSON files:

- **Databricks**: Download from Spark UI → "Event Log" tab
- **AWS EMR**: Access via S3 bucket configured for event logs
- **Google Dataproc**: Access via GCS bucket
- **On-prem**: Spark History Server

Kratos analyzes the event log file, not the cluster directly.

---

### Can I analyze running jobs?

**No**, Kratos needs complete event logs. You must wait for the job to finish (or fail) before analysis.

However, you can analyze partial logs if the file is being written incrementally, though results may be incomplete.

---

### How long does analysis take?

- **Fingerprint generation**: 5-30 seconds (depends on log size)
- **AI analysis**: 10-60 seconds (depends on complexity and model)
- **Total**: Usually under 2 minutes per analysis

Large event logs (>100MB) may take longer.

---

### What Spark versions are supported?

Kratos supports:
- **Spark 2.4.x** and higher
- **Spark 3.x** (all versions)

Event log format is relatively stable across versions.

---

## AI and API Questions

### Which AI models can I use?

Kratos supports OpenAI models:
- **gpt-4o** (default) - Best quality, higher cost
- **gpt-4o-mini** - Good quality, lower cost
- **gpt-3.5-turbo** - Fastest, lowest cost

Configure via environment variable:
```bash
export OPENAI_MODEL="gpt-3.5-turbo"
```

---

### How much do API calls cost?

Approximate costs per analysis:
- **gpt-4o**: $0.15 - $0.25
- **gpt-4o-mini**: $0.05 - $0.10
- **gpt-3.5-turbo**: $0.02 - $0.05

Costs vary based on:
- Event log complexity
- Detail level (minimal vs. detailed)
- Question complexity
- Model chosen

---

### Can I use local LLMs instead of OpenAI?

Currently, Kratos is designed for OpenAI's API. Support for local models (Ollama, LM Studio) is on the roadmap but not yet implemented.

You could extend the codebase to add custom LLM backends by implementing the agent interface.

---

### Are my logs and data sent to OpenAI?

**Yes**, fingerprint data is sent to OpenAI for analysis. This includes:
- Query structure and execution plans
- Performance metrics
- Configuration settings

**Not sent:**
- Your actual data (table contents)
- Full event logs (only fingerprints)

Review OpenAI's data usage policy: https://platform.openai.com/docs/data-usage-policy

If data privacy is critical, consider:
- Running on anonymized/test data
- Implementing local LLM support
- Using fingerprints only (without AI analysis)

---

## Git Dataflow Questions

### What repositories can I analyze?

Any git repository containing code, especially:
- Data pipeline code (Python, SQL, Scala)
- ETL scripts
- Data processing applications

Works best with:
- Commits that modify data processing code
- Clear file structure
- Meaningful commit messages

---

### How far back does git analysis go?

By default, Kratos analyzes the full commit history. For large repositories, you can limit:

```bash
# Analyze last 100 commits only
python -m src.cli git-log ./repo --max-commits 100

# Or clone with limited depth
git clone --depth 50 https://github.com/owner/repo.git
```

---

### Can I analyze private repositories?

**Yes**, but you need authentication:

```bash
# SSH (recommended)
python -m src.cli git-clone git@github.com:owner/private-repo.git

# HTTPS with token
python -m src.cli git-clone https://username:token@github.com/owner/private-repo.git
```

Generate tokens at: https://github.com/settings/tokens

---

## Data Lineage Questions

### What file formats are supported for lineage extraction?

Kratos supports:
- **Python** (.py) - PySpark, pandas code
- **SQL** (.sql) - SQL scripts with table operations

Best results with:
- Explicit table names (not dynamic strings)
- Clear column references
- Standard SQL or PySpark syntax

---

### Can lineage trace dynamic table names?

**Limited support**. Kratos works best with static table names:

```python
# [PASS] Good - static names
df = spark.read.table("customers")

# [FAIL] Harder - dynamic names
table_name = f"customers_{env}"
df = spark.read.table(table_name)
```

For dynamic names, AI attempts to infer but may miss some dependencies.

---

### Does lineage work with dbt?

**Not directly**, but you can analyze dbt-compiled SQL files:

```bash
# Compile dbt models
dbt compile

# Analyze compiled SQL
python -m src.cli lineage-extract --folder target/compiled/
```

Native dbt support is planned for future releases.

---

## Dashboard Questions

### Do I need the dashboard?

**No**, the dashboard is optional. You can use Kratos entirely via CLI and view results as JSON or Markdown files.

The dashboard provides:
- Interactive visualization
- Run history browsing
- Graph-based lineage exploration
- Side-by-side comparison

---

### Can I deploy the dashboard to production?

**Yes**, you can deploy it to any web server:

```bash
# Build for production
cd dashboard
npm run build

# Deploy dist/ folder to your server
# Serve with any static file server or cloud platform
```

The dashboard is a static React app + simple Express backend.

---

### Can multiple users access the dashboard?

Yes, but be aware:
- Dashboard reads from local `runs/` directory
- All users see the same analysis results
- No authentication built-in
- Designed for single-user or team use

For multi-user production use, consider:
- Shared network storage for `runs/`
- Add authentication layer
- Deploy to internal network only

---

## Advanced Questions

### Can I build custom agents?

**Yes!** Kratos provides a base agent interface:

```python
from src.agents.base import BaseAgent, AgentResponse

class MyCustomAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "My Custom Agent"
    
    async def analyze(self, fingerprint_data, context=None, **kwargs):
        # Your analysis logic
        return AgentResponse(
            agent_name=self.agent_name,
            summary="Analysis complete",
            explanation="Detailed findings...",
            confidence_score=0.9
        )
```

See **[Custom Agents](Custom-Agents)** guide for details.

---

### Can I automate Kratos in CI/CD pipelines?

**Yes!** Kratos is designed for automation:

```bash
# Example CI/CD script
#!/bin/bash

# Run Spark job and save event log
spark-submit --conf spark.eventLog.enabled=true my_job.py

# Analyze performance
python -m src.cli orchestrate \
  --from-log /path/to/event_log.json \
  --query "Is there a performance regression?" \
  --output results.json

# Parse results and fail build if issues found
if grep -q "CRITICAL" results.json; then
  echo "Performance regression detected!"
  exit 1
fi
```

---

### Can I compare multiple runs?

**Yes**, use fingerprint comparison:

```python
from src.fingerprint import generate_fingerprint

baseline = generate_fingerprint("baseline_log.json")
current = generate_fingerprint("current_log.json")

# Compare
if baseline.semantic.semantic_hash != current.semantic.semantic_hash:
    print("Query changed!")
    
duration_change = (
    (current.metrics.execution_summary.total_duration_ms - 
     baseline.metrics.execution_summary.total_duration_ms) /
    baseline.metrics.execution_summary.total_duration_ms * 100
)

if duration_change > 20:
    print(f"Regression: +{duration_change:.1f}%")
```

---

### How do I export results?

Results are automatically saved to `runs/` directory:

```bash
# Fingerprints
runs/fingerprints/fingerprint_TIMESTAMP.json

# Orchestrator results
runs/orchestrator/orchestrator_TIMESTAMP.json

# Git dataflow
runs/git_dataflow/git_dataflow_TIMESTAMP.json

# Lineage
runs/lineage/lineage_TIMESTAMP.json
```

Also available in markdown format:
```bash
python -m src.cli fingerprint event.json --format markdown
```

---

## Troubleshooting Questions

### Why is my analysis failing?

Common causes:
1. **Invalid event log** - Ensure it's valid JSON
2. **Missing API key** - Check `.env` file
3. **Network issues** - Verify internet connection
4. **Corrupted logs** - Try re-exporting from Spark

See **[Troubleshooting](Troubleshooting)** for detailed solutions.

---

### How do I reduce API costs?

1. Use cheaper model: `export OPENAI_MODEL="gpt-3.5-turbo"`
2. Use minimal detail: `--level minimal`
3. Cache fingerprints: Generate once, reuse for multiple questions
4. Disable evidence: `--no-evidence`

---

### Can I run Kratos offline?

**No**, internet connection is required for OpenAI API calls. However, you can:
- Generate fingerprints offline (no API needed)
- View previously generated results offline
- Use the dashboard offline (if data already exists)

Only AI analysis requires internet.

---

## Contributing Questions

### How can I contribute?

We welcome contributions! See **[Contributing Guide](Contributing)** for:
- Code contributions
- Bug reports
- Documentation improvements
- Feature requests
- Custom agents

---

### What features are planned?

Roadmap includes:
- Local LLM support (Ollama, LM Studio)
- Native dbt integration
- Real-time monitoring capabilities
- More built-in agents
- Enhanced lineage visualization
- Streaming event log analysis

---

## Still Have Questions?

- **[Troubleshooting](Troubleshooting)** - Common issues and solutions
- **[GitHub Issues](https://github.com/sumitasthana/kratos-agents/issues)** - Ask questions or report bugs
- **[Examples](Examples)** - See working examples
- **[API Reference](API-Reference)** - Complete API documentation

---

**Last Updated**: February 2026  
**Questions Answered**: 40+
