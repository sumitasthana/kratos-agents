# #!/usr/bin/env python3
# """
# Spark Execution Fingerprint CLI

# Usage:
#     python -m src.cli <event_log_path> [--output OUTPUT] [--format FORMAT] [--level LEVEL]
# """

# import argparse
# import asyncio
# import json
# import subprocess
# import sys
# import webbrowser
# from datetime import datetime, timezone
# from pathlib import Path
# from urllib.parse import urlparse
# from uuid import uuid4

# from src.fingerprint import generate_fingerprint
# from src.git_log_extractor import extract_git_log_artifacts
# from src.agents.git_diff_dataflow import GitDiffDataFlowAgent
# from src.orchestrator import SmartOrchestrator
# from src.schemas import ExecutionFingerprint


# def _repo_root() -> Path:
#     return Path(__file__).resolve().parents[1]


# def _write_run_manifest(
#     *,
#     run_id: str,
#     command: str,
#     inputs: dict,
#     artifacts: dict,
#     highlights: list[str] | None = None,
#     success: bool = True,
# ) -> Path:
#     repo_root = _repo_root()
#     runs_root = repo_root / "runs"
#     manifests_dir = runs_root / "run_manifests"
#     manifests_dir.mkdir(parents=True, exist_ok=True)

#     created_at = datetime.now(timezone.utc).isoformat()

#     def _to_repo_relative(p: str | Path | None) -> str | None:
#         if not p:
#             return None
#         pp = Path(p)
#         if not pp.is_absolute():
#             return str(pp).replace("\\", "/")
#         try:
#             return str(pp.relative_to(repo_root)).replace("\\", "/")
#         except Exception:
#             return str(pp).replace("\\", "/")

#     manifest = {
#         "run_id": run_id,
#         "created_at": created_at,
#         "command": command,
#         "inputs": inputs or {},
#         "artifacts": {k: _to_repo_relative(v) for k, v in (artifacts or {}).items()},
#         "summary": {
#             "success": bool(success),
#             "highlights": highlights or [],
#         },
#     }

#     manifest_path = manifests_dir / f"{run_id}.json"
#     manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

#     latest_path = runs_root / "latest.json"
#     latest_payload = {
#         "run_id": run_id,
#         "manifest_path": _to_repo_relative(manifest_path),
#         "created_at": created_at,
#         "command": command,
#     }
#     latest_path.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")

#     return manifest_path


# def _best_effort_open_dashboard(url: str = "http://localhost:4173") -> None:
#     try:
#         webbrowser.open(url)
#     except Exception:
#         pass


# def _best_effort_start_dashboard_server() -> None:
#     """Start dashboard server if it looks installed. Never hard-fail the CLI."""
#     try:
#         repo_root = _repo_root()
#         dashboard_dir = repo_root / "dashboard"
#         server_js = dashboard_dir / "server.js"
#         node_modules = dashboard_dir / "node_modules"
#         dist_dir = dashboard_dir / "dist"
#         if not server_js.exists():
#             return
#         # Only attempt auto-start if deps are installed.
#         if not node_modules.exists():
#             return
#         # Serving UI requires build output.
#         if not dist_dir.exists():
#             return

#         subprocess.Popen(
#             ["node", str(server_js)],
#             cwd=str(dashboard_dir),
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL,
#             creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
#         )
#     except Exception:
#         return


# def _default_fingerprint_output_path(event_log_path: Path) -> str:
#     repo_root = _repo_root()
#     output_dir = repo_root / "runs" / "fingerprints"
#     output_dir.mkdir(parents=True, exist_ok=True)

#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
#     run_id = uuid4().hex[:8]
#     stem = event_log_path.stem
#     return str(output_dir / f"fingerprint_{stem}_{timestamp}_{run_id}.json")


# def _default_cloned_repos_dir() -> Path:
#     repo_root = _repo_root()
#     base_dir = repo_root / "runs" / "cloned_repos"
#     base_dir.mkdir(parents=True, exist_ok=True)
#     return base_dir


# def _repo_name_from_url(repo_url: str) -> str:
#     # Best-effort to create a readable folder name.
#     parsed = urlparse(repo_url)
#     path = parsed.path.strip("/")
#     name = path.split("/")[-1] if path else "repo"
#     if name.lower().endswith(".git"):
#         name = name[:-4]
#     return name or "repo"


# def _default_clone_target_dir(base_dir: Path, repo_url: str) -> Path:
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
#     run_id = uuid4().hex[:8]
#     repo_name = _repo_name_from_url(repo_url)
#     return base_dir / f"{repo_name}_{timestamp}_{run_id}"


# def _default_git_artifacts_dir() -> Path:
#     repo_root = _repo_root()
#     base_dir = repo_root / "runs" / "git_artifacts"
#     base_dir.mkdir(parents=True, exist_ok=True)
#     return base_dir


# def _default_git_artifacts_output_path(base_dir: Path, repo_path: str) -> Path:
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
#     run_id = uuid4().hex[:8]
#     repo_name = Path(repo_path).resolve().name
#     return base_dir / f"git_artifacts_{repo_name}_{timestamp}_{run_id}.json"


# def _default_git_dataflow_run_dir() -> Path:
#     repo_root = _repo_root()
#     base_dir = repo_root / "runs" / "git_dataflow"
#     base_dir.mkdir(parents=True, exist_ok=True)
#     return base_dir


# def _default_git_dataflow_output_path(base_dir: Path) -> Path:
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
#     run_id = uuid4().hex[:8]
#     return base_dir / f"git_dataflow_{timestamp}_{run_id}.json"


# def _default_orchestrator_output_dir() -> Path:
#     repo_root = _repo_root()
#     base_dir = repo_root / "runs" / "orchestrator"
#     base_dir.mkdir(parents=True, exist_ok=True)
#     return base_dir


