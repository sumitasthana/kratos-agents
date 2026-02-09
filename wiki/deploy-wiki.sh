#!/bin/bash

# Kratos Wiki Deployment Script
# This script deploys the wiki content to GitHub Wiki

set -e  # Exit on error

echo "=========================================="
echo "   Kratos Wiki Deployment Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/sumitasthana/kratos-agents.git"
WIKI_URL="https://github.com/sumitasthana/kratos-agents.wiki.git"
WIKI_SOURCE="./wiki"
TEMP_WIKI_DIR="/tmp/kratos-wiki-deploy"

# Check if wiki directory exists
if [ ! -d "$WIKI_SOURCE" ]; then
    echo -e "${RED}Error: Wiki source directory '$WIKI_SOURCE' not found!${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Preparing wiki content...${NC}"
echo "Source directory: $WIKI_SOURCE"
echo ""

# Count wiki pages
PAGE_COUNT=$(find "$WIKI_SOURCE" -name "*.md" | wc -l)
echo -e "${GREEN}Found $PAGE_COUNT wiki pages${NC}"
echo ""

# Check if git is configured
if ! git config user.name > /dev/null 2>&1; then
    echo -e "${YELLOW}Git user.name not configured. Please configure git:${NC}"
    echo "  git config --global user.name \"Your Name\""
    echo "  git config --global user.email \"your.email@example.com\""
    exit 1
fi

echo -e "${YELLOW}Step 2: Cloning wiki repository...${NC}"

# Clean up any existing temp directory
if [ -d "$TEMP_WIKI_DIR" ]; then
    echo "Removing existing temp directory..."
    rm -rf "$TEMP_WIKI_DIR"
fi

# Clone the wiki repository
echo "Cloning wiki from: $WIKI_URL"
if git clone "$WIKI_URL" "$TEMP_WIKI_DIR" 2>/dev/null; then
    echo -e "${GREEN}✓ Wiki repository cloned successfully${NC}"
else
    echo -e "${YELLOW}Wiki repository doesn't exist yet. Creating initial wiki...${NC}"
    echo "Please ensure the wiki is initialized on GitHub first."
    echo ""
    echo "To initialize the wiki on GitHub:"
    echo "1. Go to: https://github.com/sumitasthana/kratos-agents/wiki"
    echo "2. Click 'Create the first page'"
    echo "3. Add any content and save"
    echo "4. Then run this script again"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 3: Copying wiki content...${NC}"

# Copy all markdown files from wiki source to temp directory
cp -v "$WIKI_SOURCE"/*.md "$TEMP_WIKI_DIR/"
echo -e "${GREEN}✓ Wiki files copied${NC}"
echo ""

echo -e "${YELLOW}Step 4: Committing changes...${NC}"

# Navigate to temp wiki directory
cd "$TEMP_WIKI_DIR"

# Add all changes
git add -A

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo -e "${YELLOW}No changes detected. Wiki is already up to date.${NC}"
    cd - > /dev/null
    rm -rf "$TEMP_WIKI_DIR"
    exit 0
fi

# Commit changes
COMMIT_MESSAGE="Update Kratos wiki - $(date +%Y-%m-%d)"
git commit -m "$COMMIT_MESSAGE"
echo -e "${GREEN}✓ Changes committed${NC}"
echo ""

echo -e "${YELLOW}Step 5: Pushing to GitHub...${NC}"

# Push to GitHub
if git push origin master; then
    echo -e "${GREEN}✓ Wiki successfully deployed to GitHub!${NC}"
else
    echo -e "${RED}Error: Failed to push to GitHub${NC}"
    echo "Please ensure you have write access to the wiki repository."
    cd - > /dev/null
    rm -rf "$TEMP_WIKI_DIR"
    exit 1
fi

# Return to original directory
cd - > /dev/null

echo ""
echo -e "${YELLOW}Step 6: Cleaning up...${NC}"
rm -rf "$TEMP_WIKI_DIR"
echo -e "${GREEN}✓ Temporary files cleaned up${NC}"

echo ""
echo "=========================================="
echo -e "${GREEN}   Wiki Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Wiki URL: https://github.com/sumitasthana/kratos-agents/wiki"
echo ""
echo "Pages deployed:"
ls -1 "$WIKI_SOURCE"/*.md | xargs -n1 basename | sed 's/.md$//' | sed 's/^/  • /'
echo ""
echo -e "${GREEN}✓ All done!${NC}"
