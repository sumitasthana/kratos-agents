"""
Prompt loader utility.

Loads LLM prompt definitions from YAML files under the ``prompts/`` directory
at the repo root.  This keeps prompt text out of source code and makes it easy
to diff, review, and version prompts independently.

Usage
-----
>>> from src.prompt_loader import load_prompt, load_prompt_content
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

# Resolve once relative to this file so the loader works regardless of cwd.
_PROMPTS_DIR: Path = Path(__file__).resolve().parent.parent / "prompts"


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
        If ``prompts/<prompt_id>.yaml`` does not exist.
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
    """Return the IDs of all available prompts (file stems in prompts/)."""
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.yaml"))