# def _default_orchestrator_output_path(base_dir: Path) -> Path:
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
#     run_id = uuid4().hex[:8]
#     return base_dir / f"orchestrator_{timestamp}_{run_id}.json"


# def main():
#     """Parse arguments and generate fingerprint."""
#     known_commands = {"fingerprint", "git-clone", "git-log", "git-dataflow", "orchestrate", "lineage-extract"}
#     use_subcommands = len(sys.argv) > 1 and sys.argv[1] in known_commands

#     if use_subcommands:
#         parser = argparse.ArgumentParser(
#             description="Spark Execution Fingerprint + Git Log Extractor"
#         )
#         subparsers = parser.add_subparsers(dest="command", required=True)

#         fp = subparsers.add_parser(
#             "fingerprint", description="Generate Spark Execution Fingerprint from event log"
#         )
#         fp.add_argument(
#             "event_log",
#             help="Path to Spark event log file",
#         )
#         fp.add_argument(
#             "--output",
#             "-o",
#             help="Output file path (default: auto-named in runs/fingerprints/)",
#             default=None,
#         )
#         fp.add_argument(
#             "--format",
#             "-f",
#             choices=["json", "yaml", "markdown"],
#             default="json",
#             help="Output format (default: json)",
#         )
#         fp.add_argument(
#             "--level",
#             "-l",
#             choices=["summary", "balanced", "detailed"],
#             default="balanced",
#             help="Detail level (default: balanced)",
#         )
#         fp.add_argument(
#             "--no-evidence",
#             action="store_true",
#             help="Exclude evidence linking from output",
#         )

#         gl = subparsers.add_parser(
#             "git-log", description="Extract Git commit + diff artifacts into JSON"
#         )
#         gl.add_argument(
#             "repo_path",
#             help="Path to a local Git repository",
#         )
#         gl.add_argument(
#             "--extensions",
#             "-e",
#             help="Comma-separated list of file extensions to include (e.g. .py,.sql)",
#             default=None,
#         )
#         gl.add_argument(
#             "--keywords",
#             "-k",
#             help="Comma-separated list of keywords to search for in file contents",
#             default=None,
#         )
#         gl.add_argument(
#             "--output",
#             "-o",
#             help="Output file path (default: auto-named in runs/git_artifacts/)",
#             default=None,
#         )

#         gc = subparsers.add_parser(
#             "git-clone", description="Clone a remote git repo into cloned_repos/"
#         )
#         gc.add_argument(
#             "repo_url",
#             help="Remote git URL (e.g. https://github.com/org/repo.git)",
#         )
#         gc.add_argument(
#             "--dest",
#             "-d",
#             default=None,
#             help="Optional destination folder name under cloned_repos/",
#         )

#         gd = subparsers.add_parser(
#             "git-dataflow", description="Extract dataflow patterns (reads/writes/joins/transformations) from git_artifacts JSON"
#         )
#         gd.add_argument(
#             "--input",
#             "-i",
#             default=None,
#             help="Path to a git_artifacts_*.json file",
#         )
#         gd.add_argument(
#             "--latest",
#             action="store_true",
#             help="Use newest git_artifacts_*.json from --dir",
#         )
#         gd.add_argument(
#             "--dir",
#             "-d",
#             default=".",
#             help="Directory to search for git_artifacts_*.json when --latest is used (default: .)",
#         )
#         gd.add_argument(
#             "--llm",
#             action="store_true",
#             help="Use LLM mode (requires provider API key env vars)",
#         )
#         gd.add_argument(
#             "--include-docs",
#             action="store_true",
#             help="Include documentation files (e.g., README.md) in dataflow extraction (default: excluded)",
#         )
#         gd.add_argument(
#             "--output",
#             "-o",
#             default=None,
#             help="Optional output file path to write the JSON result",
#         )

#         orch = subparsers.add_parser(
#             "orchestrate", description="Run SmartOrchestrator (Query Understanding + Root Cause) on a fingerprint with a natural language question"
#         )
#         orch.add_argument(
#             "--fingerprint",
#             "-f",
#             default=None,
#             help="Path to an existing fingerprint_*.json",
#         )
#         orch.add_argument(
#             "--from-log",
#             default=None,
#             help="Path to Spark event log (will generate fingerprint first)",
#         )
#         orch.add_argument(
#             "--query",
#             "-q",
#             required=True,
#             help="Question to ask the orchestrator (e.g. 'Why is my Spark job slow?')",
#         )
#         orch.add_argument(
#             "--output",
#             "-o",
#             default=None,
#             help="Optional output filename (saved under runs/orchestrator/)",
#         )

#         lineage = subparsers.add_parser(
#             "lineage-extract",
#             description="Extract data lineage from Spark ETL scripts using AI"
#         )
#         lineage.add_argument(
#             "--scripts",
#             "-s",
#             nargs="+",
#             default=None,
#             help="Path(s) to ETL script files (.py, .sql)"
#         )
#         lineage.add_argument(
#             "--folder",
#             "-f",
#             default=None,
#             help="Folder containing ETL scripts (analyzes all .py and .sql files)"
#         )
#         lineage.add_argument(
#             "--output",
#             "-o",
#             default=None,
#             help="Output JSON path (default: runs/lineage/lineage_*.json)"
#         )
#         lineage.add_argument(
#             "--trace-table",
#             default=None,
#             help="Table name to trace column lineage for"
#         )
#         lineage.add_argument(
#             "--trace-column",
#             default=None,
#             help="Column name to trace (requires --trace-table)"
#         )
#         lineage.add_argument(
#             "--trace-direction",
#             choices=["upstream", "downstream"],
#             default="upstream",
#             help="Trace direction (default: upstream)"
#         )
#         lineage.add_argument(
#             "--view",
#             action="store_true",
#             help="Open the local dashboard after completion (best-effort)"
#         )

#         args = parser.parse_args()

#         if args.command == "git-log":
#             try:
#                 extensions = args.extensions.split(",") if args.extensions else None
#                 keywords = args.keywords.split(",") if args.keywords else None

