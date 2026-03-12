# Wiki Deployment Instructions

This guide provides step-by-step instructions for deploying the Kratos wiki to GitHub.

---

## Prerequisites

Before deploying the wiki, ensure:

1. [PASS] You have write access to the repository
2. [PASS] GitHub wiki feature is enabled for the repository
3. [PASS] You have git configured locally
4. [PASS] All wiki content files are in the `wiki/` directory

---

## Deployment Methods

### Method 1: Using the Automated Script (Recommended)

We've created a deployment script that automates the entire process.

#### Step 1: Initialize Wiki on GitHub (One-time Setup)

**The GitHub wiki must be initialized before the automated script can push to it.**

1. Go to: https://github.com/sumitasthana/kratos-agents/wiki
2. Click **"Create the first page"** button
3. In the page editor:
   - Title: `Home`
   - Content: `Initial page - will be replaced by automated deployment`
4. Click **"Save Page"**

This creates the wiki git repository at: `https://github.com/sumitasthana/kratos-agents.wiki.git`

#### Step 2: Run the Deployment Script

```bash
cd /path/to/kratos-agents/wiki
./deploy-wiki.sh
```

The script will:
1. [PASS] Clone the wiki repository
2. [PASS] Copy all wiki pages
3. [PASS] Commit changes
4. [PASS] Push to GitHub
5. [PASS] Clean up temporary files

#### Step 3: Verify Deployment

Visit https://github.com/sumitasthana/kratos-agents/wiki to see your deployed wiki!

---

### Method 2: Manual Deployment

If you prefer manual control or the script doesn't work for your environment:

#### Step 1: Initialize Wiki on GitHub (if not done)

Same as Method 1, Step 1 above.

#### Step 2: Clone the Wiki Repository

```bash
# Create a temporary directory
mkdir /tmp/wiki-deploy
cd /tmp/wiki-deploy

# Clone the wiki repository
git clone https://github.com/sumitasthana/kratos-agents.wiki.git
cd kratos-agents.wiki
```

#### Step 3: Copy Wiki Files

```bash
# Copy all markdown files from your wiki directory
cp /path/to/kratos-agents/wiki/*.md .

# Verify files were copied
ls -la *.md
```

You should see:
- Home.md
- Installation-Guide.md
- Quick-Start-Tutorial.md
- Spark-Job-Analysis.md
- Troubleshooting.md
- FAQ.md
- Examples.md
- _Sidebar.md
- README.md (optional, for documentation)

#### Step 4: Commit and Push

```bash
# Stage all files
git add -A

# Commit with descriptive message
git commit -m "Deploy comprehensive Kratos wiki documentation"

# Push to GitHub
git push origin master
```

#### Step 5: Clean Up

```bash
# Return to your project
cd /path/to/kratos-agents

# Remove temporary directory
rm -rf /tmp/wiki-deploy
```

---

### Method 3: Using GitHub Web Interface (Individual Pages)

For updating individual pages without command line:

#### For Each Wiki Page:

1. Go to https://github.com/sumitasthana/kratos-agents/wiki
2. Click **"New Page"** (or edit existing page)
3. Set the page title (e.g., "Installation Guide")
4. Copy content from the corresponding `.md` file in `wiki/` directory
5. Click **"Save Page"**

**Note**: The page name in the URL will be the title with hyphens (e.g., `Installation-Guide`)

#### Create These Pages:

| Page Title | Source File | URL Path |
|------------|-------------|----------|
| Home | Home.md | `/Home` |
| Installation Guide | Installation-Guide.md | `/Installation-Guide` |
| Quick Start Tutorial | Quick-Start-Tutorial.md | `/Quick-Start-Tutorial` |
| Spark Job Analysis | Spark-Job-Analysis.md | `/Spark-Job-Analysis` |
| Troubleshooting | Troubleshooting.md | `/Troubleshooting` |
| FAQ | FAQ.md | `/FAQ` |
| Examples | Examples.md | `/Examples` |

#### Add Sidebar Navigation:

1. While on any wiki page, click **"Add a custom sidebar"**
2. Copy content from `_Sidebar.md`
3. Click **"Save Page"**

---

## Verification Checklist

After deployment, verify:

- [ ] Home page loads correctly
- [ ] All internal links work (no broken links)
- [ ] Sidebar navigation appears on all pages
- [ ] Code blocks are properly formatted
- [ ] Tables render correctly
- [ ] Images display (if any added)
- [ ] Page structure is preserved

---

## Updating the Wiki

### For Future Updates:

1. **Edit** the markdown files in `wiki/` directory
2. **Commit** changes to your main repository
3. **Deploy** using one of the methods above

### Quick Update Script:

```bash
# One-liner to update wiki (after initial setup)
cd wiki && ./deploy-wiki.sh
```

---

## Troubleshooting Deployment

### Issue: "Wiki repository doesn't exist"

**Solution**: Initialize the wiki on GitHub first (see Method 1, Step 1)

### Issue: "Authentication failed"

**Solution**: Ensure you're authenticated with GitHub
```bash
# Configure git credentials
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# For HTTPS, you may need a personal access token
# Generate at: https://github.com/settings/tokens
```

### Issue: "Permission denied"

**Solution**: Ensure you have write access to the repository

### Issue: Links not working in wiki

**Cause**: GitHub wiki uses different link format

**Solution**: Use wiki-style links without `.md` extension
```markdown
# [PASS] Correct
[Installation Guide](Installation-Guide)

# [FAIL] Wrong
[Installation Guide](Installation-Guide.md)
```

### Issue: Sidebar not showing

**Solution**: 
1. File must be named exactly `_Sidebar.md`
2. Must be deployed to wiki repository
3. Refresh browser cache

---

## Wiki Structure Overview

After deployment, your wiki will have:

###  Getting Started (3 pages)
- Home - Landing page with overview
- Installation Guide - Setup instructions
- Quick Start Tutorial - First steps

###  Feature Guides (1+ pages)
- Spark Job Analysis - Complete Spark analysis guide
- Git Dataflow Analysis - (planned)
- Data Lineage Extraction - (planned)

###  Advanced Topics (planned)
- Dashboard Guide
- Agent System
- Custom Agents
- API Reference

###  Help & Support (3 pages)
- Troubleshooting - Common issues
- FAQ - Frequently asked questions
- Examples - Real-world use cases

### [TARGET] Navigation
- _Sidebar - Navigation menu (appears on all pages)

---

## Automation Options

### GitHub Actions Workflow

Create `.github/workflows/deploy-wiki.yml`:

```yaml
name: Deploy Wiki

on:
  push:
    branches: [main]
    paths:
      - 'wiki/**'

jobs:
  deploy-wiki:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Deploy to Wiki
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          git clone https://$GITHUB_TOKEN@github.com/${{ github.repository }}.wiki.git wiki-repo
          cp wiki/*.md wiki-repo/
          cd wiki-repo
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add .
          git commit -m "Auto-deploy wiki from main branch" || exit 0
          git push
```

This automatically deploys wiki changes when you push to main branch.

---

## Best Practices

### 1. Version Control
Keep wiki content in your main repository (`wiki/` directory) so it's:
- Version controlled
- Reviewed in pull requests
- Backed up with your code

### 2. Link Validation
Before deploying, check all internal links:
```bash
# Find all wiki links
grep -r "\[.*\](" wiki/*.md
```

### 3. Test Locally
Preview markdown locally before deploying:
```bash
# Use any markdown viewer
# Or GitHub's markdown preview in VS Code
```

### 4. Consistent Updates
Always update both:
1. Source files in `wiki/` directory
2. Deployed wiki (via deployment method)

### 5. Backup
GitHub wiki has its own git repository. Clone it for backup:
```bash
git clone https://github.com/sumitasthana/kratos-agents.wiki.git wiki-backup
```

---

## Wiki Statistics

Current wiki includes:

- **Total Pages**: 9 pages (+ more planned)
- **Total Content**: ~35,000 words
- **Code Examples**: 100+ snippets
- **Coverage**: All major features
- **Last Updated**: February 2026

---

## Next Steps After Deployment

1. [PASS] Verify all pages deployed correctly
2. [PASS] Test all internal links
3. [PASS] Share wiki URL with team
4. [PASS] Add wiki link to README.md
5. ⏳ Create additional pages as needed
6. ⏳ Add screenshots/diagrams
7. ⏳ Set up automated deployment

---

## Support

For deployment issues:
- Check [Troubleshooting](#troubleshooting-deployment) section above
- Verify GitHub wiki is enabled for repository
- Ensure you have write permissions
- Contact repository maintainers

---

## Quick Reference

### Wiki URLs:
- **Main Wiki**: https://github.com/sumitasthana/kratos-agents/wiki
- **Wiki Repo**: https://github.com/sumitasthana/kratos-agents.wiki.git
- **Source Files**: `/wiki/` directory in main repository

### Key Commands:
```bash
# Deploy wiki
cd wiki && ./deploy-wiki.sh

# Manual clone wiki
git clone https://github.com/sumitasthana/kratos-agents.wiki.git

# Update specific page
# Edit wiki/<Page-Name>.md, then deploy
```

---

**Version**: 1.0  
**Last Updated**: February 2026  
**Status**: Ready for Deployment [LAUNCH]
