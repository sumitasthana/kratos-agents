"""
Demo: Orchestrated Agentic Analysis of Spark Fingerprints

This demo showcases the two-layer agentic architecture:
- Layer 1: Existing infrastructure (fingerprint generation, individual agents)
- Layer 2: Smart orchestration (problem classification, agent coordination, result synthesis)

Usage:
    python demo_agentic.py "Why is my Spark job slow?"
    python demo_agentic.py "Explain what this query does"
    python demo_agentic.py --from-log data/event_logs_rca.json "What are the performance issues?"
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

from src.fingerprint import generate_fingerprint
from src.orchestrator import SmartOrchestrator
from src.schemas import AnalysisResult, ProblemType
from src.agents import LLMConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("demo_agentic")


# Default paths
FINGERPRINT_PATH = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/fingerprint_rca.json"
EVENT_LOG_PATH = "C:/LangChain/Kratos/spark_lineage_analyzer/v3/data/event_logs_rca.json"


def print_banner():
    """Print demo banner."""
    print("\n" + "=" * 70)
    print("   SPARK FINGERPRINT ANALYZER - AGENTIC ORCHESTRATION DEMO")
    print("=" * 70)


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print('─' * 70)


def print_result(result: AnalysisResult):
    """Pretty print the analysis result."""
    
    # Problem type badge
    type_badges = {
        ProblemType.PERFORMANCE: "[PERFORMANCE]",
        ProblemType.LINEAGE: "[LINEAGE]",
        ProblemType.GENERAL: "[GENERAL]"
    }
    badge = type_badges.get(result.problem_type, "[UNKNOWN]")
    
    print_section(f"ANALYSIS RESULT {badge}")
    
    print(f"\n  Query: {result.user_query}")
    print(f"  Problem Type: {result.problem_type.value}")
    print(f"  Agents Used: {', '.join(result.agents_used)}")
    print(f"  Processing Time: {result.total_processing_time_ms}ms")
    print(f"  Confidence: {result.confidence:.0%}")
    
    print_section("EXECUTIVE SUMMARY")
    print(f"\n  {result.executive_summary}")
    
    print_section("KEY FINDINGS")
    for i, finding in enumerate(result.findings[:8], 1):
        severity_icon = {
            "critical": "[!!!]",
            "high": "[!!]",
            "medium": "[!]",
            "low": "[.]",
            "info": "[i]"
        }.get(finding.severity, "[?]")
        print(f"\n  {i}. {severity_icon} {finding.description[:100]}")
        if len(finding.description) > 100:
            print(f"      {finding.description[100:200]}...")
    
    if result.recommendations:
        print_section("RECOMMENDATIONS")
        for i, rec in enumerate(result.recommendations[:5], 1):
            print(f"\n  {i}. {rec[:120]}")
            if len(rec) > 120:
                print(f"     {rec[120:240]}...")
    
    print_section("DETAILED ANALYSIS")
    # Truncate for display
    detailed = result.detailed_analysis
    if len(detailed) > 2000:
        detailed = detailed[:2000] + "\n\n  ... [truncated for display]"
    for line in detailed.split('\n'):
        print(f"  {line}")
    
    print_section("AGENT COORDINATION")
    print(f"\n  Execution Sequence: {' -> '.join(result.agent_sequence)}")
    print(f"  Total Findings: {len(result.findings)}")
    print(f"  Total Recommendations: {len(result.recommendations)}")


def load_fingerprint_from_file(path: str):
    """Load a pre-generated fingerprint from JSON file."""
    logger.info(f"Loading fingerprint from: {path}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    # Import here to avoid circular imports
    from src.schemas import ExecutionFingerprint
    fingerprint = ExecutionFingerprint.model_validate(data)
    
    logger.info(f"Loaded fingerprint for app: {fingerprint.context.spark_config.app_name}")
    return fingerprint


def generate_fingerprint_from_log(event_log_path: str):
    """Generate fingerprint from event log."""
    logger.info(f"Generating fingerprint from: {event_log_path}")
    
    fingerprint = generate_fingerprint(
        event_log_path=event_log_path,
        output_format="json",
        include_evidence=True,
        detail_level="balanced"
    )
    
    logger.info(f"Generated fingerprint for app: {fingerprint.context.spark_config.app_name}")
    return fingerprint


async def run_orchestrated_analysis(fingerprint, user_query: str, llm_config: LLMConfig):
    """Run the orchestrated analysis."""
    
    print_section("INITIALIZING ORCHESTRATOR")
    print(f"\n  App: {fingerprint.context.spark_config.app_name}")
    print(f"  Spark Version: {fingerprint.context.spark_config.spark_version}")
    print(f"  Stages: {fingerprint.semantic.dag.total_stages}")
    print(f"  Tasks: {fingerprint.metrics.execution_summary.total_tasks}")
    print(f"  Anomalies: {len(fingerprint.metrics.anomalies)}")
    
    # Create orchestrator
    orchestrator = SmartOrchestrator(fingerprint, llm_config)
    
    print_section("RUNNING ORCHESTRATED ANALYSIS")
    print(f"\n  User Query: \"{user_query}\"")
    print(f"  LLM Model: {llm_config.model}")
    print("\n  Starting analysis...")
    
    # Run analysis
    result = await orchestrator.solve_problem(user_query)
    
    return result


async def run_independent_analysis(fingerprint, llm_config: LLMConfig):
    """Run agents independently for comparison."""
    from src.agents import QueryUnderstandingAgent, RootCauseAgent
    
    print_section("RUNNING INDEPENDENT AGENTS (for comparison)")
    
    fingerprint_dict = fingerprint.model_dump()
    
    # Run Query Understanding Agent
    print("\n  Running Query Understanding Agent independently...")
    query_agent = QueryUnderstandingAgent(llm_config)
    query_start = time.time()
    query_response = await query_agent.analyze(fingerprint_dict)
    query_time = int((time.time() - query_start) * 1000)
    print(f"  [OK] Query Understanding complete in {query_time}ms")
    
    # Run Root Cause Agent
    print("\n  Running Root Cause Agent independently...")
    rca_agent = RootCauseAgent(llm_config)
    rca_start = time.time()
    rca_response = await rca_agent.analyze(fingerprint_dict)
    rca_time = int((time.time() - rca_start) * 1000)
    print(f"  [OK] Root Cause Analysis complete in {rca_time}ms")
    
    total_time = query_time + rca_time
    print(f"\n  Total independent time: {total_time}ms")
    
    return {
        "query_understanding": query_response,
        "root_cause": rca_response,
        "total_time_ms": total_time
    }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Orchestrated Agentic Analysis of Spark Fingerprints"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="Why is my Spark job experiencing performance issues?",
        help="Natural language query about the Spark execution"
    )
    parser.add_argument(
        "--from-log",
        type=str,
        help="Generate fingerprint from event log file"
    )
    parser.add_argument(
        "--fingerprint",
        type=str,
        default=FINGERPRINT_PATH,
        help="Path to pre-generated fingerprint JSON"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Also run agents independently for comparison"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use"
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("\nError: OPENAI_API_KEY environment variable not set.")
        print("Please set it or create a .env file with your API key.")
        sys.exit(1)
    
    print_banner()
    
    # Load or generate fingerprint
    print_section("LOADING FINGERPRINT")
    
    if args.from_log:
        print(f"\n  Generating from event log: {args.from_log}")
        fingerprint = generate_fingerprint_from_log(args.from_log)
    else:
        print(f"\n  Loading from file: {args.fingerprint}")
        fingerprint = load_fingerprint_from_file(args.fingerprint)
    
    print(f"  [OK] Fingerprint ready")
    
    # Configure LLM
    llm_config = LLMConfig(model=args.model)
    logger.info(f"Using LLM model: {llm_config.model}")
    
    # Run orchestrated analysis
    result = await run_orchestrated_analysis(fingerprint, args.query, llm_config)
    
    # Print results
    print_result(result)
    
    # Optionally compare with independent execution
    if args.compare:
        independent_results = await run_independent_analysis(fingerprint, llm_config)
        
        print_section("COMPARISON: ORCHESTRATED vs INDEPENDENT")
        print(f"\n  Orchestrated time: {result.total_processing_time_ms}ms")
        print(f"  Independent time: {independent_results['total_time_ms']}ms")
        print(f"\n  Orchestrated findings: {len(result.findings)}")
        print(f"  Independent findings: {len(independent_results['query_understanding'].key_findings) + len(independent_results['root_cause'].key_findings)}")
        print(f"\n  Note: Orchestrated analysis enables context sharing between agents,")
        print(f"        allowing later agents to build on earlier findings.")
    
    print("\n" + "=" * 70)
    print("   DEMO COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
