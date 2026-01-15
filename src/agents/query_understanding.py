"""
Query Understanding Agent.

Analyzes Spark physical/logical plans and DAG structure to explain
what a query does in plain English. Uses LangChain for LLM interactions.

Helps users understand:
- What data transformations are happening
- Join strategies and their implications
- Filter and aggregation logic
- Data flow through the execution plan
"""

import logging
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END

from .base import BaseAgent, AgentResponse, AgentType, LLMConfig, AgentState

logger = logging.getLogger(__name__)


QUERY_UNDERSTANDING_PROMPT = """You are a Spark SQL expert who explains query execution plans in clear, accessible language.

Your task is to analyze a Spark execution fingerprint and explain what the query/job does.

Guidelines:
1. Start with a high-level summary (1-2 sentences) of what the query accomplishes
2. Explain the data flow step-by-step, from input sources to final output
3. Highlight important operations: joins (and their strategies), aggregations, filters
4. Note any potential concerns visible in the plan (e.g., Cartesian products, full table scans)
5. Use business-friendly language, but include technical terms where helpful
6. If SQL plan is available, focus on that; otherwise use the DAG structure

Output format:
- **Summary**: 1-2 sentence overview
- **Data Flow**: Step-by-step explanation
- **Key Operations**: Important transformations with their strategies
- **Observations**: Any notable patterns or potential concerns

Be concise but thorough. Avoid jargon without explanation."""


