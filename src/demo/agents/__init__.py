"""
src/demo/agents

Demo-specific reasoning agents that extend BaseReasoningAgent.
These call Claude claude-sonnet-4-6 with structured prompts and stream chain-of-thought
to the SSE queue as AGENT_THOUGHT events.

Agents:
  DemoEvidenceAgent      — LOGS_FIRST phase (log classification)
  DemoBacktrackingAgent  — BACKTRACK phase (per-hop ontology walk)
  DemoRankerAgent        — PERSIST phase (confidence scoring)
  DemoRoutingAgent       — ROUTE phase (pattern matching)
  DemoIncidentAgent      — INCIDENT_CARD phase (incident synthesis)
  DemoRecommendAgent     — RECOMMEND phase (remediation actions)
"""
