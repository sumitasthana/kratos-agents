"""
Query Understanding Agent.

Analyzes Spark physical/logical plans and DAG structure to explain
what a query does in plain English.

Helps users understand:
- What data transformations are happening
- Join strategies and their implications
- Filter and aggregation logic
- Data flow through the execution plan
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResponse, AgentType

logger = logging.getLogger(__name__)


QUERY_UNDERSTANDING_PROMPT = """You are a Spark SQL expert who explains query execution plans in clear, accessible language.

Your task is to analyze a Spark execution fingerprint and explain what the query/job does.

Guidelines:
1. Start with a high-level summary (1–2 sentences) of what the query accomplishes.
2. Explain the data flow step-by-step, from input sources to final output.
3. Highlight important operations: joins (and their strategies), aggregations, filters.
4. Note any potential concerns visible in the plan (e.g., Cartesian products, full table scans).
5. Use business-friendly language, but include technical terms where helpful.
6. If SQL plan is available, focus on that; otherwise use the DAG structure.

Output format (use these Markdown section headers):

- **Summary**: 1–2 sentence overview
- **Data Flow**: Step-by-step explanation
- **Key Operations**: Important transformations with their strategies
- **Observations**: Any notable patterns or potential concerns

Be concise but thorough. Avoid jargon without explanation.
"""


class QueryUnderstandingAgent(BaseAgent):
    """
    Agent that explains Spark query plans in natural language.

    Analyzes:
    - Physical plan structure (operators, joins, scans)
    - DAG topology (stages, dependencies)
    - Logical plan hash context

    Produces a human-readable explanation of what the query does.
    """

    # --------------------------------------------------------------------- #
    # Base metadata
    # --------------------------------------------------------------------- #

    @property
    def agent_type(self) -> AgentType:
        return AgentType.QUERY_UNDERSTANDING

    @property
    def agent_name(self) -> str:
        return "Query Understanding Agent"

    @property
    def description(self) -> str:
        return "Explains Spark query execution plans in plain English."

    @property
    def system_prompt(self) -> str:
        return QUERY_UNDERSTANDING_PROMPT

    # --------------------------------------------------------------------- #
    # High-level plan
    # --------------------------------------------------------------------- #

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        include_dag: bool = True,
        include_plan: bool = True,
        **kwargs: Any,
    ) -> List[str]:
        steps = ["Extract semantic layer (DAG + plan metadata)"]
        if include_dag:
            steps.append("Summarize execution DAG (stages, edges, shuffles)")
        if include_plan:
            steps.append("Include physical/logical plan details if present")
        steps.extend(
            [
                "Build LLM prompt from extracted context",
                "Call LLM to generate a plain-English explanation",
                "Parse response into summary + key findings",
            ]
        )
        return steps

    # --------------------------------------------------------------------- #
    # Main analysis
    # --------------------------------------------------------------------- #

    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        include_dag: bool = True,
        include_plan: bool = True,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Analyze fingerprint and explain the query.

        Args:
            fingerprint_data: Full fingerprint or just the semantic layer.
            context: Optional AgentContext for coordinated analysis.
            include_dag: Whether to include DAG analysis.
            include_plan: Whether to include physical plan analysis.

        Returns:
            AgentResponse with query explanation.
        """
        logger.info(
            "Starting query understanding analysis "
            f"(include_dag={include_dag}, include_plan={include_plan})"
        )
        start_time = time.time()

        try:
            semantic = self._extract_semantic(fingerprint_data)
            if not semantic:
                logger.error("No semantic data found in fingerprint")
                return self._create_error_response("No semantic data found in fingerprint")

            logger.debug(
                "Extracted semantic layer with %d stages",
                len(semantic.get("dag", {}).get("stages", [])),
            )

            ctx = self._build_context(semantic, include_dag, include_plan)
            logger.debug("Built context with keys: %s", list(ctx.keys()))

            user_prompt = self._build_user_prompt(ctx)
            logger.info("Calling LLM with %d-character prompt", len(user_prompt))

            llm_response = await self._call_llm(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
            )

            response = self._parse_llm_response(llm_response, start_time)
            logger.info(
                "Query understanding complete: %d findings, confidence=%.2f",
                len(response.key_findings),
                response.confidence,
            )
            return response

        except Exception as exc:  # noqa: BLE001
            logger.exception("Error during query understanding analysis: %s", exc)
            return self._create_error_response(str(exc))

    # --------------------------------------------------------------------- #
    # Semantic extraction & context building
    # --------------------------------------------------------------------- #

    def _extract_semantic(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract the semantic layer (DAG + plan) from fingerprint data."""
        if "semantic" in fingerprint_data:
            return fingerprint_data["semantic"]
        if "dag" in fingerprint_data:
            # Already semantic layer
            return fingerprint_data
        return None

    def _build_context(
        self,
        semantic: Dict[str, Any],
        include_dag: bool,
        include_plan: bool,
    ) -> Dict[str, Any]:
        """Build a compact context dict used to construct the LLM prompt."""
        ctx: Dict[str, Any] = {
            "semantic_hash": semantic.get("semantic_hash", "N/A"),
            "description": semantic.get("description", "No description available"),
        }

        if include_dag and "dag" in semantic:
            dag = semantic["dag"]
            ctx["dag"] = {
                "total_stages": dag.get("total_stages", len(dag.get("stages", []))),
                "stages": self._summarize_stages(dag.get("stages", [])),
                "edges": dag.get("edges", []),
                "root_stages": dag.get("root_stage_ids", []),
                "leaf_stages": dag.get("leaf_stage_ids", []),
            }

        if include_plan and semantic.get("physical_plan"):
            ctx["physical_plan"] = self._flatten_plan(semantic["physical_plan"])

        if "logical_plan_hash" in semantic:
            lph = semantic["logical_plan_hash"]
            ctx["logical_plan"] = {
                "is_sql": lph.get("is_sql", False),
                "plan_text": lph.get("plan_text", "")[:2000],
            }

        return ctx

    @staticmethod
    def _summarize_stages(stages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create concise stage summaries for the DAG section of the prompt."""
        summaries: List[Dict[str, Any]] = []
        for stage in stages:
            summaries.append(
                {
                    "id": stage.get("stage_id"),
                    "name": stage.get("stage_name", ""),
                    "partitions": stage.get("num_partitions"),
                    "is_shuffle": stage.get("is_shuffle_stage", False),
                    "description": stage.get("description", ""),
                }
            )
        return summaries

    def _flatten_plan(
        self,
        plan_node: Dict[str, Any],
        depth: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Flatten physical plan tree into a list with depth info.

        Note: In real deployments this should resolve child references
        into full nodes rather than just IDs.
        """
        if not plan_node:
            return []

        nodes = [
            {
                "depth": depth,
                "operator": plan_node.get("operator", "Unknown"),
                "description": plan_node.get("description", ""),
                "estimated_rows": plan_node.get("estimated_rows"),
                "attributes": plan_node.get("attributes", {}),
            }
        ]

        # Placeholder: children are IDs in many Spark JSON plans
        for _child_id in plan_node.get("children", []):
            # Implement full tree traversal when the physical plan structure is finalized.
            pass

        return nodes

    # --------------------------------------------------------------------- #
    # Prompt building & response parsing
    # --------------------------------------------------------------------- #

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Build the user prompt with DAG, plan, and logical SQL context."""
        parts: List[str] = [
            "Analyze this Spark execution fingerprint and explain what the query does:\n"
        ]

        description = context.get("description")
        if description:
            parts.append(f"**Existing Description**: {description}\n")

        if "dag" in context:
            dag = context["dag"]
            parts.append(f"\n**Execution DAG** ({dag['total_stages']} stages):\n")
            for stage in dag.get("stages", []):
                shuffle_marker = " [SHUFFLE]" if stage.get("is_shuffle") else ""
                parts.append(
                    f"- Stage {stage['id']}: "
                    f"{stage.get('description', stage.get('name', 'N/A'))}"
                    f" ({stage.get('partitions', '?')} partitions){shuffle_marker}\n"
                )

            if dag.get("edges"):
                parts.append("\n**Stage Dependencies**:\n")
                for edge in dag["edges"]:
                    shuffle = " (shuffle)" if edge.get("shuffle_required") else ""
                    parts.append(
                        f"- Stage {edge['from_stage_id']} → Stage {edge['to_stage_id']}"
                        f": {edge.get('reason', 'dependency')}{shuffle}\n"
                    )

        if "physical_plan" in context:
            parts.append("\n**Physical Plan Operators**:\n")
            for node in context["physical_plan"]:
                indent = "  " * node["depth"]
                rows = (
                    f" (~{node['estimated_rows']} rows)"
                    if node.get("estimated_rows") is not None
                    else ""
                )
                parts.append(
                    f"{indent}- {node['operator']}: {node['description']}{rows}\n"
                )

        logical = context.get("logical_plan", {})
        if logical.get("is_sql"):
            plan_text = logical.get("plan_text", "")
            if plan_text:
                parts.append(f"\n**Logical Plan**:\n```\n{plan_text}\n```\n")

        return "".join(parts)

    def _parse_llm_response(
        self,
        llm_response: str,
        start_time: float,
    ) -> AgentResponse:
        """Parse LLM response into structured AgentResponse."""
        processing_time = int((time.time() - start_time) * 1000)

        lines = llm_response.strip().splitlines()
        summary_parts: List[str] = []
        key_findings: List[str] = []

        in_summary = False
        for line in lines:
            raw = line.rstrip("\n")
            trimmed = raw.strip()
            lower = trimmed.lower()

            # Summary section detection
            if "**summary**" in lower or lower.startswith("summary:"):
                in_summary = True
                if ":" in raw:
                    # Capture inline summary text after the first colon
                    summary_parts.append(raw.split(":", 1)[1].strip())
                continue

            if raw.startswith("**") and in_summary:
                # Next markdown section header ends the summary block
                in_summary = False

            if in_summary and trimmed:
                summary_parts.append(trimmed)

            # Generic bullet extraction as key findings
            if trimmed.startswith("- ") or trimmed.startswith("• "):
                finding = trimmed[2:].strip()
                if finding and len(finding) > 10:
                    key_findings.append(finding)

        if summary_parts:
            summary = " ".join(summary_parts).strip()
        else:
            summary = lines[0].strip() if lines else "Query analysis complete"

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary,
            explanation=llm_response,
            key_findings=key_findings[:10],
            confidence=0.85,
            processing_time_ms=processing_time,
            model_used=self.llm_config.model,
            suggested_followup_agents=[
                AgentType.OPTIMIZATION,
                AgentType.ROOT_CAUSE,
            ],
        )

    # --------------------------------------------------------------------- #
    # Rule-based fallback (no LLM)
    # --------------------------------------------------------------------- #

    async def analyze_without_llm(
        self,
        fingerprint_data: Dict[str, Any],
    ) -> AgentResponse:
        """
        Analyze fingerprint using only rule-based extraction (no LLM call).

        Useful for testing or when the LLM is unavailable.
        """
        start_time = time.time()

        try:
            semantic = self._extract_semantic(fingerprint_data)
            if not semantic:
                return self._create_error_response("No semantic data found")

            explanation_parts: List[str] = []
            key_findings: List[str] = []

            description = semantic.get("description", "")
            if description:
                explanation_parts.append(f"**Overview**: {description}")
                key_findings.append(description)

            if "dag" in semantic:
                dag = semantic["dag"]
                stages = dag.get("stages", [])
                explanation_parts.append(
                    f"\n**Execution Structure**: {len(stages)} stages"
                )

                shuffle_stages = [
                    s for s in stages if s.get("is_shuffle_stage")
                ]
                if shuffle_stages:
                    key_findings.append(
                        f"{len(shuffle_stages)} shuffle stages detected"
                    )

                for stage in stages:
                    desc = stage.get(
                        "description",
                        stage.get("stage_name", f"Stage {stage.get('stage_id')}"),
                    )
                    explanation_parts.append(
                        f"- Stage {stage.get('stage_id')}: {desc}"
                    )

            if semantic.get("physical_plan"):
                key_findings.append(
                    "SQL physical plan available for detailed analysis"
                )

            processing_time = int((time.time() - start_time) * 1000)

            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=description
                or "Query structure extracted (LLM analysis not performed)",
                explanation="\n".join(explanation_parts),
                key_findings=key_findings,
                confidence=0.60,
                processing_time_ms=processing_time,
            )

        except Exception as exc:  # noqa: BLE001
            return self._create_error_response(str(exc))
