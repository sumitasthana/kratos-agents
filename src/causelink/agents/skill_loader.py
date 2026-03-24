"""
causelink/agents/skill_loader.py

SkillLoader — reads SKILL.md files from the skills/ directory at agent init.

Design:
  - Each agent calls SkillLoader.load(skill_name) to get the SKILL.md content
    for its domain as a string. The skill content is used to prime agent behavior
    and validate that the skill contract is in place before the agent runs.
  - SkillLoader resolves paths relative to the repository root (CLAUDE.md location).
  - Missing skill files are a WARNING, not an error — the agent proceeds but logs
    that it is running without its skill contract loaded.
  - CLAUDE.md (master directive) is always loaded at import time and cached.

Usage:
    from causelink.agents.skill_loader import SkillLoader

    loader = SkillLoader()
    skill_text = loader.load("log-analyst")      # reads skills/log-analyst/SKILL.md
    master_text = loader.master_directive         # reads CLAUDE.md (cached)
    all_skills = loader.list_skills()             # returns list of available skill names
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repository root detection
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from this file until we find CLAUDE.md (repo root marker)."""
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "CLAUDE.md").exists():
            return parent
    # Fallback: use the grandparent of src/ as a best-guess root
    return Path(__file__).resolve().parents[3]


_REPO_ROOT: Path = _find_repo_root()
_SKILLS_DIR: Path = _REPO_ROOT / "skills"
_CLAUDE_MD: Path = _REPO_ROOT / "CLAUDE.md"


# ---------------------------------------------------------------------------
# Skill name → directory mapping
# ---------------------------------------------------------------------------

_SKILL_DIR_NAMES: Dict[str, str] = {
    "rca-orchestrator":      "rca-orchestrator",
    "intake-agent":          "intake-agent",
    "log-analyst":           "log-analyst",
    "hypothesis-agent":      "hypothesis-agent",
    "causal-edge-agent":     "causal-edge-agent",
    "confidence-agent":      "confidence-agent",
    "remediation-agent":     "remediation-agent",
    "conversation-interface": "conversation-interface",
}


# ---------------------------------------------------------------------------
# SkillLoader
# ---------------------------------------------------------------------------


