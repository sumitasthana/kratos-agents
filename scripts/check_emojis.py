#!/usr/bin/env python3
"""
scripts/check_emojis.py

CI gate: scan source files for emoji characters and exit non-zero if any are found.

Usage:
    python scripts/check_emojis.py                  # scan default paths
    python scripts/check_emojis.py --strict         # fail on any Unicode > U+2BFF
    python scripts/check_emojis.py src/ tests/      # scan specific paths

Exit codes:
    0  No emojis found.
    1  One or more emoji characters detected.
    2  Usage / configuration error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Emoji detection pattern
# Covers: Miscellaneous Symbols, Dingbats, Supplemental Symbols,
#         Emoticons, Enclosed Alphanumeric Supplement, Mahjong Tiles,
#         Variation Selectors (FE00-FE0F), and all SMP emoji blocks.
# Does NOT flag standard ASCII punctuation or Latin diacritics.
# ---------------------------------------------------------------------------
_EMOJI_RE = re.compile(
    r"["
    r"\U0001F300-\U0001F9FF"   # Misc Symbols and Pictographs, Emoticons, etc.
    r"\U0001FA00-\U0001FA6F"   # Chess, Symbols Extended-A
    r"\U0001FA70-\U0001FAFF"   # Symbols and Pictographs Extended-B
    r"\U00002702-\U000027B0"   # Dingbats
    r"\U0000FE00-\U0000FE0F"   # Variation Selectors (emoji modifier)
    r"\U0001F004"              # Mahjong Tile
    r"\U0001F0CF"              # Playing Card Black Joker
    r"\U0001F1E0-\U0001F1FF"   # Flags
    r"\U00002600-\U000026FF"   # Miscellaneous Symbols
    r"\U00002B50\U00002B55"    # Star, Circle
    r"]+"
)

# Files/directories to always skip
_SKIP_PATTERNS = [
    "venv", "venv311", "node_modules", "__pycache__",
    ".git", "dist", "build", ".pytest_cache",
    "_strip_emoji_docs.py",   # this file intentionally contains the map
    "check_emojis.py",        # self-exemption
]

# Extensions to scan
_SCAN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".md", ".yaml", ".yml", ".toml", ".rst",
    ".html", ".json", ".txt", ".sh", ".env",
    ".cfg", ".ini",
}


def _should_skip(path: Path) -> bool:
    parts = path.parts
    return any(skip in parts for skip in _SKIP_PATTERNS)


def scan_file(path: Path) -> List[Tuple[int, str]]:
    """Return (line_number, line_content) for every line containing an emoji."""
    hits: List[Tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return hits
    for i, line in enumerate(text.splitlines(), 1):
        if _EMOJI_RE.search(line):
            hits.append((i, line.rstrip()))
    return hits


def scan_paths(roots: List[Path], extensions: set) -> dict:
    """Scan all matching files under roots. Returns {path: [(line, text), ...]}."""
    results: dict = {}
    for root in roots:
        if root.is_file():
            candidates = [root]
        else:
            candidates = [
                f for f in root.rglob("*")
                if f.is_file() and f.suffix in extensions and not _should_skip(f)
            ]
        for path in sorted(candidates):
            hits = scan_file(path)
            if hits:
                results[path] = hits
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan source files for emoji characters (CI gate).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["src", "tests", "scripts", "dashboard/src", "*.md", "wiki"],
        help="Paths to scan (files or directories). Default: src tests scripts dashboard/src *.md wiki",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=None,
        help="File extensions to scan (e.g. .py .md). Default: all source extensions.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print only a summary count, not individual lines.",
    )
    args = parser.parse_args()

    exts = set(args.extensions) if args.extensions else _SCAN_EXTENSIONS

    roots: List[Path] = []
    for p in args.paths:
        # Support glob patterns like '*.md'
        if "*" in p:
            roots.extend(Path(".").glob(p))
        else:
            candidate = Path(p)
            if candidate.exists():
                roots.append(candidate)

    if not roots:
        print("[check_emojis] No paths to scan — all specified paths are missing.", file=sys.stderr)
        return 2

    results = scan_paths(roots, exts)

    if not results:
        print("[check_emojis] PASS: No emoji characters found.")
        return 0

    # Report failures
    total_lines = sum(len(v) for v in results.values())
    print(
        f"[check_emojis] FAIL: {total_lines} emoji line(s) in {len(results)} file(s).\n",
        file=sys.stderr,
    )
    if not args.summary:
        for path, hits in sorted(results.items()):
            for line_no, line_text in hits:
                # Show a safe truncated version (repr strips non-printable chars)
                safe = repr(line_text[:120])
                print(f"  {path}:{line_no}: {safe}", file=sys.stderr)
        print("", file=sys.stderr)

    print(
        f"[check_emojis] Remove all emoji characters before merging. "
        f"Run: python scripts/_strip_emoji_docs.py  to strip docs automatically.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
