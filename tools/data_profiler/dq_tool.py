# Moved from: src\agents\data_profiler_agent.py
# Import updates applied by migrate step.
# agents/data_profiler_agent.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.base_agent import BaseAgent, AgentType
from core.base_agent import AgentResponse
from core.llm import LLMConfig


class DataProfilerAgent(BaseAgent):
    """
    RCA-oriented Data Profiler agent.

    Takes a generic, JSON-serializable fingerprint payload:

        {
          "dataset_name": "prices_daily",
          "row_count": 123456,
          "columns": [
            {
              "name": "price",
              "dtype": "float64",
              "null_rate": 0.01,
              "...": "other optional stats"
            },
            ...
          ],
          "reference": {  # optional baseline
            "dataset_name": "prices_daily_baseline",
            "row_count": ...,
            "columns": [...]
          }
        }

    It does NOT assume any hard-coded schema beyond:
      - columns[*]["name"]
      - columns[*]["dtype"]
      - columns[*]["null_rate"]

    All other keys are treated as optional metadata and used only if present
    (e.g., "distinct_count", "mean").
    """

    agent_type: AgentType = AgentType.DATA_PROFILER
    agent_name: str = "Data Profiler"

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
                summary=f"Failed to parse data fingerprint: {exc}",
                explanation=str(exc),
                key_findings=[],
                confidence=0.3,
                metadata={"error": str(exc)},
            )

        dataset_name = parsed["dataset_name"]
        row_count = parsed["row_count"]
        columns = parsed["columns"]
        reference = parsed["reference"]

        findings: List[str] = []
        explanation_sections: List[str] = []

        # 1) Current dataset summary
        summary_lines, health_flags = self._summarize_current(row_count, columns)
        explanation_sections.append("## Dataset summary\n\n" + "\n".join(summary_lines))

        # 2) Compare with reference if provided
        drift_findings: List[str] = []
        if reference is not None:
            drift_lines, drift_findings = self._compare_with_reference(columns, reference)
            explanation_sections.append(
                "\n\n## Drift vs reference\n\n" + "\n".join(drift_lines)
            )

        findings.extend(health_flags)
        findings.extend(drift_findings)

        # 3) Severity / health classification
        severity, health_label, confidence = self._score_health(
            health_flags, drift_findings
        )

        summary = (
            f"Data profile for dataset '{dataset_name}': "
            f"{health_label} (rows={row_count}, cols={len(columns)})."
        )
        explanation = "\n".join(explanation_sections).strip()

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary,
            explanation=explanation,
            key_findings=findings,
            confidence=confidence,
            metadata={
                "dataset_name": dataset_name,
                "row_count": row_count,
                "severity": severity,
                "health_label": health_label,
            },
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _parse_fingerprint(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize fingerprint payload without enforcing a rigid schema.

        Returns:
            {
              "dataset_name": str,
              "row_count": int,
              "columns": List[Dict[str, Any]],
              "reference": Optional[Dict[str, Any]]  # same shape as current
            }
        """
        dataset_name = str(data.get("dataset_name") or "dataset")
        row_count = int(data.get("row_count") or 0)

        cols_raw = data.get("columns") or []
        columns: List[Dict[str, Any]] = []

        for raw in cols_raw:
            name = raw.get("name")
            if not name:
                # skip unnamed columns
                continue
            col = {
                "name": str(name),
                "dtype": str(raw.get("dtype", "unknown")),
                "null_rate": float(raw.get("null_rate", 0.0)),
            }
            # preserve any extra stats if present
            for k, v in raw.items():
                if k in col:
                    continue
                col[k] = v
            columns.append(col)

        reference = None
        if data.get("reference"):
            ref = data["reference"]
            ref_cols_raw = ref.get("columns") or []
            ref_cols: List[Dict[str, Any]] = []
            for raw in ref_cols_raw:
                name = raw.get("name")
                if not name:
                    continue
                col = {
                    "name": str(name),
                    "dtype": str(raw.get("dtype", "unknown")),
                    "null_rate": float(raw.get("null_rate", 0.0)),
                }
                for k, v in raw.items():
                    if k in col:
                        continue
                    col[k] = v
                ref_cols.append(col)

            reference = {
                "dataset_name": str(ref.get("dataset_name") or f"{dataset_name}_reference"),
                "row_count": int(ref.get("row_count") or 0),
                "columns": ref_cols,
            }

        return {
            "dataset_name": dataset_name,
            "row_count": row_count,
            "columns": columns,
            "reference": reference,
        }

    def _summarize_current(
        self,
        row_count: int,
        columns: List[Dict[str, Any]],
    ) -> Tuple[List[str], List[str]]:
        lines: List[str] = []
        findings: List[str] = []

        lines.append(f"- Rows: {row_count}")
        lines.append(f"- Columns: {len(columns)}")

        # Null summary (only uses null_rate if present)
        high_null_cols = [
            c for c in columns if float(c.get("null_rate", 0.0)) >= 0.2
        ]
        moderate_null_cols = [
            c
            for c in columns
            if 0.05 <= float(c.get("null_rate", 0.0)) < 0.2
        ]

        if high_null_cols:
            cols_desc = ", ".join(
                f"{c['name']} ({float(c.get('null_rate', 0.0)):.1%})"
                for c in high_null_cols
            )
            findings.append(f"High null rates detected: {cols_desc}.")
            lines.append(f"- High null rates in: {cols_desc}")

        if moderate_null_cols:
            cols_desc = ", ".join(
                f"{c['name']} ({float(c.get('null_rate', 0.0)):.1%})"
                for c in moderate_null_cols
            )
            lines.append(f"- Moderate null rates in: {cols_desc}")

        # Basic dtype overview
        dtype_counts: Dict[str, int] = {}
        for c in columns:
            dt = str(c.get("dtype", "unknown"))
            dtype_counts[dt] = dtype_counts.get(dt, 0) + 1
        if dtype_counts:
            dtype_str = ", ".join(f"{dt}={cnt}" for dt, cnt in dtype_counts.items())
            lines.append(f"- Dtype breakdown: {dtype_str}")

        return lines, findings

    def _compare_with_reference(
        self,
        current_cols: List[Dict[str, Any]],
        reference: Dict[str, Any],
    ) -> Tuple[List[str], List[str]]:
        lines: List[str] = []
        findings: List[str] = []

        ref_name = reference.get("dataset_name", "reference")
        ref_rows = int(reference.get("row_count") or 0)
        ref_cols = reference.get("columns") or []

        lines.append(
            f"- Reference dataset '{ref_name}' rows={ref_rows}, "
            f"columns={len(ref_cols)}"
        )

        ref_by_name = {c["name"]: c for c in ref_cols}
        cur_by_name = {c["name"]: c for c in current_cols}

        # Schema drift: new / dropped columns
        new_cols = [n for n in cur_by_name.keys() if n not in ref_by_name]
        dropped_cols = [n for n in ref_by_name.keys() if n not in cur_by_name]

        if new_cols:
            msg = f"New columns since reference: {', '.join(new_cols)}."
            lines.append(f"- {msg}")
            findings.append(msg)

        if dropped_cols:
            msg = f"Columns missing vs reference: {', '.join(dropped_cols)}."
            lines.append(f"- {msg}")
            findings.append(msg)

        # Overlapping columns: null spikes and simple mean drift (if mean present)
        for name, cur_col in cur_by_name.items():
            ref_col = ref_by_name.get(name)
            if not ref_col:
                continue

            cur_null = float(cur_col.get("null_rate", 0.0))
            ref_null = float(ref_col.get("null_rate", 0.0))
            null_delta = cur_null - ref_null

            if null_delta >= 0.10:
                msg = (
                    f"Null spike in column '{name}': "
                    f"{ref_null:.1%} → {cur_null:.1%} (+{null_delta:.1%})."
                )
                lines.append(f"- {msg}")
                findings.append(msg)

            cur_dtype = str(cur_col.get("dtype", "unknown"))
            ref_dtype = str(ref_col.get("dtype", "unknown"))
            if cur_dtype != ref_dtype:
                msg = (
                    f"Schema drift in column '{name}': dtype changed "
                    f"{ref_dtype} → {cur_dtype}."
                )
                lines.append(f"- {msg}")
                findings.append(msg)

            # Optional: distribution shift based on mean if available
            if "mean" in cur_col and "mean" in ref_col:
                try:
                    cur_mean = float(cur_col["mean"])
                    ref_mean = float(ref_col["mean"])
                    base = ref_mean if abs(ref_mean) > 1e-6 else 1.0
                    rel_change = (cur_mean - ref_mean) / base
                    if abs(rel_change) >= 0.2:  # >=20% relative change
                        direction = "increased" if rel_change > 0 else "decreased"
                        msg = (
                            f"Mean value for '{name}' {direction} by "
                            f"{rel_change:+.1%} (ref={ref_mean:.3g}, cur={cur_mean:.3g})."
                        )
                        lines.append(f"- {msg}")
                        findings.append(msg)
                except (TypeError, ValueError):
                    # if mean values are not numeric, skip
                    pass

        return lines, findings

    def _score_health(
        self,
        health_flags: List[str],
        drift_findings: List[str],
    ) -> Tuple[str, str, float]:
        issues = len(health_flags) + len(drift_findings)

        if issues == 0:
            return ("low", "Healthy dataset", 0.95)

        if issues <= 3:
            return ("medium", "Minor data quality issues", 0.8)

        return ("high", "Significant data quality issues", 0.7)
