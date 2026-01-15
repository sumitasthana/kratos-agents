"""
Semantic Fingerprint Generator

Extracts DAG structure, physical plan, and produces deterministic semantic hash.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

from src.schemas import (
    DAGEdge,
    ExecutionDAG,
    LogicalPlanHash,
    PhysicalPlanNode,
    SemanticFingerprint,
    StageNode,
)
from src.parser import EventLogParser, SparkEvent, EventIndex
from src.dag_utils import DAGGraph, normalize_plan_node, hash_physical_plan, plan_to_string


class SemanticFingerprintGenerator:
    """
    Generates semantic fingerprint from event log.
    Deterministic - produces same hash for identical DAG structures across runs.
    """

    def __init__(self, event_log_path: str):
        self.event_log_path = event_log_path
        self.parser = EventLogParser(event_log_path)
        self.events, _ = self.parser.parse()
        self.index = EventIndex(self.events)

    def generate(self) -> SemanticFingerprint:
        """
        Generate complete semantic fingerprint from event log.

        Returns:
            SemanticFingerprint with DAG, physical plan, and hash
        """
        # Build execution DAG
        dag = self._extract_dag()

        # Extract physical plan (SQL only)
        physical_plan = None
        plan_hash_obj = None
        is_sql = False

        sql_events = self.index.get_by_type("SparkListenerSQLExecutionStart")
        if sql_events:
            is_sql = True
            physical_plan_raw = self._extract_physical_plan(sql_events[0])
            if physical_plan_raw:
                physical_plan = self._normalize_plan_node(physical_plan_raw)

        # Compute logical plan hash
        plan_hash_obj = self._compute_logical_plan_hash(physical_plan, dag, is_sql)

        # Compute semantic hash
        semantic_hash = self._compute_semantic_hash(dag, plan_hash_obj)

        # Generate description
        description = self._generate_description(dag, physical_plan, is_sql)

        # Evidence sources
        evidence = self._collect_evidence()

        return SemanticFingerprint(
            dag=dag,
            physical_plan=physical_plan,
            logical_plan_hash=plan_hash_obj,
            semantic_hash=semantic_hash,
            description=description,
            evidence_sources=evidence,
        )

    def _extract_dag(self) -> ExecutionDAG:
        """Extract stage DAG from event log."""
        dag = DAGGraph()
        stage_info: Dict[int, Dict[str, Any]] = {}

        # Build nodes from stage completion events
        for event in self.index.get_by_type("SparkListenerStageCompleted"):
            stage_info_dict = event.get("Stage Info", {})
            stage_id = stage_info_dict.get("Stage ID")
            if stage_id is not None:
                stage_info[stage_id] = stage_info_dict

                metadata = {
                    "num_partitions": stage_info_dict.get("Number of Tasks", 0),
                    "is_shuffle": self._is_shuffle_stage(stage_info_dict),
                    "rdd_name": stage_info_dict.get("RDD Info", [{}])[0].get("Name"),
                    "stage_name": stage_info_dict.get("Stage Name", f"Stage {stage_id}"),
                }
                dag.add_node(stage_id, metadata)

        # Add edges (dependencies)
        for stage_id, stage_dict in stage_info.items():
            parent_stages = stage_dict.get("Parent IDs", [])
            for parent_id in parent_stages:
                reason = self._infer_dependency_reason(stage_info.get(parent_id, {}), stage_dict)
                has_shuffle = self._is_shuffle_stage(stage_dict)

                dag.add_edge(
                    parent_id,
                    stage_id,
                    metadata={"shuffle_required": has_shuffle, "reason": reason},
                )

        # Convert to SemanticFingerprint DAG format
        stage_nodes = []
        root_stages = dag.get_root_nodes()
        leaf_stages = dag.get_leaf_nodes()

        for stage_id in dag.topological_sort():
            if stage_id in stage_info:
                node_meta = dag.nodes[stage_id]
                stage_nodes.append(
                    StageNode(
                        stage_id=stage_id,
                        stage_name=node_meta.get("stage_name", f"Stage {stage_id}"),
                        num_partitions=node_meta.get("num_partitions", 0),
                        is_shuffle_stage=node_meta.get("is_shuffle", False),
                        rdd_name=node_meta.get("rdd_name"),
                        description=self._describe_stage(stage_info[stage_id]),
                    )
                )

        # Convert edges
        edges = []
        for from_id, to_id in dag.edges:
            edge_meta = dag.nodes[from_id].get("edge_metadata", {}).get(to_id, {})
            edges.append(
                DAGEdge(
                    from_stage_id=from_id,
                    to_stage_id=to_id,
                    shuffle_required=edge_meta.get("shuffle_required", False),
                    reason=edge_meta.get("reason", "Unknown"),
                )
            )

        return ExecutionDAG(
            stages=stage_nodes,
            edges=edges,
            root_stage_ids=root_stages,
            leaf_stage_ids=leaf_stages,
            total_stages=len(stage_nodes),
        )

    def _extract_physical_plan(self, sql_event: SparkEvent) -> Optional[Dict[str, Any]]:
        """Extract physical plan from SQL execution event."""
        return sql_event.get("Physical Plan")

    def _normalize_plan_node(self, plan: Any, node_id: Optional[str] = None) -> PhysicalPlanNode:
        """Convert raw plan node to normalized PhysicalPlanNode."""
        if not node_id:
            node_id = "root"

        normalized = normalize_plan_node(plan)

        return PhysicalPlanNode(
            node_id=node_id,
            operator=normalized.get("op", "Unknown"),
            estimated_rows=normalized.get("statistics", {}).get("row count"),
            estimated_bytes=normalized.get("statistics", {}).get("total size"),
            attributes=normalized,
            children=[f"child_{i}" for i in range(len(normalized.get("children", [])))],
            description=self._describe_plan_operator(plan),
        )

    def _compute_logical_plan_hash(
        self, physical_plan: Optional[PhysicalPlanNode], dag: ExecutionDAG, is_sql: bool
    ) -> LogicalPlanHash:
        """Compute hash of logical/physical plan structure."""
        # For SQL: hash the physical plan
        if is_sql and physical_plan:
            plan_hash = hash_physical_plan(physical_plan.attributes)
        else:
            # For RDD: hash the DAG structure
            plan_hash = dag.hash_structure() if hasattr(dag, "hash_structure") else "no_hash"

        # Build plan text for verification
        if is_sql and physical_plan:
            plan_text = self._plan_to_text(physical_plan)
        else:
            plan_text = self._dag_to_text(dag)

        return LogicalPlanHash(
            plan_hash=plan_hash,
            plan_text=plan_text,
            is_sql=is_sql,
        )

    def _compute_semantic_hash(self, dag: ExecutionDAG, plan_hash: LogicalPlanHash) -> str:
        """
        Compute final semantic hash combining DAG structure and plan.
        Deterministic across runs - identical executions produce identical hash.
        """
        combined = {
            "dag_structure": self._dag_structure_string(dag),
            "plan_hash": plan_hash.plan_hash,
            "stage_count": dag.total_stages,
        }

        combined_str = json.dumps(combined, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(combined_str.encode()).hexdigest()

    def _is_shuffle_stage(self, stage_info: Dict[str, Any]) -> bool:
        """Determine if stage involves shuffle."""
        # Check for shuffle-related RDD names or parent count > 0
        rdd_info = stage_info.get("RDD Info", [])
        for rdd in rdd_info:
            if "shuffle" in rdd.get("Name", "").lower():
                return True
        return len(stage_info.get("Parent IDs", [])) > 0

    def _infer_dependency_reason(
        self, parent_stage: Dict[str, Any], child_stage: Dict[str, Any]
    ) -> str:
        """Infer reason for dependency based on RDD info."""
        parent_rdd = parent_stage.get("RDD Info", [])
        child_rdd = child_stage.get("RDD Info", [])

        if parent_rdd and child_rdd:
            parent_name = parent_rdd[0].get("Name", "")
            if "shuffle" in parent_name.lower():
                return "shuffle_dependency"

        return "data_dependency"

    def _describe_stage(self, stage_info: Dict[str, Any]) -> str:
        """Generate human-readable description of stage."""
        stage_id = stage_info.get("Stage ID", "?")
        num_tasks = stage_info.get("Number of Tasks", 0)
        rdd_info = stage_info.get("RDD Info", [])
        rdd_name = rdd_info[0].get("Name", "Unknown") if rdd_info else "Unknown"

        return f"Stage {stage_id}: {rdd_name} ({num_tasks} tasks)"

    def _describe_plan_operator(self, plan: Any) -> str:
        """Generate description of a plan operator."""
        if isinstance(plan, dict):
            op = plan.get("class", "Unknown").split(".")[-1]
            name = plan.get("name", "")
            if name:
                return f"{op} on {name}"
            return op
        return "Unknown"

    def _dag_structure_string(self, dag: ExecutionDAG) -> str:
        """Generate normalized string representation of DAG."""
        parts = []
        for edge in dag.edges:
            parts.append(f"{edge.from_stage_id}->{edge.to_stage_id}")
        return "|".join(sorted(parts))

    def _plan_to_text(self, plan_node: PhysicalPlanNode, indent: int = 0) -> str:
        """Convert plan node to text representation."""
        lines = ["  " * indent + f"[{plan_node.operator}] {plan_node.description}"]
        for child_id in plan_node.children:
            lines.append("  " * (indent + 1) + f"-> {child_id}")
        return "\n".join(lines)

    def _dag_to_text(self, dag: ExecutionDAG) -> str:
        """Convert DAG to text representation."""
        lines = []
        for stage in dag.stages:
            lines.append(f"Stage {stage.stage_id}: {stage.description}")
            for edge in dag.edges:
                if edge.to_stage_id == stage.stage_id:
                    lines.append(f"  <- Stage {edge.from_stage_id} ({edge.reason})")
        return "\n".join(lines)

    def _generate_description(
        self, dag: ExecutionDAG, physical_plan: Optional[PhysicalPlanNode], is_sql: bool
    ) -> str:
        """Generate natural language description of execution."""
        parts = []

        if is_sql and physical_plan:
            parts.append(f"SQL query with {len(dag.stages)} stages")
        else:
            parts.append(f"RDD/DataFrame job with {len(dag.stages)} stages")

        # Summarize operation
        shuffle_stages = sum(1 for s in dag.stages if s.is_shuffle_stage)
        if shuffle_stages > 0:
            parts.append(f"{shuffle_stages} shuffle stages")

        total_partitions = sum(s.num_partitions for s in dag.stages)
        parts.append(f"{total_partitions} total partitions")

        return "; ".join(parts)

    def _collect_evidence(self) -> List[str]:
        """Collect event IDs supporting semantic fingerprint."""
        evidence = []

        # Reference to stage events
        for event in self.index.get_by_type("SparkListenerStageCompleted"):
            stage_id = event.get("Stage Info", {}).get("Stage ID")
            if stage_id is not None:
                evidence.append(f"StageCompleted[{stage_id}]")

        # Reference to SQL events if present
        for event in self.index.get_by_type("SparkListenerSQLExecutionStart"):
            sql_id = event.get("Execution ID")
            evidence.append(f"SQLExecution[{sql_id}]")

        return evidence[:20]  # Limit to top 20
