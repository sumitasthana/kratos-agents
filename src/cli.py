#!/usr/bin/env python3
"""
Spark Execution Fingerprint CLI

Usage:
    python -m src.cli <event_log_path> [--output OUTPUT] [--format FORMAT] [--level LEVEL]
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.fingerprint import generate_fingerprint
from src.git_log_extractor import extract_git_log_artifacts
from src.agents.git_diff_dataflow import GitDiffDataFlowAgent


def _default_fingerprint_output_path(event_log_path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / "fingerprints"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    stem = event_log_path.stem
    return str(output_dir / f"fingerprint_{stem}_{timestamp}_{run_id}.json")


def _default_git_dataflow_run_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    base_dir = repo_root / "git_dataflow_runs"
    base_dir.mkdir(parents=True, exist_ok=True)

    return base_dir


def _default_git_dataflow_output_path(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    return base_dir / f"git_dataflow_{timestamp}_{run_id}.json"


def main():
    """Parse arguments and generate fingerprint."""
    known_commands = {"fingerprint", "git-log", "git-dataflow"}
    use_subcommands = len(sys.argv) > 1 and sys.argv[1] in known_commands

    if use_subcommands:
        parser = argparse.ArgumentParser(
            description="Spark Execution Fingerprint + Git Log Extractor"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        fp = subparsers.add_parser(
            "fingerprint", description="Generate Spark Execution Fingerprint from event log"
        )
        fp.add_argument(
            "event_log",
            help="Path to Spark event log file",
        )
        fp.add_argument(
            "--output",
            "-o",
            help="Output file path (default: auto-named in fingerprints/)",
            default=None,
        )
        fp.add_argument(
            "--format",
            "-f",
            choices=["json", "yaml", "markdown"],
            default="json",
            help="Output format (default: json)",
        )
        fp.add_argument(
            "--level",
            "-l",
            choices=["summary", "balanced", "detailed"],
            default="balanced",
            help="Detail level (default: balanced)",
        )
        fp.add_argument(
            "--no-evidence",
            action="store_true",
            help="Exclude evidence linking from output",
        )

        gl = subparsers.add_parser(
            "git-log", description="Extract Git commit + diff artifacts into JSON"
        )
        gl.add_argument(
            "repo_path",
            help="Path to a local Git repository",
        )
        gl.add_argument(
            "--extensions",
            "-e",
            help="Comma-separated list of file extensions to include (e.g. .py,.sql)",
            default=None,
        )
        gl.add_argument(
            "--keywords",
            "-k",
            help="Comma-separated list of keywords to search for in file contents",
            default=None,
        )
        gl.add_argument(
            "--output",
            "-o",
            help="Output file path (default: auto-named in current directory)",
            default=None,
        )

        gd = subparsers.add_parser(
            "git-dataflow", description="Extract dataflow patterns (reads/writes/joins/transformations) from git_artifacts JSON"
        )
        gd.add_argument(
            "--input",
            "-i",
            default=None,
            help="Path to a git_artifacts_*.json file",
        )
        gd.add_argument(
            "--latest",
            action="store_true",
            help="Use newest git_artifacts_*.json from --dir",
        )
        gd.add_argument(
            "--dir",
            "-d",
            default=".",
            help="Directory to search for git_artifacts_*.json when --latest is used (default: .)",
        )
        gd.add_argument(
            "--llm",
            action="store_true",
            help="Use LLM mode (requires provider API key env vars)",
        )
        gd.add_argument(
            "--output",
            "-o",
            default=None,
            help="Optional output file path to write the JSON result",
        )

        args = parser.parse_args()

        if args.command == "git-log":
            try:
                extensions = args.extensions.split(",") if args.extensions else None
                keywords = args.keywords.split(",") if args.keywords else None
                output_file = extract_git_log_artifacts(
                    args.repo_path,
                    extensions=extensions,
                    keywords=keywords,
                    output_path=args.output,
                )
                print("Git log artifacts extracted successfully")
                print(f"  Output: {output_file}")
                return 0
            except Exception as e:
                print(f"Error: {str(e)}", file=sys.stderr)
                return 1

        if args.command == "git-dataflow":
            try:
                print("[git-dataflow] Starting dataflow extraction...")
                input_path = None
                if args.input:
                    input_path = Path(args.input)
                elif args.latest:
                    search_dir = Path(args.dir)
                    print(f"[git-dataflow] Searching for latest git_artifacts_*.json in: {search_dir}")
                    candidates = sorted(
                        search_dir.glob("git_artifacts_*.json"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    input_path = candidates[0] if candidates else None

                if not input_path:
                    print(
                        "Provide --input PATH, or use --latest --dir DIR",
                        file=sys.stderr,
                    )
                    return 1

                if not input_path.exists():
                    print(f"Error: Input not found: {input_path}", file=sys.stderr)
                    return 1

                output_dir = _default_git_dataflow_run_dir()
                output_path = _default_git_dataflow_output_path(output_dir)
                print(f"[git-dataflow] Output file: {output_path}")

                print(f"[git-dataflow] Loading artifacts: {input_path}")
                payload = json.loads(input_path.read_text(encoding="utf-8"))
                agent = GitDiffDataFlowAgent()

                if args.llm:
                    print("[git-dataflow] Mode: LLM")
                    response = asyncio.run(agent.analyze(payload))
                else:
                    print("[git-dataflow] Mode: heuristic-only")
                    response = asyncio.run(agent.analyze_without_llm(payload))

                if not response.success:
                    print(f"Error: {response.error or 'analysis failed'}", file=sys.stderr)
                    return 1

                if args.output:
                    output_path = output_dir / Path(args.output).name

                output_path.write_text(response.explanation, encoding="utf-8")
                print(f"[git-dataflow] Wrote: {output_path}")
                print(f"[git-dataflow] Source: {input_path}")
                return 0
            except Exception as e:
                print(f"Error: {str(e)}", file=sys.stderr)
                return 1

        # fingerprint subcommand
        event_log_path = Path(args.event_log)
        if not event_log_path.exists():
            print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
            return 1

        try:
            output_path = args.output or _default_fingerprint_output_path(event_log_path)
            fingerprint = generate_fingerprint(
                str(event_log_path),
                output_format=args.format,
                output_path=output_path,
                include_evidence=not args.no_evidence,
                detail_level=args.level,
            )
            print("Fingerprint generated successfully")
            print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
            print(f"  Execution Class: {fingerprint.execution_class}")
            print(f"  Output: {output_path}")
            return 0
        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            return 1

    # Legacy mode: original CLI contract
    parser = argparse.ArgumentParser(
        description="Generate Spark Execution Fingerprint from event log"
    )

    parser.add_argument(
        "event_log",
        help="Path to Spark event log file",
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: auto-named in fingerprints/)",
        default=None,
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format (default: json)",
    )

    parser.add_argument(
        "--level",
        "-l",
        choices=["summary", "balanced", "detailed"],
        default="balanced",
        help="Detail level (default: balanced)",
    )

    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Exclude evidence linking from output",
    )

    args = parser.parse_args()

    event_log_path = Path(args.event_log)
    if not event_log_path.exists():
        print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
        return 1

    try:
        output_path = args.output or _default_fingerprint_output_path(event_log_path)
        fingerprint = generate_fingerprint(
            str(event_log_path),
            output_format=args.format,
            output_path=output_path,
            include_evidence=not args.no_evidence,
            detail_level=args.level,
        )
        print("Fingerprint generated successfully")
        print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
        print(f"  Execution Class: {fingerprint.execution_class}")
        print(f"  Output: {output_path}")
        return 0
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
