import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _ensure_git_log_extractor_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    extractor_src = repo_root / "git-log-extractor" / "src"
    if extractor_src.exists() and str(extractor_src) not in sys.path:
        sys.path.insert(0, str(extractor_src))
    return extractor_src


def extract_git_log_artifacts(
    repo_path: str,
    extensions: list[str] | None = None,
    keywords: list[str] | None = None,
    output_path: str | None = None,
) -> str:
    extractor_src = _ensure_git_log_extractor_on_path()
    if not extractor_src.exists():
        raise FileNotFoundError(f"git-log-extractor source not found at: {extractor_src}")

    from artifact_extractor import extract_artifacts  # type: ignore
    from json_formatter import format_to_json  # type: ignore

    repo_path_p = Path(repo_path)
    if not repo_path_p.exists():
        raise FileNotFoundError(f"Git repo path not found: {repo_path_p}")

    extracted_data = extract_artifacts(str(repo_path_p), extensions, keywords)

    repo_name = repo_path_p.name
    formatted_json = format_to_json(repo_name, str(repo_path_p), extracted_data)

    if output_path:
        output_file = Path(output_path)
    else:
        repo_root = Path(__file__).resolve().parents[1]
        output_dir = repo_root / "git_artifacts"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        run_id = uuid4().hex[:8]
        output_file = output_dir / f"git_artifacts_{repo_name}_{timestamp}_{run_id}.json"

    output_file.write_text(formatted_json, encoding="utf-8")
    return str(output_file)
