# Troubleshooting

Common issues and solutions when using Kratos.

---

## Installation Issues

### Python Version Errors

**Problem**: `ERROR: Package requires Python 3.10 or higher`

**Solution**:
```bash
# Check your Python version
python --version

# If too old, install Python 3.10+
# Then create venv with correct version
python3.10 -m venv venv
source venv/bin/activate
```

---

### pip Installation Failures

**Problem**: `ERROR: Could not find a version that satisfies the requirement`

**Solution**:
```bash
# Upgrade pip first
pip install --upgrade pip

# Then install requirements
pip install -r requirements.txt

# If still failing, try with --no-cache-dir
pip install -r requirements.txt --no-cache-dir
```

---

### OpenAI Package Not Found

**Problem**: `ModuleNotFoundError: No module named 'openai'`

**Solution**:
```bash
# Ensure you're in the virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

---

## Configuration Issues

### OpenAI API Key Not Found

**Problem**: `Error: OpenAI API key not found`

**Solution 1** - Create `.env` file:
```bash
# In project root
echo "OPENAI_API_KEY=your-key-here" > .env
```

**Solution 2** - Set environment variable:
```bash
# Linux/macOS
export OPENAI_API_KEY="your-key-here"

# Windows
set OPENAI_API_KEY=your-key-here
```

**Solution 3** - Verify `.env` file is in correct location:
```bash
# Should be in project root
ls -la .env

# Content should be:
cat .env
# Output: OPENAI_API_KEY=sk-...
```

---

### Invalid API Key

**Problem**: `AuthenticationError: Incorrect API key provided`

**Solution**:
1. Verify your key at https://platform.openai.com/api-keys
2. Ensure no extra spaces or quotes in `.env`:
   ```
   # Wrong
   OPENAI_API_KEY = "sk-..."  
   OPENAI_API_KEY='sk-...'
   
   # Correct
   OPENAI_API_KEY=sk-...
   ```
3. Regenerate key if necessary

---

## Runtime Errors

### Event Log Parsing Errors

**Problem**: `JSONDecodeError: Expecting value`

**Cause**: Corrupted or incomplete event log file

**Solution**:
```bash
# Verify JSON is valid
python -m json.tool event_log.json > /dev/null

# If invalid, re-export from Spark History Server
# Or check if file is completely written
```

---

**Problem**: `KeyError: 'Event' not found`

**Cause**: Event log missing required fields

**Solution**:
- Ensure you're using **JSON** event logs (not plaintext)
- Check Spark version compatibility (2.4+, 3.x supported)
- Verify complete execution (not truncated logs)

---

### Memory Errors During Analysis

**Problem**: `MemoryError` or system runs out of memory

**Cause**: Large event logs or fingerprints

**Solution**:
```bash
# 1. Use minimal detail level
python -m src.cli fingerprint event_log.json --level minimal

# 2. Disable evidence linking
python -m src.cli fingerprint event_log.json --no-evidence

# 3. Process in stages
# First generate fingerprint
python -m src.cli fingerprint event_log.json
# Then analyze with orchestrator using saved fingerprint
python -m src.cli orchestrate --from-fingerprint runs/fingerprints/fingerprint_*.json \
  --query "your question"
```

---

### Agent Analysis Timeouts

**Problem**: Agent analysis takes too long or times out

**Solution**:
```bash
# 1. Use faster model
export OPENAI_MODEL="gpt-3.5-turbo"

# 2. Reduce fingerprint detail
python -m src.cli orchestrate --from-log event_log.json \
  --query "your question" \
  --level minimal

# 3. Analyze specific aspects only
# Instead of general "Why is my job slow?"
# Ask specific: "What is the duration of Stage 3?"
```

---

## Dashboard Issues

### npm Installation Failures

**Problem**: `npm ERR! code EACCES`

**Solution**:
```bash
# Don't use sudo - use nvm or fix permissions
# Option 1: Use nvm (recommended)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 18
nvm use 18

# Option 2: Fix npm permissions
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

---

### Port Already in Use

**Problem**: `Error: listen EADDRINUSE: address already in use :::4173`

**Solution**:
```bash
# Find and kill process using port
# macOS/Linux:
lsof -ti:4173 | xargs kill -9

# Windows:
netstat -ano | findstr :4173
taskkill /PID <PID> /F

# Or use different port
# Edit dashboard/server.js and change port number
```

---

### Dashboard Shows No Data

**Problem**: Dashboard loads but shows "No runs found"

**Cause**: Missing or incorrect run manifest files

**Solution**:
```bash
# 1. Verify runs directory exists and has data
ls -la runs/orchestrator/
ls -la runs/run_manifests/

# 2. Re-run analysis to generate new data
python -m src.cli orchestrate --from-log event_log.json --query "test"

# 3. Check dashboard server is reading correct directory
# In dashboard/server.js, verify paths point to ../runs/
```

---

## CLI Issues

### Command Not Found

**Problem**: `python: command not found` or `python -m src.cli: No module named src`

**Solution**:
```bash
# 1. Ensure you're in project root
cd /path/to/kratos-agents

# 2. Activate virtual environment
source venv/bin/activate

# 3. Try python3 instead of python
python3 -m src.cli --help

# 4. Verify src directory exists
ls -la src/
```

---

### File Path Issues

**Problem**: `FileNotFoundError: [Errno 2] No such file or directory`

