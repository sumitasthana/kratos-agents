"""
Demo: Analyze a Spark fingerprint with Query Understanding and Root Cause agents.

Requires OPENAI_API_KEY environment variable to be set.

Usage:
    python demo.py                                    # Run with existing fingerprint
    python demo.py --from-log data/event_logs_rca.json  # Full flow: log -> fingerprint -> agents
    python demo.py --no-llm                           # Rule-based only (no API key needed)
    python demo.py --agent query                      # Run only Query Understanding agent
    python demo.py --agent root-cause                 # Run only Root Cause agent
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

from src.agents import QueryUnderstandingAgent, RootCauseAgent, LLMConfig, AgentResponse
from src.fingerprint import generate_fingerprint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("demo")


FINGERPRINT_PATH = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/fingerprint.json"
FINGERPRINT_RCA_PATH = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/fingerprint_rca.json"
EVENT_LOG_RCA_PATH = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/data/event_logs_rca.json"
FINGERPRINT_OUTPUT_DIR = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/fingerprints"


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def print_response(response: AgentResponse):
    """Pretty print an agent response."""
    print(f"\n[SUMMARY]")
    print(f"   {response.summary}")
    
    print(f"\n[EXPLANATION]")
    for line in response.explanation.split('\n'):
        print(f"   {line}")
    
    if response.key_findings:
        print(f"\n[KEY FINDINGS]")
        for i, finding in enumerate(response.key_findings[:8], 1):
            print(f"   {i}. {finding}")
    
    print(f"\n[METADATA]")
    print(f"   Confidence: {response.confidence:.0%}")
    print(f"   Processing Time: {response.processing_time_ms}ms")
    if response.model_used:
        print(f"   Model: {response.model_used}")
    
    if response.suggested_followup_agents:
        print(f"\n[SUGGESTED NEXT AGENTS]")
        for agent_type in response.suggested_followup_agents:
            print(f"   - {agent_type.value}")


def load_fingerprint(fingerprint_path: str) -> dict:
    """Load fingerprint from JSON file."""
    logger.info(f"Loading fingerprint from: {fingerprint_path}")
    print_section("Loading Fingerprint")
    print(f"  Source: {fingerprint_path}")
    
    with open(fingerprint_path, 'r') as f:
        fingerprint = json.load(f)
    
    logger.info("Fingerprint loaded successfully")
    print(f"  [OK] Fingerprint loaded successfully")
    print(f"  [OK] App: {fingerprint['context']['spark_config']['app_name']}")
    print(f"  [OK] Spark Version: {fingerprint['context']['spark_config']['spark_version']}")
    print(f"  [OK] Stages: {fingerprint['semantic']['dag']['total_stages']}")
    print(f"  [OK] Events Parsed: {fingerprint['metadata']['events_parsed']}")
    
    logger.debug(f"Fingerprint metadata: {fingerprint.get('metadata', {})}")
    return fingerprint


def generate_fingerprint_from_log(event_log_path: str, output_path: str = None) -> dict:
    """Generate fingerprint from Spark event log file and save with timestamp."""
    logger.info(f"Generating fingerprint from event log: {event_log_path}")
    print_section("Step 1: Generating Fingerprint from Event Log")
    print(f"  Event Log: {event_log_path}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(FINGERPRINT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamped output path if not provided
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = Path(event_log_path).stem
    if not output_path:
        output_path = str(output_dir / f"fingerprint_{log_name}_{timestamp}.json")
    
    # Generate fingerprint
    fingerprint = generate_fingerprint(
        event_log_path=event_log_path,
        output_format="json",
        output_path=output_path,
        include_evidence=True,
        detail_level="balanced"
    )
    
    # Convert to dict for agents
    fingerprint_dict = json.loads(fingerprint.model_dump_json())
    
    logger.info(f"Fingerprint generated and saved to: {output_path}")
    print(f"  [OK] Fingerprint generated successfully")
    print(f"  [OK] App: {fingerprint.context.spark_config.app_name}")
    print(f"  [OK] Spark Version: {fingerprint.context.spark_config.spark_version}")
    print(f"  [OK] Stages: {fingerprint.semantic.dag.total_stages}")
    print(f"  [OK] Events Parsed: {fingerprint.metadata.events_parsed}")
    
    # Show execution class and hints
    print(f"  [OK] Execution Class: {fingerprint.execution_class}")
    if fingerprint.analysis_hints:
        print(f"  [OK] Analysis Hints:")
        for hint in fingerprint.analysis_hints:
            print(f"       - {hint}")
    
    print(f"  [OK] Saved to: {output_path}")
    
    return fingerprint_dict


def show_fingerprint_preview(fingerprint: dict):
    """Show key parts of the fingerprint."""
    logger.info("Displaying fingerprint preview")
    print_section("Fingerprint Preview")
    
    semantic = fingerprint.get("semantic", {})
    context = fingerprint.get("context", {})
    metrics = fingerprint.get("metrics", {})
    
    print("\n[SEMANTIC LAYER]")
    print(f"   Description: {semantic.get('description', 'N/A')}")
    print(f"   Semantic Hash: {semantic.get('semantic_hash', 'N/A')[:16]}...")
    
    dag = semantic.get("dag", {})
    if dag:
        print(f"   Stages: {dag.get('total_stages', 0)}")
        for stage in dag.get("stages", [])[:3]:
            print(f"     - Stage {stage.get('stage_id')}: {stage.get('description', stage.get('stage_name'))}")
        if len(dag.get("stages", [])) > 3:
            print(f"     ... and {len(dag['stages']) - 3} more stages")
    
    print("\n[CONTEXT LAYER]")
    spark_config = context.get("spark_config", {})
    print(f"   App: {spark_config.get('app_name', 'N/A')}")
    print(f"   Spark: {spark_config.get('spark_version', 'N/A')}")
    
    exec_config = context.get("executor_config", {})
    print(f"   Executors: {exec_config.get('total_executors', 'N/A')} x {exec_config.get('executor_memory_mb', 'N/A')}MB")
    
    print("\n[METRICS LAYER]")
    summary = metrics.get("execution_summary", {})
    print(f"   Duration: {summary.get('total_duration_ms', 0)}ms")
    print(f"   Tasks: {summary.get('total_tasks', 0)}")
    print(f"   Failed Tasks: {summary.get('failed_task_count', 0)}")
    print(f"   Spill: {summary.get('total_spill_bytes', 0):,} bytes")
    
    anomalies = metrics.get("anomalies", [])
    if anomalies:
        print(f"   Anomalies: {len(anomalies)}")
        logger.warning(f"Found {len(anomalies)} anomalies in fingerprint")
        for a in anomalies[:3]:
            print(f"     [{a.get('severity', 'unknown').upper()}] {a.get('description')}")


async def run_query_understanding(fingerprint: dict, use_llm: bool) -> AgentResponse:
    """Run Query Understanding Agent."""
    logger.info("Starting Query Understanding Agent")
    print_section("Agent 1: Query Understanding")
    
    config = LLMConfig(model="gpt-4o") if use_llm else None
    agent = QueryUnderstandingAgent(llm_config=config)
    
    if use_llm:
        print("  Mode: LLM-powered (GPT-4o)")
        logger.info("Calling OpenAI API for query understanding...")
        print("  Calling OpenAI API...")
        response = await agent.analyze(fingerprint)
        logger.info(f"LLM response received in {response.processing_time_ms}ms")
        print(f"  [OK] LLM response received")
    else:
        print("  Mode: Rule-based (no LLM)")
        logger.info("Running rule-based analysis (no LLM)")
        response = await agent.analyze_without_llm(fingerprint)
    
    logger.debug(f"Query Understanding findings: {len(response.key_findings)} items")
    print_response(response)
    return response


async def run_root_cause(fingerprint: dict, use_llm: bool) -> AgentResponse:
    """Run Root Cause Analysis Agent."""
    logger.info("Starting Root Cause Analysis Agent")
    print_section("Agent 2: Root Cause Analysis")
    
    config = LLMConfig(model="gpt-4o") if use_llm else None
    agent = RootCauseAgent(llm_config=config)
    
    if use_llm:
        print("  Mode: LLM-powered (GPT-4o)")
        logger.info("Calling OpenAI API for root cause analysis...")
        print("  Calling OpenAI API...")
        response = await agent.analyze(fingerprint)
        logger.info(f"LLM response received in {response.processing_time_ms}ms")
        print(f"  [OK] LLM response received")
    else:
        print("  Mode: Rule-based (no LLM)")
        logger.info("Running rule-based analysis (no LLM)")
        response = await agent.analyze_without_llm(fingerprint)
    
    logger.debug(f"Root Cause findings: {len(response.key_findings)} items")
    print_response(response)
    return response


async def main():
    parser = argparse.ArgumentParser(
        description="Demo: Spark Fingerprint Analysis with LLM Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo.py                                      # Run with existing fingerprint
  python demo.py --from-log data/event_logs_rca.json  # Full flow: log -> fingerprint -> agents
  python demo.py --no-llm                             # Rule-based only
  python demo.py --agent query                        # Only Query Understanding
  python demo.py --agent root-cause                   # Only Root Cause Analysis
        """
    )
    parser.add_argument("--no-llm", action="store_true", help="Use rule-based analysis (no API key needed)")
    parser.add_argument("--agent", choices=["query", "root-cause", "all"], default="all", 
                        help="Which agent to run (default: all)")
    parser.add_argument("--fingerprint", default=FINGERPRINT_PATH, help="Path to fingerprint JSON file")
    parser.add_argument("--from-log", dest="event_log", help="Generate fingerprint from event log file first")
    parser.add_argument("--save-fingerprint", dest="save_fp", help="Save generated fingerprint to this path")
    args = parser.parse_args()
    
    use_llm = not args.no_llm
    
    # Check for API key if using LLM
    if use_llm and not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set")
        print("\n[ERROR] OPENAI_API_KEY not set!")
        print("   Set it with: $env:OPENAI_API_KEY = 'sk-your-key-here'")
        print("   Or run with --no-llm for rule-based analysis")
        return
    
    print("\n" + "SPARK FINGERPRINT ANALYZER DEMO".center(70))
    print(f"   Mode: {'LLM-powered (GPT-4o)' if use_llm else 'Rule-based'}")
    logger.info(f"Starting demo with mode: {'LLM' if use_llm else 'Rule-based'}")
    
    # Either generate fingerprint from log or load existing
    if args.event_log:
        # Full flow: event log -> fingerprint -> agents
        try:
            fingerprint = generate_fingerprint_from_log(args.event_log, args.save_fp)
        except Exception as e:
            logger.error(f"Failed to generate fingerprint: {e}")
            print(f"  [ERROR] Failed to generate fingerprint: {e}")
            print(f"  Falling back to pre-generated fingerprint...")
            fingerprint = load_fingerprint(FINGERPRINT_RCA_PATH)
    else:
        # Load existing fingerprint
        fingerprint = load_fingerprint(args.fingerprint)
    
    # Show fingerprint preview
    show_fingerprint_preview(fingerprint)
    
    # Run agents
    if args.agent in ["query", "all"]:
        await run_query_understanding(fingerprint, use_llm)
    
    if args.agent in ["root-cause", "all"]:
        await run_root_cause(fingerprint, use_llm)
    
    print_section("Demo Complete")
    logger.info("Demo completed successfully")
    if not use_llm:
        print("  Tip: Run with LLM by setting OPENAI_API_KEY and running without --no-llm")


if __name__ == "__main__":
    asyncio.run(main())
