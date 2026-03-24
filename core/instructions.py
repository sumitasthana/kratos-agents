"""
core/instructions.py
Prompt loader utility for the Kratos agent system.

Moved from: src/prompt_loader.py
Import update: path now resolves to resources/prompts/ relative to repo root.

Loads LLM prompt definitions from YAML files under ``resources/prompts/``
at the repo root. This keeps prompt text out of source code and makes it easy
to diff, review, and version prompts independently.

Usage
-----
>>> from core.instructions import load_prompt, load_prompt_content
>>>
>>> # Full prompt record (id, description, source_file, agent, type, content)
>>> record = load_prompt("root_cause_spark")
>>> print(record["description"])
>>>
>>> # Just the content string — most common usage
>>> SYSTEM_PROMPT = load_prompt_content("root_cause_spark")
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

# Resolve once relative to repo root so the loader works regardless of cwd.
# core/instructions.py lives at <repo_root>/core/instructions.py
# prompts live at <repo_root>/resources/prompts/
_REPO_ROOT: Path = Path(__file__).resolve().parents[1]
_PROMPTS_DIR: Path = _REPO_ROOT / "resources" / "prompts"

# Fallback: if resources/prompts/ doesn't exist yet, fall back to legacy prompts/
if not _PROMPTS_DIR.exists():
    _PROMPTS_DIR = _REPO_ROOT / "prompts"


@lru_cache(maxsize=None)
def load_prompt(prompt_id: str) -> Dict[str, Any]:
    """
    Load and return a prompt record by ID.

    Parameters
    ----------
    prompt_id:
        The ``id`` field of the prompt (matches ``<id>.yaml`` filename).

    Returns
    -------
    dict with keys: id, description, source_file, agent, type, content.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist in the prompts directory.
    ValueError
        If the YAML file is missing the ``content`` key.
    """
    path = _PROMPTS_DIR / f"{prompt_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}. "
            f"Available prompts: {[p.stem for p in _PROMPTS_DIR.glob('*.yaml')]}"
        )
    record: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "content" not in record:
        raise ValueError(f"Prompt file {path} is missing required 'content' key.")
    return record


def load_prompt_content(prompt_id: str) -> str:
    """
    Convenience shortcut — returns just the ``content`` string for *prompt_id*.

    Example
    -------
    >>> SYSTEM_PROMPT = load_prompt_content("root_cause_spark")
    """
    return load_prompt(prompt_id)["content"]


def list_prompts() -> list[str]:
    """Return the IDs of all available prompts (file stems in the prompts dir)."""
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.yaml"))
