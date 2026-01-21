from pydriller import Repository
import os

def extract_repository_data(repo_path):
    """
    Extracts commit history, diffs, blame, and file history from the given repository.

    :param repo_path: Path to the Git repository.
    :return: List of extracted data for each commit.
    """
    extracted_data = []

    for commit in Repository(repo_path).traverse_commits():
        commit_data = {
            "hash": commit.hash,
            "author": commit.author.name,
            "date": commit.author_date.isoformat() if commit.author_date else None,
            "message": commit.msg,
            "modified_files": [
                {
                    "file_path": os.path.normpath(mod.new_path or mod.old_path or mod.filename).replace('\\', '/'),
                    "change_type": mod.change_type.name,
                    "diff": mod.diff,
                    "added_lines": mod.added_lines,
                    "deleted_lines": mod.deleted_lines
                }
                for mod in commit.modified_files
            ]
        }
        extracted_data.append(commit_data)

    return extracted_data