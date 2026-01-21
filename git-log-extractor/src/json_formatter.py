import json

def format_to_json(repo_name, repo_url, extracted_data):
    """
    Format extracted data into structured JSON.

    :param repo_name: Name of the repository.
    :param repo_url: URL of the repository.
    :param extracted_data: Extracted lineage artifacts.
    :return: JSON string of the formatted data.
    """
    formatted_data = {
        "repository": {
            "name": repo_name,
            "url": repo_url
        },
        "files": []
    }

    for commit in extracted_data:
        for mod in commit["modified_files"]:
            file_entry = {
                "file_path": mod["file_path"],
                "commits": [
                    {
                        "commit_hash": commit["hash"],
                        "author": commit["author"],
                        "date": commit["date"],
                        "message": commit["message"],
                        "diff": mod["diff"],
                        "added_lines": mod["added_lines"],
                        "deleted_lines": mod["deleted_lines"]
                    }
                ]
            }
            formatted_data["files"].append(file_entry)

    return json.dumps(formatted_data, indent=4)