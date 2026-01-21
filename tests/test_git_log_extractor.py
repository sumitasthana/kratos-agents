from pathlib import Path


def test_git_log_extractor_src_path_exists():
    repo_root = Path(__file__).resolve().parents[1]
    extractor_src = repo_root / "git-log-extractor" / "src"
    assert extractor_src.exists()


def test_git_log_extractor_wrapper_importable():
    from src.git_log_extractor import extract_git_log_artifacts  # noqa: F401
