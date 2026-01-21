from repository_interaction import extract_repository_data
from file_identifier import identify_files

def extract_artifacts(repo_path, extensions=None, keywords=None):
    """
    Extract lineage artifacts (commits, diffs, blame, file history) for filtered files in the repository.

    :param repo_path: Path to the Git repository.
    :param extensions: List of file extensions to include (e.g., ['.py']).
    :param keywords: List of keywords to search for in file content.
    :return: Extracted artifacts for the filtered files.
    """
    # Identify relevant files
    relevant_files = identify_files(repo_path, extensions, keywords)

    # Extract repository data
    repo_data = extract_repository_data(repo_path)

    # Filter repository data for relevant files
    filtered_data = []
    for commit in repo_data:
        filtered_commit = {
            "hash": commit["hash"],
            "author": commit["author"],
            "date": commit["date"],
            "message": commit["message"],
            "modified_files": [
                mod for mod in commit["modified_files"] if mod["file_path"] in relevant_files
            ]
        }
        if filtered_commit["modified_files"]:
            filtered_data.append(filtered_commit)

    return filtered_data