#                 output_path = args.output
#                 if output_path is None:
#                     out_dir = _default_git_artifacts_dir()
#                     output_path = str(_default_git_artifacts_output_path(out_dir, args.repo_path))

#                 output_file = extract_git_log_artifacts(
#                     args.repo_path,
#                     extensions=extensions,
#                     keywords=keywords,
#                     output_path=output_path,
#                 )
#                 print("Git log artifacts extracted successfully")
#                 print(f"  Output: {output_file}")
#                 return 0
#             except Exception as e:
#                 print(f"Error: {str(e)}", file=sys.stderr)
#                 return 1

#         if args.command == "git-clone":
#             try:
#                 base_dir = _default_cloned_repos_dir()
#                 target_dir = base_dir / args.dest if args.dest else _default_clone_target_dir(base_dir, args.repo_url)

#                 print("[git-clone] Cloning...")
#                 print(f"[git-clone] Repo: {args.repo_url}")
#                 print(f"[git-clone] Dest: {target_dir}")

#                 if target_dir.exists() and any(target_dir.iterdir()):
#                     print(f"Error: Destination is not empty: {target_dir}", file=sys.stderr)
#                     return 1

#                 target_dir.parent.mkdir(parents=True, exist_ok=True)
#                 subprocess.run(
#                     ["git", "clone", args.repo_url, str(target_dir)],
#                     check=True,
#                     stdout=sys.stdout,
#                     stderr=sys.stderr,
#                 )

#                 print("[git-clone] Done")
#                 print(f"[git-clone] Local path: {target_dir}")
#                 return 0
#             except subprocess.CalledProcessError as e:
#                 print(f"Error: git clone failed ({e})", file=sys.stderr)
#                 return 1
#             except Exception as e:
#                 print(f"Error: {str(e)}", file=sys.stderr)
#                 return 1

#         if args.command == "git-dataflow":
#             try:
#                 print("[git-dataflow] Starting dataflow extraction...")
#                 input_path = None
#                 if args.input:
#                     input_path = Path(args.input)
#                 elif args.latest:
#                     search_dir = Path(args.dir)
#                     print(f"[git-dataflow] Searching for latest git_artifacts_*.json in: {search_dir}")
#                     candidates = sorted(
#                         search_dir.glob("git_artifacts_*.json"),
#                         key=lambda p: p.stat().st_mtime,
#                         reverse=True,
#                     )
#                     input_path = candidates[0] if candidates else None

#                 if not input_path:
#                     print(
#                         "Provide --input PATH, or use --latest --dir DIR",
#                         file=sys.stderr,
#                     )
#                     return 1

#                 if not input_path.exists():
#                     print(f"Error: Input not found: {input_path}", file=sys.stderr)
#                     return 1

#                 output_dir = _default_git_dataflow_run_dir()
#                 output_path = _default_git_dataflow_output_path(output_dir)
#                 print(f"[git-dataflow] Output file: {output_path}")

#                 print(f"[git-dataflow] Loading artifacts: {input_path}")
#                 payload = json.loads(input_path.read_text(encoding="utf-8"))
#                 agent = GitDiffDataFlowAgent()
#                 agent.include_docs = bool(getattr(args, "include_docs", False))

#                 try:
#                     plan_steps = agent.plan(payload, always_use_llm=bool(args.llm))
#                     if plan_steps:
#                         print(f"[plan] {agent.agent_name}")
#                         for step in plan_steps:
#                             print(f"[plan] - {step}")
#                 except Exception:
#                     pass

#                 if args.llm:
#                     print("[git-dataflow] Mode: LLM")
#                     response = asyncio.run(agent.analyze(payload))
#                 else:
#                     print("[git-dataflow] Mode: heuristic-only")
#                     response = asyncio.run(agent.analyze_without_llm(payload))

#                 if not response.success:
#                     print(f"Error: {response.error or 'analysis failed'}", file=sys.stderr)
#                     return 1

#                 if args.output:
#                     output_path = output_dir / Path(args.output).name

#                 output_path.write_text(response.explanation, encoding="utf-8")
#                 print(f"[git-dataflow] Wrote: {output_path}")
#                 print(f"[git-dataflow] Source: {input_path}")

#                 run_id = uuid4().hex[:12]
#                 highlights = list(response.key_findings or [])
#                 _write_run_manifest(
#                     run_id=run_id,
#                     command="git-dataflow",
#                     inputs={
#                         "input": str(input_path),
#                         "latest": bool(getattr(args, "latest", False)),
#                         "dir": str(getattr(args, "dir", "")) if getattr(args, "dir", None) else None,
#                         "llm": bool(getattr(args, "llm", False)),
#                         "include_docs": bool(getattr(args, "include_docs", False)),
#                     },
#                     artifacts={
#                         "git_dataflow_json": str(output_path),
#                         "git_artifacts_json": str(input_path),
#                     },
#                     highlights=highlights,
#                     success=True,
#                 )

#                 return 0
#             except Exception as e:
#                 print(f"Error: {str(e)}", file=sys.stderr)
#                 return 1

#         if args.command == "lineage-extract":
#             try:
#                 from src.agents.lineage_extraction import LineageExtractionAgent
                
#                 print("[lineage-extract] Starting lineage extraction...")
                
#                 # Determine script paths
#                 script_paths = []
#                 if args.folder:
#                     folder_path = Path(args.folder)
#                     if not folder_path.exists():
#                         print(f"Error: Folder not found: {folder_path}", file=sys.stderr)
#                         return 1
#                     if not folder_path.is_dir():
#                         print(f"Error: Not a directory: {folder_path}", file=sys.stderr)
#                         return 1
                    
#                     # Find all .py and .sql files
#                     script_paths = sorted([
#                         str(p) for p in folder_path.glob("**/*.py")
#                     ] + [
#                         str(p) for p in folder_path.glob("**/*.sql")
#                     ])
                    
