# scripts/setup_log_storage.py
"""
Initialize and manage log storage structure for Kratos Agent Platform
Production-grade log storage manager
"""

import logging
from pathlib import Path
import json
from datetime import datetime
from typing import List, Tuple, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogStorageManager:
    """
    Manages the directory structure for Kratos log storage.
    Handles creation, validation, and indexing of log directories.
    """
    
    def __init__(self, base_dir: str = "logs"):
        """
        Initialize the log storage manager.
        
        Args:
            base_dir: Base directory for all log storage (default: "logs")
        """
        self.base_dir = Path(base_dir)
        self.directories = [
            ("raw/spark_events", "Spark event logs storage"),
            ("raw/openlineage", "OpenLineage JSON logs storage"),
            ("raw/git_repos", "Git repositories for dataflow analysis"),
            ("raw/etl_scripts", "ETL scripts for lineage extraction"),
            ("processed/fingerprints", "Generated fingerprints output"),
            ("processed/analysis_results", "AI agent analysis results output"),
            ("processed/lineage_graphs", "Data lineage visualization output"),
            ("archives", "Archived and backup logs")
        ]
        
    def setup(self) -> Path:
        """
        Create all necessary directories for log storage.
        
        Returns:
            Path: The base directory path
        """
        logger.info("Initializing Kratos log storage structure")
        logger.info(f"Base directory: {self.base_dir.absolute()}")
        
        created_dirs = self._create_directories()
        self._create_readme_files()
        self._create_index()
        
        logger.info(f"Successfully created {len(created_dirs)} directories")
        self._print_summary(created_dirs)
        
        return self.base_dir
    
    def _create_directories(self) -> List[Tuple[Path, str]]:
        """
        Create all directory paths.
        
        Returns:
            List of tuples containing (path, description)
        """
        created_dirs = []
        
        for dir_path, description in self.directories:
            full_path = self.base_dir / dir_path
            
            try:
                full_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append((full_path, description))
                logger.debug(f"Created directory: {full_path}")
            except Exception as e:
                logger.error(f"Failed to create directory {full_path}: {e}")
                raise
        
        return created_dirs
    
    def _create_readme_files(self) -> None:
        """Create README.md files in each subdirectory for documentation."""
        for dir_path, description in self.directories:
            if "archives" in dir_path:
                continue
                
            full_path = self.base_dir / dir_path
            readme_path = full_path / "README.md"
            
            subdir_name = dir_path.split('/')[-1]
            title = subdir_name.replace('_', ' ').title()
            
            readme_content = f"""# {title}

## Description
{description}

## Usage
Place relevant files in this directory for processing by Kratos agents.

## File Naming Convention
- Use descriptive names with timestamps
- Format: `{{name}}_{{YYYYMMDD}}_{{HHMMSS}}.{{ext}}`
- Example: `financial_etl_20260210_103000.json`

## Notes
- Check the parent INDEX.json for overall structure
- Processed outputs will be saved to logs/processed/
"""
            
            try:
                readme_path.write_text(readme_content, encoding='utf-8')
                logger.debug(f"Created README: {readme_path}")
            except Exception as e:
                logger.warning(f"Failed to create README at {readme_path}: {e}")
    
    def _create_index(self) -> None:
        """Create master INDEX.json file documenting the structure."""
        index = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0",
                "base_directory": str(self.base_dir.absolute()),
                "system": "Kratos Agent Platform"
            },
            "structure": {
                "raw": {
                    "spark_events": {
                        "description": "Spark event logs",
                        "supported_formats": [".json", ".log"],
                        "purpose": "Spark job performance analysis"
                    },
                    "openlineage": {
                        "description": "OpenLineage JSON logs",
                        "supported_formats": [".json"],
                        "purpose": "Data lineage extraction and analysis"
                    },
                    "git_repos": {
                        "description": "Git repositories",
                        "supported_formats": ["git repository"],
                        "purpose": "Code dataflow analysis"
                    },
                    "etl_scripts": {
                        "description": "ETL scripts",
                        "supported_formats": [".py", ".sql", ".scala"],
                        "purpose": "Static lineage extraction"
                    }
                },
                "processed": {
                    "fingerprints": {
                        "description": "Generated fingerprints",
                        "output_format": "JSON"
                    },
                    "analysis_results": {
                        "description": "AI agent analysis results",
                        "output_format": "JSON"
                    },
                    "lineage_graphs": {
                        "description": "Data lineage visualizations",
                        "output_format": "JSON/DOT"
                    }
                },
                "archives": {
                    "description": "Archived logs and backups",
                    "retention_policy": "Manual cleanup"
                }
            },
            "workflows": {
                "collect": "Place raw logs in logs/raw/{{type}}/",
                "process": "Run Kratos CLI commands to generate fingerprints",
                "analyze": "AI agents produce insights in logs/processed/",
                "archive": "Move old logs to logs/archives/"
            }
        }
        
        index_path = self.base_dir / "INDEX.json"
        
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
            logger.info(f"Created index file: {index_path}")
        except Exception as e:
            logger.error(f"Failed to create index file: {e}")
            raise
    
    def _print_summary(self, created_dirs: List[Tuple[Path, str]]) -> None:
        """
        Print summary of created directories.
        
        Args:
            created_dirs: List of created directory paths and descriptions
        """
        print("\n" + "=" * 70)
        print("LOG STORAGE STRUCTURE SUMMARY")
        print("=" * 70)
        
        for dir_path, description in created_dirs:
            print(f"\n[DIR] {dir_path}")
            print(f"      {description}")
        
        print("\n" + "=" * 70)
        print(f"Base Directory: {self.base_dir.absolute()}")
        print(f"Total Directories: {len(created_dirs)}")
        print(f"Index File: {self.base_dir / 'INDEX.json'}")
        print("=" * 70 + "\n")
    
    def print_structure(self, max_depth: int = 3) -> None:
        """
        Print the directory tree structure.
        
        Args:
            max_depth: Maximum depth to display (default: 3)
        """
        print(f"\nDirectory Structure: {self.base_dir}/")
        print("-" * 70)
        
        def print_tree(directory: Path, prefix: str = "", depth: int = 0) -> None:
            if depth >= max_depth:
                return
                
            try:
                items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                
                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    current = "+-- " if is_last else "|-- "
                    print(f"{prefix}{current}{item.name}")
                    
                    if item.is_dir():
                        extension = "    " if is_last else "|   "
                        try:
                            if any(item.iterdir()):
                                print_tree(item, prefix + extension, depth + 1)
                        except PermissionError:
                            pass
            except PermissionError:
                logger.warning(f"Permission denied: {directory}")
        
        if self.base_dir.exists():
            print_tree(self.base_dir)
        else:
            logger.error("Base directory does not exist. Run setup() first.")
        
        print("-" * 70 + "\n")
    
    def validate(self) -> bool:
        """
        Validate that all expected directories exist.
        
        Returns:
            bool: True if all directories exist, False otherwise
        """
        logger.info("Validating log storage structure")
        
        all_exist = True
        for dir_path, _ in self.directories:
            full_path = self.base_dir / dir_path
            
            if not full_path.exists():
                logger.error(f"Missing directory: {full_path}")
                all_exist = False
            else:
                logger.debug(f"Validated: {full_path}")
        
        index_path = self.base_dir / "INDEX.json"
        if not index_path.exists():
            logger.error(f"Missing index file: {index_path}")
            all_exist = False
        
        if all_exist:
            logger.info("Validation successful: All directories exist")
        else:
            logger.error("Validation failed: Some directories are missing")
        
        return all_exist
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about stored logs.
        
        Returns:
            Dictionary with file counts per category
        """
        stats = {}
        
        raw_dir = self.base_dir / "raw"
        if raw_dir.exists():
            for subdir in raw_dir.iterdir():
                if subdir.is_dir():
                    file_count = sum(1 for _ in subdir.rglob("*") if _.is_file())
                    stats[subdir.name] = file_count
        
        logger.info(f"Storage statistics: {stats}")
        return stats


def main():
    """Main entry point for the script."""
    manager = LogStorageManager()
    
    # Setup directories
    base_path = manager.setup()
    
    # Print structure
    manager.print_structure()
    
    # Validate
    is_valid = manager.validate()
    
    if is_valid:
        logger.info("Log storage setup completed successfully")
        return 0
    else:
        logger.error("Log storage setup completed with errors")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
