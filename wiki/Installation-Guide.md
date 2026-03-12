# Installation Guide

This guide will help you set up Kratos on your local machine or server.

---

## Prerequisites

Before installing Kratos, ensure you have:

- **Python 3.10 or higher** ([Download Python](https://www.python.org/downloads/))
- **pip** (Python package installer, comes with Python)
- **OpenAI API key** for AI-powered analysis ([Get API Key](https://platform.openai.com/api-keys))
- **Node.js 16+ and npm** (optional, for dashboard) ([Download Node.js](https://nodejs.org/))
- **Git** for repository cloning ([Download Git](https://git-scm.com/))

---

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/sumitasthana/kratos-agents.git
cd kratos-agents
```

### Step 2: Create a Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate on Linux/macOS
source venv/bin/activate

# Activate on Windows
venv\Scripts\activate
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This will install all required Python packages including:
- `openai` - OpenAI API client
- `pydantic` - Data validation
- `networkx` - Graph operations
- `python-dotenv` - Environment variable management
- And other dependencies

### Step 4: Configure OpenAI API Key

Create a `.env` file in the project root:

```bash
# Create .env file
touch .env
```

Add your OpenAI API key to the `.env` file:

```
OPENAI_API_KEY=your-api-key-here
```

**Alternative:** Set as environment variable:

```bash
# Linux/macOS
export OPENAI_API_KEY="your-api-key-here"

# Windows
set OPENAI_API_KEY=your-api-key-here
```

### Step 5: Verify Installation

Test that everything is installed correctly:

```bash
# Check Python version
python --version

# Verify CLI is working
python -m src.cli --help

# Test fingerprint generation (optional)
python -m src.cli fingerprint --help
```

---

## Installing the Dashboard (Optional)

The dashboard provides an interactive web UI for visualizing results.

### Step 1: Navigate to Dashboard Directory

```bash
cd dashboard
```

### Step 2: Install Node.js Dependencies

```bash
npm install
```

This will install:
- React and React Router
- Recharts for data visualization
- Express for the backend server
- Vite for building

### Step 3: Build the Dashboard

```bash
npm run build
```

This creates optimized production files in the `dist/` directory.

### Step 4: Start the Dashboard Server

```bash
npm run server
```

The dashboard will be available at **http://localhost:4173**

**For Development:**
```bash
npm run dev  # Runs on port 5173 with hot reload
```

---

## Directory Structure After Installation

```
kratos-agents/
├── .env                      # Your API key configuration
├── venv/                     # Python virtual environment
├── src/                      # Source code
│   ├── agents/              # AI analysis agents
│   ├── fingerprint.py       # Fingerprint generator
│   ├── orchestrator.py      # Smart orchestrator
│   └── cli.py               # Command-line interface
├── dashboard/               # Dashboard UI
│   ├── node_modules/        # Node.js dependencies
│   ├── dist/                # Built dashboard files
│   └── server.js            # Express server
├── runs/                    # Output directory (auto-created)
│   ├── fingerprints/        # Generated fingerprints
│   ├── orchestrator/        # Analysis results
│   ├── git_artifacts/       # Git extraction results
│   ├── git_dataflow/        # Dataflow analysis
│   └── lineage/             # Lineage extraction results
├── requirements.txt         # Python dependencies
└── README.md               # Project readme
```

---

## Platform-Specific Installation

### Linux

```bash
# Install Python 3.10+ (Ubuntu/Debian)
sudo apt update
sudo apt install python3.10 python3-pip python3-venv

# Install Node.js (for dashboard)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Clone and install Kratos
git clone https://github.com/sumitasthana/kratos-agents.git
cd kratos-agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### macOS

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.10+
brew install python@3.10

# Install Node.js (for dashboard)
brew install node

# Clone and install Kratos
git clone https://github.com/sumitasthana/kratos-agents.git
cd kratos-agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows

1. **Install Python**:
   - Download from [python.org](https://www.python.org/downloads/)
   - Check "Add Python to PATH" during installation

2. **Install Git**:
   - Download from [git-scm.com](https://git-scm.com/)

3. **Install Node.js** (for dashboard):
   - Download from [nodejs.org](https://nodejs.org/)

4. **Clone and Install**:
   ```cmd
   git clone https://github.com/sumitasthana/kratos-agents.git
   cd kratos-agents
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## Upgrading Kratos

To upgrade to the latest version:

```bash
# Update repository
git pull origin main

# Update Python dependencies
pip install -r requirements.txt --upgrade

# Update dashboard dependencies (if using)
cd dashboard
npm install
npm run build
```

---

## Verifying Your Installation

### 1. Check Python Installation

```bash
python --version
# Should show: Python 3.10.x or higher
```

### 2. Check Installed Packages

```bash
pip list | grep openai
pip list | grep pydantic
```

### 3. Test CLI

```bash
python -m src.cli --help
```

Expected output:
```
Usage: python -m src.cli [OPTIONS] COMMAND [ARGS]...

  Kratos CLI - Data Engineering Analysis Platform

Commands:
  fingerprint      Generate execution fingerprint
  orchestrate      Orchestrate AI agents to answer questions
  git-clone        Clone a git repository
  git-log          Extract git artifacts
  git-dataflow     Analyze git dataflow patterns
  lineage-extract  Extract data lineage from ETL scripts
```

### 4. Test Dashboard (if installed)

```bash
cd dashboard
npm run server
```

Visit http://localhost:4173 - you should see the Kratos dashboard interface.

---

## Troubleshooting Installation

### Python Version Issues

**Problem**: `python: command not found`  
**Solution**: Try `python3` instead, or ensure Python is in your PATH.

**Problem**: Wrong Python version  
**Solution**: Use a specific version:
```bash
python3.10 -m venv venv
```

### pip Installation Issues

**Problem**: `pip: command not found`  
**Solution**: Use `python -m pip` instead:
```bash
python -m pip install -r requirements.txt
```

### OpenAI API Key Issues

**Problem**: `OpenAI API key not found`  
**Solution**: Verify your `.env` file exists and contains:
```
OPENAI_API_KEY=sk-...
```

**Problem**: Invalid API key  
**Solution**: Check your key at https://platform.openai.com/api-keys

### Dashboard Installation Issues

**Problem**: `npm: command not found`  
**Solution**: Install Node.js from https://nodejs.org/

**Problem**: Port 4173 already in use  
**Solution**: Change the port in `dashboard/server.js` or kill the process:
```bash
# Find process
lsof -i :4173  # macOS/Linux
netstat -ano | findstr :4173  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

### Permission Issues

**Problem**: Permission denied when installing packages  
**Solution**: Use virtual environment or add `--user` flag:
```bash
pip install -r requirements.txt --user
```

---

## Next Steps

After successful installation:

1. **[Quick Start Tutorial](Quick-Start-Tutorial)** - Run your first analysis
2. **[Configuration](Configuration)** - Customize settings
3. **[Spark Job Analysis](Spark-Job-Analysis)** - Analyze your first Spark job
4. **[Dashboard Guide](Dashboard-Guide)** - Explore the web interface

---

## Getting Help

If you encounter issues during installation:

- Check the **[Troubleshooting](Troubleshooting)** page
- Review **[FAQ](FAQ)** for common questions
- Open an issue on [GitHub](https://github.com/sumitasthana/kratos-agents/issues)
- Search existing issues for solutions

---

**Last Updated**: February 2026  
**Status**: [PASS] Tested on Python 3.10-3.12, macOS/Linux/Windows