#                     if not script_paths:
#                         print(f"Error: No .py or .sql files found in: {folder_path}", file=sys.stderr)
#                         return 1
                    
#                     print(f"[lineage-extract] Found {len(script_paths)} script(s) in folder: {folder_path}")
#                     for sp in script_paths:
#                         print(f"  - {sp}")
                
#                 elif args.scripts:
#                     script_paths = args.scripts
#                 else:
#                     print("Error: Provide either --scripts or --folder", file=sys.stderr)
#                     return 1
                
#                 output_dir = Path(__file__).resolve().parents[1] / "runs" / "lineage"
#                 output_dir.mkdir(parents=True, exist_ok=True)
#                 output_path = output_dir / f"lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
#                 if args.output:
#                     output_path = Path(args.output)
#                     output_path.parent.mkdir(parents=True, exist_ok=True)
                
#                 agent = LineageExtractionAgent()
                
#                 # Print plan
#                 try:
#                     plan_steps = agent.plan(
#                         {},
#                         script_paths=args.scripts,
#                         trace_table=args.trace_table,
#                         trace_column=args.trace_column
#                     )
#                     if plan_steps:
#                         print(f"[plan] {agent.agent_name}")
#                         for step in plan_steps:
#                             print(f"[plan] - {step}")
#                 except Exception:
#                     pass
                
#                 # Run extraction
#                 response = asyncio.run(agent.analyze(
#                     {},
#                     script_paths=script_paths,
#                     output_path=str(output_path),
#                     trace_table=args.trace_table,
#                     trace_column=args.trace_column,
#                     trace_direction=args.trace_direction
#                 ))
                
#                 if not response.success:
#                     print(f"Error: {response.error}", file=sys.stderr)
#                     return 1
                
#                 print(f"[lineage-extract] Success: {response.summary}")
#                 print(f"[lineage-extract] Output: {output_path}")
                
#                 if response.key_findings:
#                     print("[lineage-extract] Findings:")
#                     for finding in response.key_findings:
#                         print(f"  - {finding}")

#                 # Write dashboard manifest + optionally open dashboard
#                 run_id = uuid4().hex[:12]
#                 highlights = list(response.key_findings or [])
#                 _write_run_manifest(
#                     run_id=run_id,
#                     command="lineage-extract",
#                     inputs={
#                         "folder": str(args.folder) if args.folder else None,
#                         "scripts": script_paths,
#                         "trace_table": args.trace_table,
#                         "trace_column": args.trace_column,
#                         "trace_direction": args.trace_direction,
#                     },
#                     artifacts={
#                         "lineage_json": str(output_path),
#                     },
#                     highlights=highlights,
#                     success=True,
#                 )

#                 if bool(getattr(args, "view", False)):
#                     _best_effort_start_dashboard_server()
#                     _best_effort_open_dashboard("http://localhost:4173")
                
#                 return 0
                
#             except Exception as e:
#                 print(f"Error: {str(e)}", file=sys.stderr)
#                 return 1

#         if args.command == "orchestrate":
#             try:
#                 print("[orchestrate] Starting orchestrator...")

#                 if (args.fingerprint is None) == (args.from_log is None):
#                     print(
#                         "Provide exactly one of --fingerprint or --from-log",
#                         file=sys.stderr,
#                     )
#                     return 1

#                 if args.fingerprint:
#                     fp_path = Path(args.fingerprint)
#                     if not fp_path.exists():
#                         print(f"Error: Fingerprint not found: {fp_path}", file=sys.stderr)
#                         return 1
#                     print(f"[orchestrate] Loading fingerprint: {fp_path}")
#                     fp_payload = json.loads(fp_path.read_text(encoding="utf-8"))
#                     fingerprint = ExecutionFingerprint.model_validate(fp_payload)
#                 else:
#                     event_log_path = Path(args.from_log)
#                     if not event_log_path.exists():
#                         print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
#                         return 1
#                     fp_out = _default_fingerprint_output_path(event_log_path)
#                     print(f"[orchestrate] Generating fingerprint from log: {event_log_path}")
#                     fingerprint = generate_fingerprint(
#                         str(event_log_path),
#                         output_format="json",
#                         output_path=fp_out,
#                         include_evidence=True,
#                         detail_level="balanced",
#                     )
#                     print(f"[orchestrate] Fingerprint written: {fp_out}")

#                 out_dir = _default_orchestrator_output_dir()
#                 out_path = _default_orchestrator_output_path(out_dir)
#                 if args.output:
#                     out_path = out_dir / Path(args.output).name

#                 print(f"[orchestrate] Query: {args.query}")
#                 result = asyncio.run(SmartOrchestrator(fingerprint).solve_problem(args.query))
#                 out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

#                 print(f"[orchestrate] Wrote: {out_path}")

#                 run_id = uuid4().hex[:12]
#                 _write_run_manifest(
#                     run_id=run_id,
#                     command="orchestrate",
#                     inputs={
#                         "query": args.query,
#                         "fingerprint": str(args.fingerprint) if getattr(args, "fingerprint", None) else None,
#                         "from_log": str(args.from_log) if getattr(args, "from_log", None) else None,
#                         "output": str(out_path),
#                     },
#                     artifacts={
#                         "orchestrator_json": str(out_path),
#                     },
#                     highlights=[],
#                     success=True,
#                 )

#                 return 0
#             except Exception as e:
#                 print(f"Error: {str(e)}", file=sys.stderr)
#                 return 1

#         # fingerprint subcommand
#         event_log_path = Path(args.event_log)
#         if not event_log_path.exists():
#             print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
#             return 1

