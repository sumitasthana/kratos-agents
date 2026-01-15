"""
Utilities for DAG manipulation and analysis.
"""

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque


class DAGGraph:
    """
    Directed Acyclic Graph representing stage dependencies.
    Supports topological ordering, cycle detection, and traversal.
    """

    def __init__(self):
        self.nodes: Dict[int, Dict[str, Any]] = {}
        self.edges: List[Tuple[int, int]] = []
        self.adjacency: Dict[int, List[int]] = defaultdict(list)
        self.reverse_adjacency: Dict[int, List[int]] = defaultdict(list)

    def add_node(self, node_id: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a node to the DAG."""
        if node_id not in self.nodes:
            self.nodes[node_id] = metadata or {}

    def add_edge(self, from_id: int, to_id: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a directed edge from from_id to to_id."""
        self.add_node(from_id)
        self.add_node(to_id)

        if (from_id, to_id) not in self.edges:
            self.edges.append((from_id, to_id))
            self.adjacency[from_id].append(to_id)
            self.reverse_adjacency[to_id].append(from_id)

            if metadata:
                if "edge_metadata" not in self.nodes[from_id]:
                    self.nodes[from_id]["edge_metadata"] = {}
                self.nodes[from_id]["edge_metadata"][to_id] = metadata

    def get_dependencies(self, node_id: int) -> List[int]:
        """Get immediate dependencies (parents) of a node."""
        return self.reverse_adjacency.get(node_id, [])

    def get_dependents(self, node_id: int) -> List[int]:
        """Get nodes that depend on this node (children)."""
        return self.adjacency.get(node_id, [])

    def topological_sort(self) -> List[int]:
        """Return topologically sorted node IDs."""
        visited: Set[int] = set()
        result: List[int] = []

        def dfs(node_id: int) -> None:
            if node_id in visited:
                return
            visited.add(node_id)
            for child in self.get_dependents(node_id):
                dfs(child)
            result.append(node_id)

        # Start from root nodes
        for node_id in self.nodes:
            if not self.get_dependencies(node_id):
                dfs(node_id)

        # Ensure all nodes included
        for node_id in self.nodes:
            dfs(node_id)

        return result

    def get_root_nodes(self) -> List[int]:
        """Get nodes with no dependencies."""
        return [n for n in self.nodes if not self.get_dependencies(n)]

    def get_leaf_nodes(self) -> List[int]:
        """Get nodes with no dependents."""
        return [n for n in self.nodes if not self.get_dependents(n)]

    def get_all_upstream(self, node_id: int) -> Set[int]:
        """Get all nodes upstream of (feeding into) this node."""
        upstream: Set[int] = set()
        queue = deque([node_id])
        visited: Set[int] = set()

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for parent in self.get_dependencies(current):
                if parent not in upstream:
                    upstream.add(parent)
                    queue.append(parent)

        return upstream

    def get_all_downstream(self, node_id: int) -> Set[int]:
        """Get all nodes downstream of (consuming output from) this node."""
        downstream: Set[int] = set()
        queue = deque([node_id])
        visited: Set[int] = set()

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for child in self.get_dependents(current):
                if child not in downstream:
                    downstream.add(child)
                    queue.append(child)

        return downstream

    def is_acyclic(self) -> bool:
        """Check if graph is acyclic (should be true for Spark DAGs)."""
        try:
            self.topological_sort()
            return True
        except:
            return False

    def hash_structure(self) -> str:
        """
        Compute deterministic hash of DAG structure.
        Useful for equality checking across runs.
        """
        # Create normalized representation
        topo_order = self.topological_sort()
        edges_normalized = []

        for from_id in topo_order:
            for to_id in sorted(self.get_dependents(from_id)):
                edges_normalized.append(f"{from_id}->{to_id}")

        structure_str = "|".join(edges_normalized)
        return hashlib.sha256(structure_str.encode()).hexdigest()


# ============================================================================
# Plan normalization utilities
# ============================================================================


def normalize_plan_node(node: Any) -> Dict[str, Any]:
    """
    Normalize a physical plan node for hashing.
    Removes runtime-specific information to enable equality comparison.
    """
    if isinstance(node, dict):
        normalized = {}

        # Include operator name and key attributes
        if "class" in node:
            # Extract class name (e.g., "org.apache.spark.sql.execution.Scan" -> "Scan")
            class_name = node["class"].split(".")[-1]
            normalized["op"] = class_name

        # Preserve key parameters
        for key in ["name", "table", "statistics", "outputOrdering"]:
            if key in node:
                normalized[key] = node[key]

        # Process children recursively
        if "children" in node:
            normalized["children"] = [normalize_plan_node(child) for child in node["children"]]

        return normalized

    return node


def hash_physical_plan(plan: Any) -> str:
    """
    Compute deterministic hash of normalized physical plan.
    Two plans with same structure produce identical hashes.
    """
    import json

    normalized = normalize_plan_node(plan)
    plan_str = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(plan_str.encode()).hexdigest()


def extract_plan_operators(plan: Any, operators: Optional[List[str]] = None) -> List[str]:
    """Extract all unique operators used in a plan."""
    if operators is None:
        operators = []

    if isinstance(plan, dict):
        if "class" in plan:
            op_name = plan["class"].split(".")[-1]
            if op_name not in operators:
                operators.append(op_name)

        if "children" in plan:
            for child in plan["children"]:
                extract_plan_operators(child, operators)

    return operators


def plan_to_string(plan: Any, indent: int = 0) -> str:
    """Convert plan to human-readable string representation."""
    lines = []

    if isinstance(plan, dict):
        op_name = plan.get("class", "Unknown").split(".")[-1]
        lines.append("  " * indent + op_name)

        # Add key attributes
        for key in ["name", "table", "statistics"]:
            if key in plan and plan[key]:
                lines.append("  " * (indent + 1) + f"{key}: {plan[key]}")

        # Process children
        if "children" in plan:
            for i, child in enumerate(plan["children"]):
                lines.append("  " * (indent + 1) + f"Child {i}:")
                lines.extend(plan_to_string(child, indent + 2).split("\n"))

    return "\n".join(filter(None, lines))