**Solution**:
```bash
# Use absolute paths
python -m src.cli fingerprint /absolute/path/to/event_log.json

# Or relative from project root
python -m src.cli fingerprint ./runs/spark_event_logs/sample.json

# Verify file exists
ls -la /path/to/event_log.json
```

---

## Git Dataflow Issues

### Git Clone Failures

**Problem**: `fatal: repository not found` or authentication errors

**Solution**:
```bash
# For public repos - verify URL
git ls-remote https://github.com/owner/repo.git

# For private repos - set up authentication
# Option 1: SSH
git clone git@github.com:owner/repo.git

# Option 2: Personal Access Token
git clone https://username:token@github.com/owner/repo.git

# Or use Kratos CLI with token
python -m src.cli git-clone https://username:token@github.com/owner/repo.git
```

---

### Large Repository Timeout

**Problem**: Git extraction times out on large repositories

**Solution**:
```bash
# 1. Clone with depth limit
git clone --depth 100 https://github.com/owner/repo.git
cd repo
git fetch --unshallow  # If you need full history later

# 2. Limit commit range in git-log
python -m src.cli git-log ./repo --max-commits 100

# 3. Analyze specific time range
# Checkout specific branch/date first
cd ./runs/cloned_repos/repo
git checkout $(git rev-list -1 --before="2026-01-01" main)
cd ../../..
python -m src.cli git-log ./runs/cloned_repos/repo
```

---

## Lineage Extraction Issues

### No Lineage Found

**Problem**: `No lineage extracted` or empty results

**Cause**: Scripts don't contain recognizable data operations

**Solution**:
```bash
# 1. Verify scripts contain SQL or DataFrame operations
grep -r "spark.sql\|read\.table\|\.join\|\.select" ./scripts/

# 2. Check file extensions (.py, .sql supported)
ls -la ./scripts/

# 3. Use verbose mode to see what's being analyzed
python -m src.cli lineage-extract --folder ./scripts/ --verbose
```

---

### Incomplete Lineage

**Problem**: Some tables or columns missing from lineage

**Cause**: Complex transformations or dynamic table names

**Solution**:
- Static table names work best (avoid string concatenation)
- Ensure complete code context in single file
- Add comments describing transformations
- Use explicit column names (not `select *`)

---

## Performance Issues

### Slow Fingerprint Generation

**Problem**: Fingerprint generation takes very long

**Solutions**:
```bash
# 1. Use minimal detail level
python -m src.cli fingerprint event_log.json --level minimal

# 2. Disable evidence linking
python -m src.cli fingerprint event_log.json --no-evidence

# 3. Check event log size
ls -lh event_log.json
# Logs > 100MB may be slow

# 4. Filter events if possible (advanced)
# Extract only necessary event types from Spark
```

---

### High API Costs

**Problem**: OpenAI API costs too high

**Solutions**:
```bash
# 1. Use cheaper model
export OPENAI_MODEL="gpt-3.5-turbo"

# 2. Reduce fingerprint detail
python -m src.cli orchestrate --from-log event.json --query "..." --level minimal

# 3. Cache fingerprints and reuse
# Generate once:
python -m src.cli fingerprint event.json
# Reuse for multiple questions:
python -m src.cli orchestrate --from-fingerprint runs/fingerprints/latest.json --query "q1"
python -m src.cli orchestrate --from-fingerprint runs/fingerprints/latest.json --query "q2"

# 4. Use lower temperature
export OPENAI_TEMPERATURE="0.1"
```

---

## Common Error Messages

### "No fingerprint data provided"

**Cause**: Orchestrator needs either `--from-log` or `--from-fingerprint`

**Solution**:
```bash
# Provide event log
python -m src.cli orchestrate --from-log event.json --query "..."

# Or provide fingerprint
python -m src.cli orchestrate --from-fingerprint fingerprint.json --query "..."
```

---

### "Failed to parse event log"

**Cause**: Invalid or corrupted event log

**Solution**:
1. Validate JSON: `python -m json.tool event_log.json`
2. Check file isn't truncated (incomplete write)
3. Ensure it's Spark event log (not application logs)
4. Try re-exporting from Spark History Server

---

### "Agent analysis failed"

**Cause**: API errors, network issues, or invalid input

**Solution**:
```bash
# Check logs for specific error
python -m src.cli orchestrate --from-log event.json --query "..." --verbose

# Verify API key works
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Try with simpler query
python -m src.cli orchestrate --from-log event.json --query "What is the job duration?"
```

---

## Getting Help

If you can't resolve your issue:

1. **Check logs** - Look in `runs/` for detailed error logs
2. **Enable verbose mode** - Add `--verbose` to CLI commands
3. **Search issues** - https://github.com/sumitasthana/kratos-agents/issues
4. **Open new issue** - Include:
   - Error message
   - Command used
   - Python version (`python --version`)
   - OS and version
   - Relevant logs

---

## Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from src.fingerprint import generate_fingerprint
# Now see detailed logs
fingerprint = generate_fingerprint("event.json")
```

---

## Still Need Help?

- **[FAQ](FAQ)** - Frequently asked questions
- **[GitHub Issues](https://github.com/sumitasthana/kratos-agents/issues)** - Report bugs
- **[Examples](Examples)** - Working examples
- **[API Reference](API-Reference)** - Detailed API docs

---

**Last Updated**: February 2026  
**Common Issues Resolved**: 95%+