#         try:
#             output_path = args.output or _default_fingerprint_output_path(event_log_path)
#             fingerprint = generate_fingerprint(
#                 str(event_log_path),
#                 output_format=args.format,
#                 output_path=output_path,
#                 include_evidence=not args.no_evidence,
#                 detail_level=args.level,
#             )
#             print("Fingerprint generated successfully")
#             print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
#             print(f"  Execution Class: {fingerprint.execution_class}")
#             print(f"  Output: {output_path}")
#             return 0
#         except Exception as e:
#             print(f"Error: {str(e)}", file=sys.stderr)
#             return 1

#     # Legacy mode: original CLI contract
#     parser = argparse.ArgumentParser(
#         description="Generate Spark Execution Fingerprint from event log"
#     )

#     parser.add_argument(
#         "event_log",
#         help="Path to Spark event log file",
#     )

#     parser.add_argument(
#         "--output",
#         "-o",
#         help="Output file path (default: auto-named in runs/fingerprints/)",
#         default=None,
#     )

#     parser.add_argument(
#         "--format",
#         "-f",
#         choices=["json", "yaml", "markdown"],
#         default="json",
#         help="Output format (default: json)",
#     )

#     parser.add_argument(
#         "--level",
#         "-l",
#         choices=["summary", "balanced", "detailed"],
#         default="balanced",
#         help="Detail level (default: balanced)",
#     )

#     parser.add_argument(
#         "--no-evidence",
#         action="store_true",
#         help="Exclude evidence linking from output",
#     )

#     args = parser.parse_args()

#     event_log_path = Path(args.event_log)
#     if not event_log_path.exists():
#         print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
#         return 1

#     try:
#         output_path = args.output or _default_fingerprint_output_path(event_log_path)
#         fingerprint = generate_fingerprint(
#             str(event_log_path),
#             output_format=args.format,
#             output_path=output_path,
#             include_evidence=not args.no_evidence,
#             detail_level=args.level,
#         )
#         print("Fingerprint generated successfully")
#         print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
#         print(f"  Execution Class: {fingerprint.execution_class}")
#         print(f"  Output: {output_path}")
#         return 0
#     except Exception as e:
#         print(f"Error: {str(e)}", file=sys.stderr)
#         return 1


# if __name__ == "__main__":
#     sys.exit(main())
#!/usr/bin/env python3
"""
Spark Execution Fingerprint CLI

Usage:
    python -m src.cli <event_log_path> [--output OUTPUT] [--format FORMAT] [--level LEVEL]
"""

import argparse
import asyncio
import json
import subprocess
import sys
import traceback
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from src.fingerprint import generate_fingerprint
from src.git_log_extractor import extract_git_log_artifacts
from src.agents.git_diff_dataflow import GitDiffDataFlowAgent
from src.orchestrator import SmartOrchestrator
from src.schemas import ExecutionFingerprint


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_run_manifest(
    *,
    run_id: str,
    command: str,
    inputs: dict,
    artifacts: dict,
    highlights: list[str] | None = None,
    success: bool = True,
) -> Path:
    repo_root = _repo_root()
    runs_root = repo_root / "runs"
    manifests_dir = runs_root / "run_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc).isoformat()

    def _to_repo_relative(p: str | Path | None) -> str | None:
        if not p:
            return None
        pp = Path(p)
        if not pp.is_absolute():
            return str(pp).replace("\\", "/")
        try:
            return str(pp.relative_to(repo_root)).replace("\\", "/")
        except Exception:
            return str(pp).replace("\\", "/")

    manifest = {
        "run_id": run_id,
        "created_at": created_at,
        "command": command,
        "inputs": inputs or {},
        "artifacts": {k: _to_repo_relative(v) for k, v in (artifacts or {}).items()},
        "summary": {
            "success": bool(success),
            "highlights": highlights or [],
        },
    }

    manifest_path = manifests_dir / f"{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    latest_path = runs_root / "latest.json"
    latest_payload = {
        "run_id": run_id,
        "manifest_path": _to_repo_relative(manifest_path),
        "created_at": created_at,
        "command": command,
    }
    latest_path.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
    return manifest_path


