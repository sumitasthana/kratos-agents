# Main entry point for the GitHub Lineage Artifact Extractor

import os
import sys
import uuid
from datetime import datetime
from artifact_extractor import extract_artifacts
from json_formatter import format_to_json
from logger import setup_logger

def main():
    logger = setup_logger()

    if len(sys.argv) < 2:
        logger.error("Usage: python main.py <path_to_git_repo> [file_extensions] [keywords]")
        print("Usage: python main.py <path_to_git_repo> [file_extensions] [keywords]")
        sys.exit(1)

    repo_path = sys.argv[1]
    extensions = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2] else None
    keywords = sys.argv[3].split(',') if len(sys.argv) > 3 and sys.argv[3] else None

    logger.info(f"Extracting artifacts from repository: {repo_path}")
    extracted_data = extract_artifacts(repo_path, extensions, keywords)

    logger.info("Formatting extracted data to JSON")
    repo_name = os.path.basename(os.path.normpath(repo_path))
    formatted_json = format_to_json(repo_name, repo_path, extracted_data)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid.uuid4().hex[:8]
    output_file = f"git_artifacts_{repo_name}_{timestamp}_{run_id}.json"
    with open(output_file, "w") as f:
        f.write(formatted_json)

    logger.info(f"Extraction complete. Results saved to {output_file}")
    print(f"Extraction complete. Results saved to {output_file}")

if __name__ == "__main__":
    main()