class QueryUnderstandingAgent(BaseAgent):
    """
    Agent that explains Spark query plans in natural language.
    
    Analyzes:
    - Physical plan structure (operators, joins, scans)
    - DAG topology (stages, dependencies)
    - Logical plan hash context
    
    Produces human-readable explanation of what the query does.
    """
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.QUERY_UNDERSTANDING
    
    @property
    def agent_name(self) -> str:
        return "Query Understanding Agent"
    
    @property
    def description(self) -> str:
        return "Explains Spark query execution plans in plain English"
    
    @property
    def system_prompt(self) -> str:
        return QUERY_UNDERSTANDING_PROMPT
    
    async def analyze(
        self, 
        fingerprint_data: Dict[str, Any],
        include_dag: bool = True,
        include_plan: bool = True,
        **kwargs
    ) -> AgentResponse:
        """
        Analyze fingerprint and explain the query.
        
        Args:
            fingerprint_data: Full fingerprint or just semantic layer
            include_dag: Whether to include DAG analysis
            include_plan: Whether to include physical plan analysis
            
        Returns:
            AgentResponse with query explanation
        """
        logger.info(f"Starting query understanding analysis (include_dag={include_dag}, include_plan={include_plan})")
        start_time = time.time()
        
        try:
            # Extract semantic layer
            semantic = self._extract_semantic(fingerprint_data)
            if not semantic:
                logger.error("No semantic data found in fingerprint")
                return self._create_error_response("No semantic data found in fingerprint")
            
            logger.debug(f"Extracted semantic layer with {len(semantic.get('dag', {}).get('stages', []))} stages")
            
            # Build context for LLM
            context = self._build_context(semantic, include_dag, include_plan)
            logger.debug(f"Built context with keys: {list(context.keys())}")
            
            # Call LLM for interpretation
            user_prompt = self._build_user_prompt(context)
            logger.info(f"Calling LLM with {len(user_prompt)} char prompt")
            llm_response = await self._call_llm(QUERY_UNDERSTANDING_PROMPT, user_prompt)
            
            # Parse response into structured format
            response = self._parse_llm_response(llm_response, start_time)
            logger.info(f"Analysis complete: {len(response.key_findings)} findings, confidence={response.confidence}")
            return response
            
        except Exception as e:
            logger.exception(f"Error during query understanding analysis: {e}")
            return self._create_error_response(str(e))
    
    def _extract_semantic(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract semantic layer from fingerprint data."""
        # Handle both full fingerprint and semantic-only input
        if "semantic" in fingerprint_data:
            return fingerprint_data["semantic"]
        elif "dag" in fingerprint_data:
            # Already semantic layer
            return fingerprint_data
        return None
    
    def _build_context(
        self, 
        semantic: Dict[str, Any],
        include_dag: bool,
        include_plan: bool
    ) -> Dict[str, Any]:
        """Build context dict for LLM prompt."""
        context = {
            "semantic_hash": semantic.get("semantic_hash", "N/A"),
            "description": semantic.get("description", "No description available"),
        }
        
        # Add DAG information
        if include_dag and "dag" in semantic:
            dag = semantic["dag"]
            context["dag"] = {
                "total_stages": dag.get("total_stages", len(dag.get("stages", []))),
                "stages": self._summarize_stages(dag.get("stages", [])),
                "edges": dag.get("edges", []),
                "root_stages": dag.get("root_stage_ids", []),
                "leaf_stages": dag.get("leaf_stage_ids", []),
            }
        
        # Add physical plan if available
        if include_plan and semantic.get("physical_plan"):
            context["physical_plan"] = self._flatten_plan(semantic["physical_plan"])
        
        # Add logical plan info
        if "logical_plan_hash" in semantic:
            lph = semantic["logical_plan_hash"]
            context["logical_plan"] = {
                "is_sql": lph.get("is_sql", False),
                "plan_text": lph.get("plan_text", "")[:2000],  # Truncate if too long
            }
        
        return context
    
    def _summarize_stages(self, stages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create concise stage summaries."""
        summaries = []
        for stage in stages:
            summaries.append({
                "id": stage.get("stage_id"),
                "name": stage.get("stage_name", ""),
                "partitions": stage.get("num_partitions"),
                "is_shuffle": stage.get("is_shuffle_stage", False),
                "description": stage.get("description", ""),
            })
        return summaries
    
    def _flatten_plan(self, plan_node: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
        """Flatten physical plan tree into list with depth info."""
        if not plan_node:
            return []
        
        nodes = [{
            "depth": depth,
            "operator": plan_node.get("operator", "Unknown"),
            "description": plan_node.get("description", ""),
            "estimated_rows": plan_node.get("estimated_rows"),
            "attributes": plan_node.get("attributes", {}),
        }]
        
        # Recursively process children
        for child_id in plan_node.get("children", []):
            # Note: In real implementation, would need to resolve child references
            pass
        
        return nodes
    
    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Build the user prompt with context data."""
        prompt_parts = [
            "Analyze this Spark execution fingerprint and explain what the query does:\n"
        ]
        
        # Add description if available
        if context.get("description"):
            prompt_parts.append(f"**Existing Description**: {context['description']}\n")
        
        # Add DAG info
        if "dag" in context:
            dag = context["dag"]
            prompt_parts.append(f"\n**Execution DAG** ({dag['total_stages']} stages):\n")
            
            for stage in dag.get("stages", []):
                shuffle_marker = " [SHUFFLE]" if stage.get("is_shuffle") else ""
                prompt_parts.append(
                    f"- Stage {stage['id']}: {stage.get('description', stage.get('name', 'N/A'))}"
                    f" ({stage.get('partitions', '?')} partitions){shuffle_marker}\n"
                )
            
            if dag.get("edges"):
                prompt_parts.append("\n**Stage Dependencies**:\n")
                for edge in dag["edges"]:
                    shuffle = " (shuffle)" if edge.get("shuffle_required") else ""
                    prompt_parts.append(
                        f"- Stage {edge['from_stage_id']} → Stage {edge['to_stage_id']}"
                        f": {edge.get('reason', 'dependency')}{shuffle}\n"
                    )
        
        # Add physical plan
        if "physical_plan" in context:
            prompt_parts.append("\n**Physical Plan Operators**:\n")
            for node in context["physical_plan"]:
                indent = "  " * node["depth"]
                rows = f" (~{node['estimated_rows']} rows)" if node.get("estimated_rows") else ""
                prompt_parts.append(f"{indent}- {node['operator']}: {node['description']}{rows}\n")
        
        # Add logical plan text if SQL
        if context.get("logical_plan", {}).get("is_sql"):
            plan_text = context["logical_plan"].get("plan_text", "")
            if plan_text:
                prompt_parts.append(f"\n**Logical Plan**:\n```\n{plan_text}\n```\n")
        
        return "".join(prompt_parts)
    
    def _parse_llm_response(self, llm_response: str, start_time: float) -> AgentResponse:
        """Parse LLM response into structured AgentResponse."""
        processing_time = int((time.time() - start_time) * 1000)
        
        # Extract sections from response
        lines = llm_response.strip().split("\n")
        summary = ""
        key_findings = []
        
        # Simple parsing - look for Summary section
        in_summary = False
        for line in lines:
            line_lower = line.lower().strip()
            if "**summary**" in line_lower or line_lower.startswith("summary:"):
                in_summary = True
                # Check if summary is on same line
                if ":" in line:
                    summary = line.split(":", 1)[1].strip()
                continue
            elif line.startswith("**") and in_summary:
                in_summary = False
            elif in_summary and line.strip():
                summary += " " + line.strip()
            
            # Extract bullet points as key findings
            if line.strip().startswith("- ") or line.strip().startswith("• "):
                finding = line.strip()[2:].strip()
                if finding and len(finding) > 10:
                    key_findings.append(finding)
        
        # Fallback summary if not found
        if not summary:
            summary = lines[0] if lines else "Query analysis complete"
        
        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary.strip(),
            explanation=llm_response,
            key_findings=key_findings[:10],  # Limit to top 10
            confidence=0.85,  # Default confidence for LLM-based analysis
            processing_time_ms=processing_time,
            model_used=self.llm_config.model,
            suggested_followup_agents=[
                AgentType.OPTIMIZATION,  # Might want optimization suggestions
                AgentType.ROOT_CAUSE,    # If anomalies detected
            ]
        )
    
    async def analyze_without_llm(self, fingerprint_data: Dict[str, Any]) -> AgentResponse:
        """
        Analyze fingerprint using only rule-based extraction (no LLM call).
        Useful for testing or when LLM is unavailable.
        """
        start_time = time.time()
        
        try:
            semantic = self._extract_semantic(fingerprint_data)
            if not semantic:
                return self._create_error_response("No semantic data found")
            
            # Build explanation from available data
            explanation_parts = []
            key_findings = []
            
            # Use existing description
            description = semantic.get("description", "")
            if description:
                explanation_parts.append(f"**Overview**: {description}")
                key_findings.append(description)
            
            # Analyze DAG
            if "dag" in semantic:
                dag = semantic["dag"]
                stages = dag.get("stages", [])
                edges = dag.get("edges", [])
                
                explanation_parts.append(f"\n**Execution Structure**: {len(stages)} stages")
                
                shuffle_stages = [s for s in stages if s.get("is_shuffle_stage")]
                if shuffle_stages:
                    key_findings.append(f"{len(shuffle_stages)} shuffle stages detected")
                
                for stage in stages:
                    desc = stage.get("description", stage.get("stage_name", f"Stage {stage.get('stage_id')}"))
                    explanation_parts.append(f"- Stage {stage.get('stage_id')}: {desc}")
            
            # Note if SQL plan available
            if semantic.get("physical_plan"):
                key_findings.append("SQL physical plan available for detailed analysis")
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=description or "Query structure extracted (LLM analysis not performed)",
                explanation="\n".join(explanation_parts),
                key_findings=key_findings,
                confidence=0.6,  # Lower confidence without LLM
                processing_time_ms=processing_time,
            )
            
        except Exception as e:
            return self._create_error_response(str(e))
