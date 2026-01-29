"""
Lineage Extraction Agent - extracts data lineage from Spark ETL scripts.

This agent wraps the lineage-map library to provide AI-powered extraction
of table and column-level data lineage from Spark ETL scripts (.py, .sql).
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import json
from datetime import datetime, timezone
from hashlib import sha256

from src.agents.base import BaseAgent, AgentResponse, AgentType

logger = logging.getLogger(__name__)


def _normalize_lineage_map_result(result: Any) -> Dict[str, Any]:
    """Best-effort normalization of lineage-map results to a plain dict."""
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    # Pydantic v2
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:
            pass
    # Pydantic v1
    dict_fn = getattr(result, "dict", None)
    if callable(dict_fn):
        try:
            return dict_fn()
        except Exception:
            pass
    # Fallback: try __dict__
    try:
        return dict(getattr(result, "__dict__", {}))
    except Exception:
        return {}


def _result_success(result_dict: Dict[str, Any]) -> bool:
    if "success" in result_dict:
        return bool(result_dict.get("success"))
    # If no explicit success flag, treat presence of error as failure
    if result_dict.get("error"):
        return False
    return True


class LineageExtractionAgent(BaseAgent):
    """
    Agent that extracts data lineage (table/column dependencies) from Spark ETL scripts.
    
    Uses the lineage-map library with LangGraph orchestration to:
    - Extract lineage from single or multiple scripts
    - Validate extracted lineage schema
    - Merge lineages from multiple scripts
    - Trace column-level dependencies (upstream/downstream)
    - Generate lineage summaries
    """
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.LINEAGE_EXTRACTION
    
    @property
    def agent_name(self) -> str:
        return "Lineage Extraction Agent"
    
    @property
    def description(self) -> str:
        return "Extracts data lineage (table/column dependencies) from Spark ETL scripts using AI"
    
    @property
    def system_prompt(self) -> str:
        return """You are a data lineage extraction specialist. You analyze Spark ETL scripts
