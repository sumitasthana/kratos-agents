# Spark Fingerprint Analyzer

## Overview
AI-powered tool for understanding and troubleshooting Apache Spark jobs. It analyzes Spark event logs to provide insights about query structure, performance bottlenecks, and recommendations.

## Project Structure
```
├── src/                    # Main source code
│   ├── cli.py             # Command-line interface
│   ├── fingerprint.py     # Fingerprint generation
│   ├── parser.py          # Event log parsing
│   ├── orchestrator.py    # Smart agent coordination
│   ├── agents/            # Analysis agents
│   │   ├── query_understanding.py
│   │   └── root_cause.py
│   └── schemas.py         # Data schemas
├── data/                  # Sample data files
│   ├── event_logs.json    # Sample Spark event log
│   └── event_logs_rca.json
├── tests/                 # Test suite
├── requirements.txt       # Python dependencies
└── pyproject.toml         # Project configuration
```

## Usage

### Generate Fingerprint
```bash
python -m src.cli fingerprint data/event_logs.json
```

### Extract Git Log
```bash
python -m src.cli git-log <repo_path>
```

### Analyze Git Dataflow
```bash
python -m src.cli git-dataflow --latest --dir .
```

## Requirements
- Python 3.12
- OpenAI API key (for AI analysis features)

## Environment Variables
- `OPENAI_API_KEY` - Required for AI-powered analysis features

## Recent Changes
- Initial setup in Replit environment (2026-01-25)
