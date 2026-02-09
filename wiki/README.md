# Kratos Wiki Content

This directory contains the complete wiki documentation for the Kratos project.

## 📚 Wiki Pages

### Getting Started
- **Home.md** - Main wiki landing page with overview and navigation
- **Installation-Guide.md** - Detailed installation instructions for all platforms
- **Quick-Start-Tutorial.md** - Step-by-step tutorial for first-time users

### Core Features
- **Spark-Job-Analysis.md** - Complete guide to Spark job analysis
- **Git-Dataflow-Analysis.md** - Git repository dataflow extraction guide
- **Data-Lineage-Extraction.md** - Data lineage extraction guide

### Advanced Topics
- **Dashboard-Guide.md** - Interactive dashboard usage
- **Agent-System.md** - Understanding AI agents and orchestration
- **Custom-Agents.md** - Building custom analysis agents
- **API-Reference.md** - Complete API documentation

### Help & Support
- **Troubleshooting.md** - Common issues and solutions
- **FAQ.md** - Frequently asked questions
- **Examples.md** - Real-world usage examples

### Navigation
- **_Sidebar.md** - Wiki sidebar navigation menu

## 🚀 Deploying the Wiki

### Option 1: Automated Deployment (Recommended)

Use the provided deployment script:

```bash
cd wiki
./deploy-wiki.sh
```

This script will:
1. Clone the GitHub wiki repository
2. Copy all wiki pages
3. Commit and push changes
4. Clean up temporary files

### Option 2: Manual Deployment

1. **Initialize the wiki on GitHub** (if not already done):
   - Go to https://github.com/sumitasthana/kratos-agents/wiki
   - Click "Create the first page"
   - Add any content and save

2. **Clone the wiki repository**:
   ```bash
   git clone https://github.com/sumitasthana/kratos-agents.wiki.git
   cd kratos-agents.wiki
   ```

3. **Copy wiki files**:
   ```bash
   cp /path/to/kratos-agents/wiki/*.md .
   ```

4. **Commit and push**:
   ```bash
   git add -A
   git commit -m "Update wiki documentation"
   git push origin master
   ```

### Option 3: GitHub Web Interface

For individual page updates:
1. Go to https://github.com/sumitasthana/kratos-agents/wiki
2. Click the page you want to edit or "New Page"
3. Copy content from the corresponding .md file
4. Save the page

## 📝 Wiki Structure

```
wiki/
├── README.md                          # This file
├── deploy-wiki.sh                     # Automated deployment script
├── _Sidebar.md                        # Navigation sidebar
│
├── Home.md                            # Landing page
├── Installation-Guide.md              # Installation instructions
├── Quick-Start-Tutorial.md            # Getting started tutorial
│
├── Spark-Job-Analysis.md              # Spark analysis guide
├── Git-Dataflow-Analysis.md           # Git dataflow guide
├── Data-Lineage-Extraction.md         # Lineage extraction guide
│
├── Dashboard-Guide.md                 # Dashboard usage
├── Agent-System.md                    # AI agents overview
├── Custom-Agents.md                   # Custom agent development
├── API-Reference.md                   # API documentation
│
├── Troubleshooting.md                 # Common issues
├── FAQ.md                             # Frequently asked questions
├── Examples.md                        # Usage examples
│
└── [Additional pages as needed]
```

## ✨ Features

### Comprehensive Coverage
- **7+ core documentation pages**
- **40+ FAQ answers**
- **Multiple real-world examples**
- **Complete troubleshooting guide**

### Easy Navigation
- Sidebar navigation menu
- Cross-referenced links
- Organized by topic
- Search-friendly structure

### Platform Support
- Detailed installation for Linux, macOS, Windows
- Cloud platform instructions (Databricks, EMR, Dataproc)
- Docker deployment (planned)

### Visual Elements
- Code examples with syntax highlighting
- Emoji icons for better readability
- Structured tables and lists
- ASCII diagrams

## 🔄 Updating the Wiki

### Adding a New Page

1. **Create the markdown file**:
   ```bash
   touch wiki/New-Page.md
   ```

2. **Add content** following the existing page structure:
   ```markdown
   # Page Title
   
   Brief description.
   
   ---
   
   ## Section 1
   Content...
   
   ---
   
   **Last Updated**: February 2026
   ```

3. **Update _Sidebar.md** to include link:
   ```markdown
   * [New Page](New-Page)
   ```

4. **Deploy**:
   ```bash
   cd wiki
   ./deploy-wiki.sh
   ```

### Updating Existing Pages

1. Edit the .md file in the `wiki/` directory
2. Run the deployment script
3. Changes will be pushed to GitHub wiki

## 📦 What's Included

### Documentation Quality
- ✅ Production-ready content
- ✅ Tested on multiple platforms
- ✅ Beginner to advanced coverage
- ✅ Real-world examples
- ✅ Comprehensive troubleshooting

### Topics Covered
- ✅ Installation and setup
- ✅ Quick start tutorials
- ✅ All three core features
- ✅ Dashboard usage
- ✅ AI agent system
- ✅ API reference
- ✅ Troubleshooting
- ✅ FAQ (40+ questions)

## 🎯 Wiki Goals

1. **Accessibility** - Easy for beginners to get started
2. **Completeness** - Cover all features comprehensively
3. **Searchability** - Well-organized and cross-referenced
4. **Maintainability** - Easy to update and extend
5. **Visual** - Use formatting to enhance readability

## 🤝 Contributing to Wiki

To contribute improvements:

1. Fork the repository
2. Update wiki/*.md files
3. Test locally (view markdown)
4. Submit pull request
5. Wiki will be deployed after merge

## 📋 Checklist

Before deploying, ensure:

- [ ] All links work correctly
- [ ] Code examples are tested
- [ ] Screenshots are up to date (if any)
- [ ] Version numbers are current
- [ ] Cross-references are accurate
- [ ] Sidebar navigation is complete

## 🔗 Related Resources

- **Main README**: `/README.md` in repository root
- **API Docs**: `/API_REFERENCE.md`
- **Architecture**: `/ARCHITECTURE.md`
- **Quick Start**: `/QUICKSTART.md`

## 📊 Wiki Statistics

- **Total Pages**: 8+ documentation pages
- **Word Count**: ~30,000 words
- **Code Examples**: 100+ code snippets
- **Coverage**: All major features
- **Last Updated**: February 2026

## 🚦 Status

- ✅ Core documentation complete
- ✅ Installation guides for all platforms
- ✅ Comprehensive troubleshooting
- ✅ FAQ with 40+ answers
- ✅ Automated deployment script
- ✅ Navigation sidebar
- ⏳ Screenshot assets (optional)
- ⏳ Video tutorials (planned)

## 📞 Support

For wiki-related questions:
- Open an issue on GitHub
- Suggest improvements via pull request
- Discussion on GitHub Discussions

---

**Version**: 1.0.0  
**Last Updated**: February 2026  
**Status**: ✅ Production Ready