class SkillLoader:
    """
    Loads SKILL.md files from the skills/ directory tree.

    All file reads are performed once and cached per instance.
    Thread-safe for read access (no mutation after init).
    """

    def __init__(self, skills_dir: Optional[Path] = None, claude_md: Optional[Path] = None) -> None:
        self._skills_dir = skills_dir or _SKILLS_DIR
        self._claude_md_path = claude_md or _CLAUDE_MD
        self._cache: Dict[str, str] = {}
        self._master: Optional[str] = None

        if not self._skills_dir.exists():
            logger.warning(
                "SkillLoader: skills directory not found at %s — "
                "agents will run without skill contracts.",
                self._skills_dir,
            )
        if not self._claude_md_path.exists():
            logger.warning(
                "SkillLoader: CLAUDE.md not found at %s — "
                "master directive unavailable.",
                self._claude_md_path,
            )

    # ── Master directive ──────────────────────────────────────────────────

    @property
    def master_directive(self) -> str:
        """
        Return the contents of CLAUDE.md (master agent directive).
        Cached after first read. Returns empty string if file not found.
        """
        if self._master is None:
            if self._claude_md_path.exists():
                self._master = self._claude_md_path.read_text(encoding="utf-8")
                logger.debug("SkillLoader: master directive loaded (%d chars)", len(self._master))
            else:
                self._master = ""
                logger.warning("SkillLoader: CLAUDE.md missing — master directive is empty.")
        return self._master

    # ── Individual skill loading ──────────────────────────────────────────

    def load(self, skill_name: str) -> str:
        """
        Load and return the SKILL.md content for the named skill.

        Args:
            skill_name: One of the keys in _SKILL_DIR_NAMES (e.g. "log-analyst").

        Returns:
            Full text of the SKILL.md file, or empty string if missing.

        Raises:
            Never — missing skill files are logged as warnings only.
        """
        if skill_name in self._cache:
            return self._cache[skill_name]

        dir_name = _SKILL_DIR_NAMES.get(skill_name, skill_name)
        skill_path = self._skills_dir / dir_name / "SKILL.md"

        if not skill_path.exists():
            logger.warning(
                "SkillLoader: SKILL.md not found for '%s' at %s — "
                "agent proceeds without skill contract.",
                skill_name,
                skill_path,
            )
            self._cache[skill_name] = ""
            return ""

        content = skill_path.read_text(encoding="utf-8")
        self._cache[skill_name] = content
        logger.debug(
            "SkillLoader: loaded skill '%s' (%d chars) from %s",
            skill_name,
            len(content),
            skill_path,
        )
        return content

    # ── Bulk operations ───────────────────────────────────────────────────

    def load_all(self) -> Dict[str, str]:
        """Load all registered skills and return as a dict of {skill_name: content}."""
        return {name: self.load(name) for name in _SKILL_DIR_NAMES}

    def list_skills(self) -> List[str]:
        """Return names of all registered skills."""
        return list(_SKILL_DIR_NAMES.keys())

    def available_skills(self) -> List[str]:
        """Return names of skills whose SKILL.md files actually exist on disk."""
        available = []
        for name, dir_name in _SKILL_DIR_NAMES.items():
            skill_path = self._skills_dir / dir_name / "SKILL.md"
            if skill_path.exists():
                available.append(name)
        return available

    def skill_status(self) -> Dict[str, bool]:
        """Return {skill_name: file_exists} for all registered skills."""
        return {
            name: (_SKILLS_DIR / dir_name / "SKILL.md").exists()
            for name, dir_name in _SKILL_DIR_NAMES.items()
        }

    # ── Trigger resolution ────────────────────────────────────────────────

    def resolve_skill_for_input(self, user_text: str) -> str:
        """
        Heuristic: map free-form user input to the most likely skill name.
        Used by the /api/chat endpoint to select the opening skill.

        Priority order (first match wins):
          1. Explicit JSON payload → rca-orchestrator
          2. "caused", "hypothesis" → hypothesis-agent
          3. "chain", "path", "hops" → causal-edge-agent
          4. "confident", "confidence", "score" → confidence-agent
          5. "fix", "remediation", "action plan" → remediation-agent
          6. "log", "error line", "batch output" → log-analyst
          7. Scenario / incident keywords → intake-agent
          8. Default → conversation-interface
        """
        text = user_text.lower()

        # JSON payload detection
        if text.strip().startswith("{"):
            return "rca-orchestrator"

        trigger_map = [
            ("caused|hypothesis|what failed|what went wrong",        "hypothesis-agent"),
            ("chain|path|hops|traverse|backtrack|show me",           "causal-edge-agent"),
            ("confident|confidence|score|probability|how sure",      "confidence-agent"),
            ("fix|remediat|action plan|resolve|patch|change|repair", "remediation-agent"),
            ("log|error line|batch output|jcl output|grep",          "log-analyst"),
            ("inc-|scenario|investigation|incident|deposit|trust|wire|mt202|smdia|irr|aggregat", "intake-agent"),
        ]

        import re
        for pattern, skill_name in trigger_map:
            if re.search(pattern, text):
                return skill_name

        return "conversation-interface"


# ---------------------------------------------------------------------------
# Module-level singleton (optional convenience)
# ---------------------------------------------------------------------------

_default_loader: Optional[SkillLoader] = None


def get_loader() -> SkillLoader:
    """Return the module-level singleton SkillLoader, creating it on first call."""
    global _default_loader
    if _default_loader is None:
        _default_loader = SkillLoader()
    return _default_loader


def load_skill(skill_name: str) -> str:
    """Convenience function: load a single skill via the singleton loader."""
    return get_loader().load(skill_name)


def master_directive() -> str:
    """Convenience function: return CLAUDE.md content via the singleton loader."""
    return get_loader().master_directive
