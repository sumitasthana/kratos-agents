# agents/infra_analyzer_agent.py
"""
InfraAnalyzerAgent — infrastructure / observability RCA agent.

Accepts a flexible fingerprint_data dict describing cluster or node-level
metrics and surfaces resource saturation signals.

Expected fingerprint_data shape (all keys optional beyond "cluster_id"):

    {
      "cluster_id":        "prod-spark-01",
      "environment":       "production",
      "time_window":       "2026-02-25T08:00:00Z / 2026-02-25T09:00:00Z",

      # Utilization (0-100 %)
      "cpu_utilization":      78.4,
      "memory_utilization":   91.2,
      "disk_io_utilization":  45.0,
      "network_io_utilization": 22.0,

      # Worker / executor counts
      "total_workers":        20,
      "available_workers":    14,
      "queued_tasks":         350,

      # Autoscaling
      "autoscale_events": [
        {"direction": "down", "delta": 4, "timestamp": "2026-02-25T08:30:00Z"},
        ...
      ],

      # Alert / error counts from monitoring
      "alert_count":    5,
      "error_count":    12,

      # Optional per-node breakdown (list of dicts)
      "nodes": [
        {"node_id": "n-01", "cpu": 95.1, "memory": 88.2, "role": "executor"},
        ...
      ]
    }

All keys are treated as optional.  Missing numeric fields default to 0.0.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent, AgentType
from agents import AgentResponse, LLMConfig
from prompt_loader import load_prompt_content


class InfraAnalyzerAgent(BaseAgent):
    """
    Analyse infrastructure / observability metrics from a cluster fingerprint.

    Heuristics used (no LLM needed by default):
      - CPU utilization   ≥ 85 %  → HIGH pressure
      - Memory utilization ≥ 90 % → CRITICAL pressure
      - Queued tasks      ≥ 200   → capacity risk
      - Available workers < 50 %  → executor loss / scaling event
      - Any autoscale "down" event → cluster shrinkage
    """

    agent_type: AgentType = AgentType.INFRA_ANALYZER
    agent_name: str = "Infra Analyzer"

    @property
    def description(self) -> str:
        return (
            "Analyzes cluster infrastructure and observability metrics — CPU, memory, "
            "disk and network I/O, worker capacity, task queue depth, and autoscaling "
            "events — to surface resource saturation and capacity risk."
        )

    @property
    def system_prompt(self) -> str:
        # Loaded from prompts/infra_analyzer.yaml
        return load_prompt_content("infra_analyzer")

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        super().__init__(llm_config or LLMConfig())

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        **_: Any,
    ) -> AgentResponse:
        try:
            parsed = self._parse_fingerprint(fingerprint_data)
        except Exception as exc:
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=False,
                summary=f"Failed to parse infra fingerprint: {exc}",
                explanation=str(exc),
                key_findings=[],
                confidence=0.3,
                metadata={"error": str(exc)},
            )

        findings: List[str] = []
        sections: List[str] = []

        # ── CPU ──────────────────────────────────────────────────────────
        cpu_lines, cpu_findings = self._analyze_cpu(parsed)
        sections.append("## CPU\n\n" + "\n".join(cpu_lines))
        findings.extend(cpu_findings)

        # ── Memory ───────────────────────────────────────────────────────
        mem_lines, mem_findings = self._analyze_memory(parsed)
        sections.append("\n\n## Memory\n\n" + "\n".join(mem_lines))
        findings.extend(mem_findings)

        # ── Capacity (workers / queued tasks) ─────────────────────────────
        cap_lines, cap_findings = self._analyze_capacity(parsed)
        sections.append("\n\n## Capacity\n\n" + "\n".join(cap_lines))
        findings.extend(cap_findings)

        # ── Autoscaling ───────────────────────────────────────────────────
        asg_lines, asg_findings = self._analyze_autoscaling(parsed)
        sections.append("\n\n## Autoscaling\n\n" + "\n".join(asg_lines))
        findings.extend(asg_findings)

        # ── Network / Disk I/O ────────────────────────────────────────────
        net_lines, net_findings = self._analyze_io(parsed)
        sections.append("\n\n## Network & Disk I/O\n\n" + "\n".join(net_lines))
        findings.extend(net_findings)

        # ── Alerts / errors ───────────────────────────────────────────────
        alert_lines, alert_findings = self._analyze_alerts(parsed)
        sections.append("\n\n## Alerts & Errors\n\n" + "\n".join(alert_lines))
        findings.extend(alert_findings)

        severity, health_label, confidence = self._score_health(findings)

        cluster_id  = parsed["cluster_id"]
        environment = parsed["environment"]
        summary = (
            f"Infra analysis for cluster '{cluster_id}' ({environment}): "
            f"{health_label}."
        )
        explanation = "\n".join(sections).strip()

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary,
            explanation=explanation,
            key_findings=findings,
            confidence=confidence,
            metadata={
                "cluster_id":          cluster_id,
                "environment":         environment,
                "severity":            severity,
                "health_label":        health_label,
                "cpu_utilization":     parsed["cpu_utilization"],
                "memory_utilization":  parsed["memory_utilization"],
                "queued_tasks":        parsed["queued_tasks"],
                "available_workers":   parsed["available_workers"],
                "total_workers":       parsed["total_workers"],
            },
        )

    # ------------------------------------------------------------------ #
    # Parser
    # ------------------------------------------------------------------ #

    def _parse_fingerprint(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def _float(key: str, default: float = 0.0) -> float:
            try:
                return float(data.get(key) or default)
            except (TypeError, ValueError):
                return default

        def _int(key: str, default: int = 0) -> int:
            try:
                return int(data.get(key) or default)
            except (TypeError, ValueError):
                return default

        return {
            "cluster_id":              str(data.get("cluster_id") or "unknown"),
            "environment":             str(data.get("environment") or "unknown"),
            "time_window":             str(data.get("time_window") or ""),
            "cpu_utilization":         _float("cpu_utilization"),
            "memory_utilization":      _float("memory_utilization"),
            "disk_io_utilization":     _float("disk_io_utilization"),
            "network_io_utilization":  _float("network_io_utilization"),
            "total_workers":           _int("total_workers"),
            "available_workers":       _int("available_workers"),
            "queued_tasks":            _int("queued_tasks"),
            "autoscale_events":        list(data.get("autoscale_events") or []),
            "alert_count":             _int("alert_count"),
            "error_count":             _int("error_count"),
            "nodes":                   list(data.get("nodes") or []),
        }

    # ------------------------------------------------------------------ #
    # Heuristic analyzers
    # ------------------------------------------------------------------ #

    def _analyze_cpu(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        cpu = p["cpu_utilization"]
        lines: List[str] = [f"- Cluster avg CPU utilization: **{cpu:.1f}%**"]
        findings: List[str] = []

        if cpu >= 95:
            findings.append(f"CRITICAL: CPU utilization at {cpu:.1f}% — cluster at full capacity")
        elif cpu >= 85:
            findings.append(f"HIGH: Elevated CPU utilization ({cpu:.1f}%) — capacity risk")
        elif cpu >= 70:
            findings.append(f"MEDIUM: CPU utilization moderately high ({cpu:.1f}%)")

        # Per-node hot spots
        hot_nodes = [
            n for n in p["nodes"]
            if float(n.get("cpu", 0)) >= 90
        ]
        if hot_nodes:
            node_ids = [str(n.get("node_id", "?")) for n in hot_nodes[:5]]
            lines.append(f"- Hot nodes (≥90% CPU): {', '.join(node_ids)}")
            findings.append(
                f"HIGH: {len(hot_nodes)} node(s) running at ≥90% CPU: "
                f"{', '.join(node_ids)}"
            )

        return lines, findings

    def _analyze_memory(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        mem = p["memory_utilization"]
        lines: List[str] = [f"- Cluster avg memory utilization: **{mem:.1f}%**"]
        findings: List[str] = []

        if mem >= 92:
            findings.append(f"CRITICAL: Memory utilization at {mem:.1f}% — imminent OOM risk")
        elif mem >= 80:
            findings.append(f"HIGH: Memory pressure detected ({mem:.1f}%)")
        elif mem >= 70:
            findings.append(f"MEDIUM: Memory utilization elevated ({mem:.1f}%)")

        hot_nodes = [
            n for n in p["nodes"]
            if float(n.get("memory", 0)) >= 90
        ]
        if hot_nodes:
            node_ids = [str(n.get("node_id", "?")) for n in hot_nodes[:5]]
            lines.append(f"- High-memory nodes (≥90%): {', '.join(node_ids)}")
            findings.append(
                f"HIGH: {len(hot_nodes)} node(s) at ≥90% memory: "
                f"{', '.join(node_ids)}"
            )

        return lines, findings

    def _analyze_capacity(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        total     = p["total_workers"]
        avail     = p["available_workers"]
        queued    = p["queued_tasks"]
        lines: List[str] = [
            f"- Workers: {avail}/{total} available",
            f"- Queued tasks: {queued}",
        ]
        findings: List[str] = []

        if total > 0:
            pct_avail = avail / total * 100
            if pct_avail < 25:
                findings.append(
                    f"CRITICAL: Only {avail}/{total} workers available ({pct_avail:.0f}%) — "
                    "severe executor loss"
                )
            elif pct_avail < 50:
                findings.append(
                    f"HIGH: {avail}/{total} workers available ({pct_avail:.0f}%) — "
                    "cluster capacity degraded"
                )

        if queued >= 500:
            findings.append(f"CRITICAL: {queued} tasks queued — backlog critical")
        elif queued >= 200:
            findings.append(f"HIGH: Large task backlog ({queued} queued)")
        elif queued >= 50:
            findings.append(f"MEDIUM: Task queue building up ({queued} queued)")

        return lines, findings

    def _analyze_autoscaling(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        events = p["autoscale_events"]
        lines: List[str] = [f"- Autoscale events in window: {len(events)}"]
        findings: List[str] = []

        down_events = [e for e in events if str(e.get("direction", "")).lower() == "down"]
        up_events   = [e for e in events if str(e.get("direction", "")).lower() == "up"]

        if down_events:
            total_shrink = sum(int(e.get("delta", 0)) for e in down_events)
            lines.append(f"- Scale-down events: {len(down_events)} (−{total_shrink} workers total)")
            findings.append(
                f"HIGH: Cluster scaled DOWN {len(down_events)} time(s), "
                f"removing {total_shrink} worker(s) during the analysis window"
            )
        if up_events:
            total_grow = sum(int(e.get("delta", 0)) for e in up_events)
            lines.append(f"- Scale-up events: {len(up_events)} (+{total_grow} workers)")

        return lines, findings

    def _analyze_io(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        disk    = p["disk_io_utilization"]
        network = p["network_io_utilization"]
        lines: List[str] = [
            f"- Disk I/O utilization: {disk:.1f}%",
            f"- Network I/O utilization: {network:.1f}%",
        ]
        findings: List[str] = []

        if disk >= 90:
            findings.append(f"HIGH: Disk I/O saturation ({disk:.1f}%) — spill/shuffle at risk")
        elif disk >= 75:
            findings.append(f"MEDIUM: Elevated disk I/O ({disk:.1f}%)")

        if network >= 85:
            findings.append(f"HIGH: Network I/O saturation ({network:.1f}%) — shuffle overhead likely")
        elif network >= 65:
            findings.append(f"MEDIUM: Elevated network I/O ({network:.1f}%)")

        return lines, findings

    def _analyze_alerts(
        self, p: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        alerts = p["alert_count"]
        errors = p["error_count"]
        lines: List[str] = [
            f"- Monitoring alerts: {alerts}",
            f"- Error events: {errors}",
        ]
        findings: List[str] = []

        if errors >= 50:
            findings.append(f"CRITICAL: {errors} error events from monitoring")
        elif errors >= 10:
            findings.append(f"HIGH: {errors} error events recorded in window")

        if alerts >= 10:
            findings.append(f"HIGH: {alerts} monitoring alerts triggered")
        elif alerts >= 3:
            findings.append(f"MEDIUM: {alerts} monitoring alerts active")

        return lines, findings

    # ------------------------------------------------------------------ #
    # Health scoring
    # ------------------------------------------------------------------ #

    def _score_health(
        self, findings: List[str]
    ) -> Tuple[str, str, float]:
        """
        Returns (severity, health_label, confidence).
        severity  : "low" | "medium" | "high" | "critical"
        health_label: human-readable label
        confidence: 0–1
        """
        critical = sum(1 for f in findings if f.startswith("CRITICAL"))
        high     = sum(1 for f in findings if f.startswith("HIGH"))
        medium   = sum(1 for f in findings if f.startswith("MEDIUM"))

        if critical >= 1:
            return "critical", "Critical Resource Pressure",  0.88
        if high >= 2:
            return "high",     "Severe Resource Stress",       0.80
        if high == 1:
            return "high",     "Resource Pressure Detected",   0.75
        if medium >= 1:
            return "medium",   "Moderate Resource Utilisation", 0.65
        return "low", "Infrastructure Healthy", 0.60