def _best_effort_open_dashboard(url: str = "http://localhost:4173") -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def _best_effort_start_dashboard_server() -> None:
    try:
        repo_root = _repo_root()
        dashboard_dir = repo_root / "dashboard"
        if not (dashboard_dir / "server.js").exists():
            return
        if not (dashboard_dir / "node_modules").exists():
            return
        if not (dashboard_dir / "dist").exists():
            return
        subprocess.Popen(
            ["node", str(dashboard_dir / "server.js")],
            cwd=str(dashboard_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception:
        return


# ─────────────────────────────────────────────────────────────────────────────
# Default output path helpers
# ─────────────────────────────────────────────────────────────────────────────

def _default_fingerprint_output_path(event_log_path: Path) -> str:
    repo_root = _repo_root()
    output_dir = repo_root / "runs" / "fingerprints"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    stem = event_log_path.stem
    return str(output_dir / f"fingerprint_{stem}_{timestamp}_{run_id}.json")


def _default_cloned_repos_dir() -> Path:
    base_dir = _repo_root() / "runs" / "cloned_repos"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/")
    name = path.split("/")[-1] if path else "repo"
    if name.lower().endswith(".git"):
        name = name[:-4]
    return name or "repo"


def _default_clone_target_dir(base_dir: Path, repo_url: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    return base_dir / f"{_repo_name_from_url(repo_url)}_{timestamp}_{run_id}"


def _default_git_artifacts_dir() -> Path:
    base_dir = _repo_root() / "runs" / "git_artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _default_git_artifacts_output_path(base_dir: Path, repo_path: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    repo_name = Path(repo_path).resolve().name
    return base_dir / f"git_artifacts_{repo_name}_{timestamp}_{run_id}.json"


def _default_git_dataflow_run_dir() -> Path:
    base_dir = _repo_root() / "runs" / "git_dataflow"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _default_git_dataflow_output_path(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    return base_dir / f"git_dataflow_{timestamp}_{run_id}.json"


def _default_orchestrator_output_dir() -> Path:
    base_dir = _repo_root() / "runs" / "orchestrator"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _default_orchestrator_output_path(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    return base_dir / f"orchestrator_{timestamp}_{run_id}.json"


def _default_rca_output_dir() -> Path:
    base_dir = _repo_root() / "runs" / "rca"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _default_rca_output_path(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    return base_dir / f"rca_{timestamp}_{run_id}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Result serialization helper  ← KEY FIX
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_result(result) -> str:
    """
    Safely serialize an AnalysisResult (or any Pydantic model / dict) to a
    JSON string.  Falls back to a plain dict representation so the file is
    always written even if model_dump_json raises.
    """
    # Pydantic v2
    if hasattr(result, "model_dump"):
        try:
            return json.dumps(result.model_dump(mode="json"), indent=2)
        except Exception:
            pass
    # Pydantic v1
    if hasattr(result, "dict"):
        try:
            return json.dumps(result.dict(), indent=2)
        except Exception:
            pass
    # Already a dict
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    # Last resort
    return json.dumps({"raw": str(result)}, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────────────

def main():
    known_commands = {
        "fingerprint", "git-clone", "git-log", "git-dataflow",
        "orchestrate", "lineage-extract", "rca",
    }
    use_subcommands = len(sys.argv) > 1 and sys.argv[1] in known_commands

    if use_subcommands:
        parser = argparse.ArgumentParser(
            description="Spark Execution Fingerprint + Git Log Extractor + GRC RCA"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        # ── fingerprint ──────────────────────────────────────────────────────
        fp = subparsers.add_parser("fingerprint", description="Generate Spark Execution Fingerprint from event log")
        fp.add_argument("event_log", help="Path to Spark event log file")
        fp.add_argument("--output", "-o", default=None, help="Output file path")
        fp.add_argument("--format", "-f", choices=["json", "yaml", "markdown"], default="json")
        fp.add_argument("--level", "-l", choices=["summary", "balanced", "detailed"], default="balanced")
        fp.add_argument("--no-evidence", action="store_true")

        # ── git-log ──────────────────────────────────────────────────────────
        gl = subparsers.add_parser("git-log", description="Extract Git commit + diff artifacts into JSON")
        gl.add_argument("repo_path", help="Path to a local Git repository")
        gl.add_argument("--extensions", "-e", default=None)
        gl.add_argument("--keywords", "-k", default=None)
        gl.add_argument("--output", "-o", default=None)

        # ── git-clone ─────────────────────────────────────────────────────────
        gc = subparsers.add_parser("git-clone", description="Clone a remote git repo into cloned_repos/")
        gc.add_argument("repo_url")
        gc.add_argument("--dest", "-d", default=None)

        # ── git-dataflow ──────────────────────────────────────────────────────
        gd = subparsers.add_parser("git-dataflow", description="Extract dataflow patterns from git_artifacts JSON")
        gd.add_argument("--input", "-i", default=None)
        gd.add_argument("--latest", action="store_true")
        gd.add_argument("--dir", "-d", default=".")
        gd.add_argument("--llm", action="store_true")
        gd.add_argument("--include-docs", action="store_true")
        gd.add_argument("--output", "-o", default=None)

        # ── orchestrate ───────────────────────────────────────────────────────
        orch = subparsers.add_parser("orchestrate", description="Run SmartOrchestrator on a fingerprint")
        orch.add_argument("--fingerprint", "-f", default=None)
        orch.add_argument("--from-log", default=None)
        orch.add_argument("--query", "-q", required=True)
        orch.add_argument("--output", "-o", default=None)

        # ── lineage-extract ───────────────────────────────────────────────────
        lineage = subparsers.add_parser("lineage-extract", description="Extract data lineage from Spark ETL scripts")
        lineage.add_argument("--scripts", "-s", nargs="+", default=None)
        lineage.add_argument("--folder", "-f", default=None)
        lineage.add_argument("--output", "-o", default=None)
        lineage.add_argument("--trace-table", default=None)
        lineage.add_argument("--trace-column", default=None)
        lineage.add_argument("--trace-direction", choices=["upstream", "downstream"], default="upstream")
        lineage.add_argument("--view", action="store_true")

        # ── rca ───────────────────────────────────────────────────────────────
        rca = subparsers.add_parser("rca", description="Run Root Cause Analysis (GRC Compliance or Spark Performance)")
        rca.add_argument("--fingerprint", "-f", default=None)
        rca.add_argument("--from-log", default=None)
        rca.add_argument("--mode", "-m", choices=["spark", "grc"], default="spark")
        rca.add_argument("--incident-type", "-i",
                         choices=["audit_finding", "regulatory_issue", "data_quality_breach",
                                  "control_failure", "production_incident"],
                         default=None)
        rca.add_argument("--incident-id", default=None)
        rca.add_argument("--focus", nargs="+", default=None)
        rca.add_argument("--output", "-o", default=None)
        rca.add_argument("--view", action="store_true")

        args = parser.parse_args()

        # ── git-log handler ───────────────────────────────────────────────────
        if args.command == "git-log":
            try:
                extensions = args.extensions.split(",") if args.extensions else None
                keywords = args.keywords.split(",") if args.keywords else None
                output_path = args.output or str(
                    _default_git_artifacts_output_path(_default_git_artifacts_dir(), args.repo_path)
                )
                output_file = extract_git_log_artifacts(
                    args.repo_path, extensions=extensions, keywords=keywords, output_path=output_path
                )
                print("Git log artifacts extracted successfully")
                print(f"  Output: {output_file}")
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

        # ── git-clone handler ─────────────────────────────────────────────────
        if args.command == "git-clone":
            try:
                base_dir = _default_cloned_repos_dir()
                target_dir = base_dir / args.dest if args.dest else _default_clone_target_dir(base_dir, args.repo_url)
                print(f"[git-clone] Repo: {args.repo_url}")
                print(f"[git-clone] Dest: {target_dir}")
                if target_dir.exists() and any(target_dir.iterdir()):
                    print(f"Error: Destination not empty: {target_dir}", file=sys.stderr)
                    return 1
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "clone", args.repo_url, str(target_dir)], check=True)
                print(f"[git-clone] Done: {target_dir}")
                return 0
            except subprocess.CalledProcessError as e:
                print(f"Error: git clone failed: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

        # ── git-dataflow handler ──────────────────────────────────────────────
        if args.command == "git-dataflow":
            try:
                print("[git-dataflow] Starting...")
                input_path = None
                if args.input:
                    input_path = Path(args.input)
                elif args.latest:
                    search_dir = Path(args.dir)
                    candidates = sorted(search_dir.glob("git_artifacts_*.json"),
                                        key=lambda p: p.stat().st_mtime, reverse=True)
                    input_path = candidates[0] if candidates else None

                if not input_path or not input_path.exists():
                    print("Provide --input PATH or --latest --dir DIR", file=sys.stderr)
                    return 1

                output_dir = _default_git_dataflow_run_dir()
                output_path = _default_git_dataflow_output_path(output_dir)
                if args.output:
                    output_path = output_dir / Path(args.output).name

                payload = json.loads(input_path.read_text(encoding="utf-8"))
                agent = GitDiffDataFlowAgent()
                agent.include_docs = bool(getattr(args, "include_docs", False))

                try:
                    for step in agent.plan(payload, always_use_llm=bool(args.llm)):
                        print(f"[plan] - {step}")
                except Exception:
                    pass

                response = asyncio.run(
                    agent.analyze(payload) if args.llm else agent.analyze_without_llm(payload)
                )
                if not response.success:
                    print(f"Error: {response.error or 'analysis failed'}", file=sys.stderr)
                    return 1

                output_path.write_text(response.explanation, encoding="utf-8")
                print(f"[git-dataflow] Wrote: {output_path}")

                run_id = uuid4().hex[:12]
                _write_run_manifest(
                    run_id=run_id, command="git-dataflow",
                    inputs={"input": str(input_path), "llm": bool(args.llm)},
                    artifacts={"git_dataflow_json": str(output_path), "git_artifacts_json": str(input_path)},
                    highlights=list(response.key_findings or []),
                    success=True,
                )
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

        # ── orchestrate handler ───────────────────────────────────────────────
        if args.command == "orchestrate":
            try:
                print("[orchestrate] Starting orchestrator...")

                if (args.fingerprint is None) == (args.from_log is None):
                    print("Provide exactly one of --fingerprint or --from-log", file=sys.stderr)
                    return 1

                if args.fingerprint:
                    fp_path = Path(args.fingerprint)
                    if not fp_path.exists():
                        print(f"Error: Fingerprint not found: {fp_path}", file=sys.stderr)
                        return 1
                    print(f"[orchestrate] Loading fingerprint: {fp_path}")
                    fp_payload = json.loads(fp_path.read_text(encoding="utf-8"))
                    fingerprint = ExecutionFingerprint.model_validate(fp_payload)
                else:
                    event_log_path = Path(args.from_log)
                    if not event_log_path.exists():
                        print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
                        return 1
                    fp_out = _default_fingerprint_output_path(event_log_path)
                    print(f"[orchestrate] Generating fingerprint: {event_log_path}")
                    fingerprint = generate_fingerprint(
                        str(event_log_path), output_format="json",
                        output_path=fp_out, include_evidence=True, detail_level="balanced",
                    )
                    print(f"[orchestrate] Fingerprint written: {fp_out}")

                out_dir = _default_orchestrator_output_dir()
                out_path = _default_orchestrator_output_path(out_dir)
                if args.output:
                    out_path = out_dir / Path(args.output).name

                print(f"[orchestrate] Query: {args.query}")
                result = asyncio.run(SmartOrchestrator(fingerprint).solve_problem(args.query))

                # ── KEY FIX: safe serialization ──
                out_path.write_text(_serialize_result(result), encoding="utf-8")
                print(f"[orchestrate] Wrote: {out_path}")

                pt = getattr(result, "problem_type", None)
                pt_val = pt.value if hasattr(pt, "value") else str(pt)
                print(f"[orchestrate] Problem type: {pt_val}")

                findings = getattr(result, "findings", []) or []
                print(f"[orchestrate] Findings: {len(findings)}")

                run_id = uuid4().hex[:12]
                _write_run_manifest(
                    run_id=run_id, command="orchestrate",
                    inputs={
                        "query": args.query,
                        "fingerprint": str(args.fingerprint) if args.fingerprint else None,
                        "from_log": str(args.from_log) if getattr(args, "from_log", None) else None,
                    },
                    artifacts={"orchestrator_json": str(out_path)},
                    highlights=[f.get("description", "") if isinstance(f, dict) else str(f)
                                for f in findings[:5]],
                    success=True,
                )
                return 0

            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()   # ← full stack trace always shown
                return 1

        # ── lineage-extract handler ───────────────────────────────────────────
        if args.command == "lineage-extract":
            try:
                from src.agents.lineage_extraction import LineageExtractionAgent

                print("[lineage-extract] Starting...")
                script_paths = []
                if args.folder:
                    folder_path = Path(args.folder)
                    if not folder_path.is_dir():
                        print(f"Error: Not a directory: {folder_path}", file=sys.stderr)
                        return 1
                    script_paths = sorted(
                        [str(p) for p in folder_path.glob("**/*.py")]
                        + [str(p) for p in folder_path.glob("**/*.sql")]
                    )
                    if not script_paths:
                        print(f"Error: No .py/.sql files in: {folder_path}", file=sys.stderr)
                        return 1
                    print(f"[lineage-extract] {len(script_paths)} script(s) found")
                elif args.scripts:
                    script_paths = args.scripts
                else:
                    print("Error: Provide --scripts or --folder", file=sys.stderr)
                    return 1

                output_dir = _repo_root() / "runs" / "lineage"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                if args.output:
                    output_path = Path(args.output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                agent = LineageExtractionAgent()
                response = asyncio.run(agent.analyze(
                    {}, script_paths=script_paths, output_path=str(output_path),
                    trace_table=args.trace_table, trace_column=args.trace_column,
                    trace_direction=args.trace_direction,
                ))

                if not response.success:
                    print(f"Error: {response.error}", file=sys.stderr)
                    return 1

                print(f"[lineage-extract] Success: {response.summary}")
                print(f"[lineage-extract] Output: {output_path}")

                run_id = uuid4().hex[:12]
                _write_run_manifest(
                    run_id=run_id, command="lineage-extract",
                    inputs={"folder": str(args.folder) if args.folder else None,
                            "scripts": script_paths, "trace_table": args.trace_table},
                    artifacts={"lineage_json": str(output_path)},
                    highlights=list(response.key_findings or []),
                    success=True,
                )
                if getattr(args, "view", False):
                    _best_effort_start_dashboard_server()
                    _best_effort_open_dashboard()
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

        # ── rca handler ───────────────────────────────────────────────────────
        if args.command == "rca":
            try:
                from src.agents.root_cause import RootCauseAgent, IncidentType
                from src.agent_coordination import AgentContext, IncidentContext

                print("[rca] Starting Root Cause Analysis...")

                if args.mode == "grc" and not args.incident_type:
                    print("Error: --incident-type required when --mode grc", file=sys.stderr)
                    return 1

                if (args.fingerprint is None) == (args.from_log is None):
                    print("Provide exactly one of --fingerprint or --from-log", file=sys.stderr)
                    return 1

                if args.fingerprint:
                    fp_path = Path(args.fingerprint)
                    if not fp_path.exists():
                        print(f"Error: Fingerprint not found: {fp_path}", file=sys.stderr)
                        return 1
                    fingerprint_dict = json.loads(fp_path.read_text(encoding="utf-8"))
                else:
                    event_log_path = Path(args.from_log)
                    fp_out = _default_fingerprint_output_path(event_log_path)
                    generate_fingerprint(str(event_log_path), output_format="json",
                                         output_path=fp_out, include_evidence=True, detail_level="balanced")
                    fingerprint_dict = json.loads(Path(fp_out).read_text())

                out_dir = _default_rca_output_dir()
                out_path = _default_rca_output_path(out_dir)
                if args.output:
                    out_path = out_dir / Path(args.output).name

                context = None
                if args.mode == "grc":
                    incident_ctx = IncidentContext(
                        incident_id=args.incident_id or f"INC-{uuid4().hex[:8]}",
                        incident_type=args.incident_type,
                        severity="high",
                        timestamp=datetime.now(timezone.utc),
                    )
                    context = AgentContext(
                        fingerprint_data=fingerprint_dict,
                        user_query=f"Analyze {args.incident_type} incident",
                        incident_context=incident_ctx,
                    )

                agent = RootCauseAgent()
                response = asyncio.run(agent.analyze(
                    fingerprint_dict, context=context, focus_areas=args.focus,
                    incident_type=IncidentType(args.incident_type) if args.incident_type else None,
                ))

                if not response.success:
                    print(f"Error: {response.error}", file=sys.stderr)
                    return 1

                result_data = {
                    "run_id": uuid4().hex[:12],
                    "mode": args.mode,
                    "incident_type": args.incident_type,
                    "incident_id": args.incident_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": response.summary,
                    "confidence": response.confidence,
                    "findings": response.key_findings,
                    "metadata": getattr(response, "metadata", {}),
                }
                out_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
                print(f"[rca] Success | Confidence: {response.confidence:.0%}")
                print(f"[rca] Output: {out_path}")

                run_id = uuid4().hex[:12]
                _write_run_manifest(
                    run_id=run_id, command="rca",
                    inputs={"mode": args.mode, "incident_type": args.incident_type,
                            "fingerprint": str(args.fingerprint) if args.fingerprint else None},
                    artifacts={"rca_json": str(out_path)},
                    highlights=list(response.key_findings or [])[:5],
                    success=True,
                )
                if getattr(args, "view", False):
                    _best_effort_start_dashboard_server()
                    _best_effort_open_dashboard()
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

        # ── fingerprint handler (subcommand) ──────────────────────────────────
        if args.command == "fingerprint":
            event_log_path = Path(args.event_log)
            if not event_log_path.exists():
                print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
                return 1
            try:
                output_path = args.output or _default_fingerprint_output_path(event_log_path)
                fingerprint = generate_fingerprint(
                    str(event_log_path), output_format=args.format,
                    output_path=output_path, include_evidence=not args.no_evidence,
                    detail_level=args.level,
                )
                print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
                print(f"  Execution Class: {fingerprint.execution_class}")
                print(f"  Output: {output_path}")
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                traceback.print_exc()
                return 1

    # ── Legacy mode ───────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Generate Spark Execution Fingerprint from event log")
    parser.add_argument("event_log")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--format", "-f", choices=["json", "yaml", "markdown"], default="json")
    parser.add_argument("--level", "-l", choices=["summary", "balanced", "detailed"], default="balanced")
    parser.add_argument("--no-evidence", action="store_true")
    args = parser.parse_args()

    event_log_path = Path(args.event_log)
    if not event_log_path.exists():
        print(f"Error: Event log not found: {event_log_path}", file=sys.stderr)
        return 1

    try:
        output_path = args.output or _default_fingerprint_output_path(event_log_path)
        fingerprint = generate_fingerprint(
            str(event_log_path), output_format=args.format,
            output_path=output_path, include_evidence=not args.no_evidence,
            detail_level=args.level,
        )
        print(f"  Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
        print(f"  Execution Class: {fingerprint.execution_class}")
        print(f"  Output: {output_path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