to identify table and column-level data dependencies, transformations, and data flows."""
    
    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        script_paths: Optional[List[str]] = None,
        trace_table: Optional[str] = None,
        trace_column: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """Generate execution plan for lineage extraction."""
        steps = [
            "Load ETL script(s) from provided paths",
            "Extract lineage using OpenAI GPT-4 (tables, columns, transformations)",
            "Validate extracted lineage schema",
        ]
        
        if script_paths and len(script_paths) > 1:
            steps.append(f"Merge lineages from {len(script_paths)} scripts")
        
        if trace_table and trace_column:
            steps.append(f"Trace column lineage: {trace_table}.{trace_column}")
        
        steps.extend([
            "Generate lineage summary (table count, column count, dependencies)",
            "Return structured lineage JSON"
        ])
        
        return steps
    
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        script_paths: Optional[List[str]] = None,
        output_path: Optional[str] = None,
        trace_table: Optional[str] = None,
        trace_column: Optional[str] = None,
        trace_direction: str = "upstream",
        **kwargs
    ) -> AgentResponse:
        """
        Extract lineage from ETL scripts.
        
        Args:
            fingerprint_data: Not used for lineage extraction (kept for interface consistency)
            context: Optional agent context
            script_paths: List of paths to ETL scripts (.py, .sql)
            output_path: Where to save lineage JSON
            trace_table: Optional table name to trace column lineage for
            trace_column: Optional column name to trace (requires trace_table)
            trace_direction: "upstream" or "downstream" (default: upstream)
            
        Returns:
            AgentResponse with lineage extraction results
        """
        try:
            # Validate inputs
            if not script_paths:
                return AgentResponse(
                    agent_type=self.agent_type,
                    agent_name=self.agent_name,
                    success=False,
                    summary="No script paths provided",
                    explanation="",
                    error="script_paths parameter is required"
                )
            
            # Verify scripts exist
            missing_scripts = []
            for script_path in script_paths:
                if not Path(script_path).exists():
                    missing_scripts.append(script_path)
            
            if missing_scripts:
                return AgentResponse(
                    agent_type=self.agent_type,
                    agent_name=self.agent_name,
                    success=False,
                    summary=f"Script(s) not found: {', '.join(missing_scripts)}",
                    explanation="",
                    error=f"Missing scripts: {missing_scripts}"
                )
            
            # Import lineage-map components (lazy import to avoid dependency issues)
            try:
                from lineage_mapper.agent import build_agent_graph, AgentState as LineageState
            except ImportError as e:
                return AgentResponse(
                    agent_type=self.agent_type,
                    agent_name=self.agent_name,
                    success=False,
                    summary="lineage-map library not installed",
                    explanation="",
                    error=f"Import error: {str(e)}. Run: pip install git+https://github.com/Byte-Farmer/lineage-map.git@main"
                )
            
            # Build lineage-map agent graph
            logger.info(f"[LineageExtractionAgent] Building lineage extraction graph")
            graph = build_agent_graph()
            
            # Prepare state
            state = LineageState(
                task="extract",
                script_paths=script_paths,
                output_path=output_path or "runs/lineage/lineage.json",
                trace_table=trace_table,
                trace_column=trace_column,
                trace_direction=trace_direction
            )
            
            logger.info(f"[LineageExtractionAgent] Extracting lineage from {len(script_paths)} script(s)")
            
            # Run lineage extraction (run in thread to avoid blocking)
            raw_result = await asyncio.to_thread(graph.invoke, state)
            result = _normalize_lineage_map_result(raw_result)

            if not _result_success(result):
                return AgentResponse(
                    agent_type=self.agent_type,
                    agent_name=self.agent_name,
                    success=False,
                    summary="Lineage extraction failed",
                    explanation="",
                    error=str(result.get("error") or "Unknown error during lineage extraction")
                )
            
            # Format response
            summary = f"Extracted lineage from {len(script_paths)} script(s)"
            
            # Build explanation from lineage data
            explanation_parts = []
            
            lineage_json = result.get("lineage_json") or result.get("lineage") or result.get("output")

            if lineage_json:
                try:
                    lineage_data = json.loads(lineage_json) if isinstance(lineage_json, str) else lineage_json
                    explanation_parts.append("## Lineage Extraction Results\n")
                    
                    if "tables" in lineage_data:
                        explanation_parts.append(f"**Tables identified:** {len(lineage_data['tables'])}")
                    
                    if "transformations" in lineage_data:
                        explanation_parts.append(f"**Transformations:** {len(lineage_data['transformations'])}")
                    
                except Exception as e:
                    logger.warning(f"Could not parse lineage JSON: {e}")
                    explanation_parts.append(f"Lineage data saved to: {output_path}")
            else:
                explanation_parts.append(f"Lineage data saved to: {output_path}")
            
            explanation = "\n".join(explanation_parts)
            
            # Build key findings
            key_findings = []
            
            result_summary = result.get("summary")
            if isinstance(result_summary, dict):
                if "table_count" in result_summary:
                    key_findings.append(f"Tables: {result_summary['table_count']}")
                if "column_count" in result_summary:
                    key_findings.append(f"Columns: {result_summary['column_count']}")
                if "transformation_count" in result_summary:
                    key_findings.append(f"Transformations: {result_summary['transformation_count']}")
            
            trace_result = result.get("trace_result")
            if trace_result:
                key_findings.append(f"Traced {trace_direction} dependencies for {trace_table}.{trace_column}")
                if isinstance(trace_result, dict) and "dependencies" in trace_result:
                    dep_count = len(trace_result["dependencies"])
                    key_findings.append(f"Found {dep_count} {trace_direction} dependencies")
            
            if output_path:
                key_findings.append(f"Output saved to: {output_path}")
            
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=summary,
                explanation=explanation,
                key_findings=key_findings,
                confidence=0.9
            )
            
        except Exception as e:
            logger.exception(f"[LineageExtractionAgent] Unexpected error: {e}")
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=False,
                summary="Lineage extraction error",
                explanation="",
                error=f"Unexpected error: {str(e)}"
            )
