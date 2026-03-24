"""
tools/views/cypher_views.py
Pre-built parameterized Cypher queries for Neo4j ontology traversal.

All functions return raw Cypher strings ready to be executed via a Neo4j
driver (``session.run(cypher, **params)``).  Use named parameters in the
Cypher text where possible so callers can pass them safely.
"""
from __future__ import annotations


def trace_code_path(script_name: str, max_hops: int = 5) -> str:
    """Return Cypher to trace the ontology path originating from a named script.

    Args:
        script_name: Exact ``name`` property of the source ``Script`` node.
        max_hops:    Maximum relationship depth to traverse (default 5).

    Returns:
        Cypher string.  Run with ``{script_name: script_name}`` params.
    """
    return (
        f"MATCH path = (s:Script {{name: $script_name}})-[*1..{max_hops}]->(n) "
        "RETURN path, nodes(path) AS nodes, relationships(path) AS rels "
        "ORDER BY length(path) ASC"
    )


def find_control_failures(control_id: str | None = None) -> str:
    """Return Cypher to find all control nodes with FAILED status.

    Args:
        control_id: Optional specific control ID to filter on.

    Returns:
        Cypher string.  Run with ``{control_id: control_id}`` if filtering.
    """
    if control_id:
        return (
            "MATCH (c:Control {id: $control_id}) "
            "WHERE c.status = 'FAILED' OR c.status = 'VIOLATED' "
            "OPTIONAL MATCH (c)-[:TRIGGERED_BY]->(evt:Event) "
            "RETURN c, collect(evt) AS triggering_events"
        )
    return (
        "MATCH (c:Control) "
        "WHERE c.status = 'FAILED' OR c.status = 'VIOLATED' "
        "OPTIONAL MATCH (c)-[:TRIGGERED_BY]->(evt:Event) "
        "RETURN c, collect(evt) AS triggering_events "
        "ORDER BY c.severity DESC"
    )


def get_ontology_subgraph(node_id: str, depth: int = 3) -> str:
    """Return Cypher to fetch the full subgraph around a given node ID.

    Args:
        node_id: The ``id`` property of the center node.
        depth:   Hop radius (default 3).

    Returns:
        Cypher string.  Run with ``{node_id: node_id}`` params.
    """
    return (
        f"MATCH path = (n {{id: $node_id}})-[*0..{depth}]-(neighbor) "
        "RETURN path, nodes(path) AS nodes, relationships(path) AS rels"
    )


def dependency_chain(job_id: str) -> str:
    """Return Cypher to trace the upstream dependency chain for a pipeline job.

    Args:
        job_id: The ``job_id`` property of the terminal ``Job`` node.

    Returns:
        Cypher string.  Run with ``{job_id: job_id}`` params.
    """
    return (
        "MATCH path = (j:Job {job_id: $job_id})<-[:FEEDS*1..10]-(upstream) "
        "RETURN path, nodes(path) AS nodes, relationships(path) AS rels "
        "ORDER BY length(path) ASC"
    )


def lineage_from_table(table_name: str, max_hops: int = 6) -> str:
    """Return Cypher to walk data lineage downstream from a source table.

    Args:
        table_name: Exact ``name`` property of the source ``Table`` node.
        max_hops:   Maximum downstream hops (default 6).

    Returns:
        Cypher string.  Run with ``{table_name: table_name}`` params.
    """
    return (
        f"MATCH path = (t:Table {{name: $table_name}})-[:FEEDS|READS|WRITES*1..{max_hops}]->(downstream) "
        "RETURN path, nodes(path) AS nodes, relationships(path) AS rels "
        "ORDER BY length(path) ASC"
    )


def incident_blast_radius(incident_id: str, depth: int = 4) -> str:
    """Return Cypher to identify all nodes affected by a given incident.

    Args:
        incident_id: The ``incident_id`` property of the ``Incident`` node.
        depth:       Propagation depth (default 4).

    Returns:
        Cypher string.  Run with ``{incident_id: incident_id}`` params.
    """
    return (
        f"MATCH path = (i:Incident {{incident_id: $incident_id}})-[:AFFECTS|PROPAGATES_TO*1..{depth}]->(n) "
        "RETURN path, nodes(path) AS nodes, relationships(path) AS rels, "
        "labels(n) AS node_types "
        "ORDER BY length(path) ASC"
    )

