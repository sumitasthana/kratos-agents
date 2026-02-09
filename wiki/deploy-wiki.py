#!/usr/bin/env python3
"""
Kratos Wiki Deployment Script (Python version)
Deploys wiki content to GitHub Wiki repository
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
REPO_NAME = "sumitasthana/kratos-agents"
WIKI_URL = f"https://github.com/{REPO_NAME}.wiki.git"
WIKI_SOURCE = Path(__file__).parent
TEMP_DIR = Path("/tmp/kratos-wiki-deploy")

# Colors for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color

def print_step(step_num, message):
    """Print a deployment step message"""
    print(f"\n{Colors.YELLOW}Step {step_num}: {message}{Colors.NC}")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_error(message):
    """Print an error message"""
    print(f"{Colors.RED}✗ {message}{Colors.NC}")

def run_command(cmd, cwd=None, check=True):
    """Run a shell command and return result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def check_git_config():
    """Check if git is configured"""
    success, stdout, _ = run_command("git config user.name", check=False)
    if not success or not stdout.strip():
        print_error("Git user.name not configured")
        print("Please configure git:")
        print("  git config --global user.name \"Your Name\"")
        print("  git config --global user.email \"your.email@example.com\"")
        return False
    return True

def count_wiki_pages():
    """Count markdown files in wiki source directory"""
    md_files = list(WIKI_SOURCE.glob("*.md"))
    return len(md_files)

def deploy_wiki():
    """Main deployment function"""
    print("=" * 50)
    print("   Kratos Wiki Deployment Script")
    print("=" * 50)
    print()
    
    # Check if wiki source directory has markdown files
    if not WIKI_SOURCE.exists():
        print_error(f"Wiki source directory not found: {WIKI_SOURCE}")
        return False
    
    page_count = count_wiki_pages()
    if page_count == 0:
        print_error("No wiki pages found!")
        return False
    
    print_step(1, "Preparing wiki content...")
    print(f"Source directory: {WIKI_SOURCE}")
    print_success(f"Found {page_count} wiki pages")
    print()
    
    # Check git configuration
    if not check_git_config():
        return False
    
    print_step(2, "Cloning wiki repository...")
    
    # Clean up existing temp directory
    if TEMP_DIR.exists():
        print("Removing existing temp directory...")
        shutil.rmtree(TEMP_DIR)
    
    # Clone wiki repository
    success, stdout, stderr = run_command(
        f"git clone {WIKI_URL} {TEMP_DIR}",
        check=False
    )
    
    if not success:
        print_error("Failed to clone wiki repository")
        print()
        print("The wiki repository doesn't exist yet. Please initialize it:")
        print("1. Go to: https://github.com/sumitasthana/kratos-agents/wiki")
        print("2. Click 'Create the first page'")
        print("3. Add any content and save")
        print("4. Then run this script again")
        return False
    
    print_success("Wiki repository cloned successfully")
    print()
    
    print_step(3, "Copying wiki content...")
    
    # Copy all markdown files
    md_files = list(WIKI_SOURCE.glob("*.md"))
    copied_count = 0
    
    for md_file in md_files:
        if md_file.name == "README.md":
            # Skip README.md as it's for the wiki directory itself
            continue
        
        dest_file = TEMP_DIR / md_file.name
        shutil.copy2(md_file, dest_file)
        print(f"  Copied: {md_file.name}")
        copied_count += 1
    
    print_success(f"{copied_count} wiki files copied")
    print()
    
    print_step(4, "Committing changes...")
    
    # Navigate to wiki directory and commit
    os.chdir(TEMP_DIR)
    
    # Add all changes
    run_command("git add -A")
    
    # Check if there are changes to commit
    success, stdout, _ = run_command("git diff --staged --quiet", check=False)
    
    if success:  # No changes (exit code 0 means no diff)
        print_success("No changes detected. Wiki is already up to date.")
        cleanup()
        return True
    
    # Commit changes
    commit_message = f"Update Kratos wiki - {datetime.now().strftime('%Y-%m-%d')}"
    success, _, stderr = run_command(f'git commit -m "{commit_message}"')
    
    if not success:
        print_error("Failed to commit changes")
        print(stderr)
        cleanup()
        return False
    
    print_success("Changes committed")
    print()
    
    print_step(5, "Pushing to GitHub...")
    
    # Push to GitHub
    success, stdout, stderr = run_command("git push origin master", check=False)
    
    if not success:
        print_error("Failed to push to GitHub")
        print(stderr)
        print()
        print("Please ensure you have write access to the wiki repository.")
        cleanup()
        return False
    
    print_success("Wiki successfully deployed to GitHub!")
    print()
    
    cleanup()
    
    print("=" * 50)
    print(f"{Colors.GREEN}   Wiki Deployment Complete!{Colors.NC}")
    print("=" * 50)
    print()
    print(f"Wiki URL: https://github.com/{REPO_NAME}/wiki")
    print()
    print("Pages deployed:")
    for md_file in md_files:
        if md_file.name != "README.md":
            page_name = md_file.stem.replace('-', ' ')
            print(f"  • {page_name}")
    print()
    print_success("All done!")
    
    return True

def cleanup():
    """Clean up temporary files"""
    print()
    print_step(6, "Cleaning up...")
    
    # Return to original directory
    os.chdir(WIKI_SOURCE)
    
    # Remove temp directory
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        print_success("Temporary files cleaned up")

def main():
    """Main entry point"""
    try:
        success = deploy_wiki()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print()
        print_error("Deployment cancelled by user")
        cleanup()
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()
