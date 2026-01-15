#!/usr/bin/env python3
"""
Spark Execution Fingerprint CLI

Usage:
    python -m src.cli <event_log_path> [--output OUTPUT] [--format FORMAT] [--level LEVEL]
"""

import argparse
import sys
from pathlib import Path

from src.fingerprint import generate_fingerprint


def main():
    """Parse arguments and generate fingerprint."""
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
        help="Output file path (default: fingerprint.json)",
        default="fingerprint.json",
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

    # Validate input
    event_log_path = Path(args.event_log)
    if not event_log_path.exists():
        print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
        sys.exit(1)

    # Generate fingerprint
    try:
        fingerprint = generate_fingerprint(
            str(event_log_path),
            output_format=args.format,
            output_path=args.output,
            include_evidence=not args.no_evidence,
            detail_level=args.level,
        )
        print("Fingerprint generated successfully")
        print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
        print(f"  Execution Class: {fingerprint.execution_class}")
        print(f"  Output: {args.output}")
        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
