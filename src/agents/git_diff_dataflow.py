import json
import logging
import re
import time
from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResponse, AgentType

logger = logging.getLogger(__name__)


GIT_DIFF_DATAFLOW_PROMPT = """You are a senior data engineer.

You will be given git diffs (unified diff format) for code changes. Your job is to extract *data flow patterns* introduced or modified by the change.

Data flow patterns to extract:
- reads: sources of data (tables, files, APIs) being read
- writes: sinks of data (tables, files, APIs) being written
- joins: join operations and join keys if available
- transformations: filters, projections/selects, aggregations/groupBy, unions, sorts, window functions, mapping/UDFs

Important:
- Ignore *Python imports* (e.g., `from typing import ...`) and other library/module references. These are not data reads.
- Only treat SQL `FROM/JOIN/INSERT` as dataflow when it is part of an actual SQL query string or SQL statement, not Python `from ... import ...`.
- Prefer concrete artifacts: table names, file paths, formats, catalog/db.schema.table identifiers.

Return STRICT JSON ONLY (no markdown) with this schema:
{{
  "reads": [{{"source": "...", "evidence": "..."}}],
  "writes": [{{"sink": "...", "evidence": "..."}}],
  "joins": [{{"type": "...", "keys": ["..."], "evidence": "..."}}],
  "transformations": [{{"type": "...", "details": "...", "evidence": "..."}}],
  "notes": ["..."]
}}

Rules:
- Only infer what is justified by the diff.
- Prefer concrete artifacts (table names, paths, formats).
- Keep evidence short (a relevant line or two).
"""


@dataclass
class DiffDataFlow:
    reads: List[Dict[str, str]] = field(default_factory=list)
    writes: List[Dict[str, str]] = field(default_factory=list)
    joins: List[Dict[str, Any]] = field(default_factory=list)
    transformations: List[Dict[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GitDiffDataFlowAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.GIT_DIFF_DATAFLOW

    @property
    def agent_name(self) -> str:
        return "Git Diff Data Flow Agent"

    @property
    def description(self) -> str:
        return "Extracts data flow patterns (reads/writes/joins/transformations) from git diffs in git_artifacts JSON"

    @property
    def system_prompt(self) -> str:
        return GIT_DIFF_DATAFLOW_PROMPT

    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        max_commits: int = 25,
        max_chars_per_diff: int = 8000,
        always_use_llm: bool = True,
        **kwargs,
    ) -> AgentResponse:
        start_time = time.time()
        try:
            flows = await _extract_from_git_artifacts_with_llm(
                self,
                fingerprint_data,
                max_commits=max_commits,
                max_chars_per_diff=max_chars_per_diff,
                always_use_llm=always_use_llm,
            )

            processing_time = int((time.time() - start_time) * 1000)
            summary, key_findings, explanation = self._summarize_flows(flows)

            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=summary,
                explanation=explanation,
                key_findings=key_findings,
                confidence=0.85,
                processing_time_ms=processing_time,
                model_used=self.llm_config.model,
            )
        except Exception as e:
            logger.exception("Error during git diff dataflow analysis")
            return self._create_error_response(str(e))

    async def analyze_without_llm(
        self,
        fingerprint_data: Dict[str, Any],
        max_commits: int = 50,
        max_chars_per_diff: int = 8000,
    ) -> AgentResponse:
        start_time = time.time()
        try:
            flows = self._extract_from_git_artifacts(
                fingerprint_data,
                max_commits=max_commits,
                max_chars_per_diff=max_chars_per_diff,
                use_llm=False,
            )

            processing_time = int((time.time() - start_time) * 1000)
            summary, key_findings, explanation = self._summarize_flows(flows)

            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=summary,
                explanation=explanation,
                key_findings=key_findings,
                confidence=0.6,
                processing_time_ms=processing_time,
            )
        except Exception as e:
            return self._create_error_response(str(e))

    def _extract_from_git_artifacts(
        self,
        payload: Dict[str, Any],
        max_commits: int,
        max_chars_per_diff: int,
        use_llm: bool,
    ) -> List[Dict[str, Any]]:
        files = payload.get("files")
        if not isinstance(files, list):
            raise ValueError("Invalid git_artifacts payload: missing 'files' list")

        results: List[Dict[str, Any]] = []
        commits_seen = 0

        for file_entry in files:
            file_path = file_entry.get("file_path")
            commit_list = file_entry.get("commits") or []
            if not file_path or not isinstance(commit_list, list):
                continue

            if not self._is_relevant_file(file_path):
                continue

            for c in commit_list:
                if commits_seen >= max_commits:
                    return results

                diff = c.get("diff") or ""
                if not isinstance(diff, str) or not diff.strip():
                    continue

                diff = self._truncate_diff(diff, max_chars_per_diff)

                heuristic = self._extract_patterns_from_diff(diff)

                if use_llm:
                    raise RuntimeError("use_llm=True is only supported via _extract_from_git_artifacts_with_llm")

                merged = heuristic

                results.append(
                    {
                        "file_path": file_path,
                        "commit_hash": c.get("commit_hash"),
                        "author": c.get("author"),
                        "date": c.get("date"),
                        "message": c.get("message"),
                        "dataflow": merged.to_dict(),
                    }
                )
                commits_seen += 1

        return results

    def _truncate_diff(self, diff: str, max_chars: int) -> str:
        if len(diff) <= max_chars:
            return diff
        return diff[:max_chars] + "\n... [truncated]"

    def _is_relevant_file(self, file_path: str) -> bool:
        # Skip obviously non-source/binary artifacts that create lots of noise in diffs.
        lowered = file_path.lower()
        if lowered.endswith((
            ".pyc",
            ".pyo",
            ".class",
            ".jar",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
        )):
            return False
        return True

    def _extract_relevant_diff_text(self, diff: str) -> str:
        """Reduce diff to lines most likely to carry dataflow signal."""
        kept: List[str] = []
        for raw in diff.splitlines():
            if raw.startswith("+++ ") or raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
                continue
            if raw.startswith("@@"):
                continue
            if not (raw.startswith("+") or raw.startswith("-")):
                continue
            if raw.startswith("+++") or raw.startswith("---"):
                continue

            line = raw[1:].strip()
            if not line:
                continue

            # Filter out Python import noise unless it contains explicit data access patterns.
            if (line.startswith("from ") or line.startswith("import ")):
                if "spark" not in line and "SELECT" not in line and "select" not in line:
                    continue

            # Keep only lines that have reasonable chance of describing dataflow.
            if not re.search(
                r"spark\.|\.read\.|\.write\.|\.saveAsTable\(|\.save\(|\.load\(|\.join\(|\.groupBy\(|\.agg\(|\.filter\(|\.where\(|\bselect\b|\bfrom\b|\bjoin\b|\binsert\b|\bmerge\b|\bcreate\b",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            kept.append(raw)

        return "\n".join(kept)

    def _chunk_text(self, text: str, max_chars: int) -> List[str]:
        if len(text) <= max_chars:
            return [text]
        chunks: List[str] = []
        start = 0
        overlap = 300
        while start < len(text):
            end = min(len(text), start + max_chars)
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = max(0, end - overlap)
        return chunks

    def _safe_finditer(self, pattern: str, text: str, flags: int = 0):
        try:
            return re.finditer(pattern, text, flags=flags)
        except re.error as e:
            logger.warning(f"[GIT_DIFF_DATAFLOW] Invalid regex pattern skipped: {pattern!r} ({e})")
            return iter(())

    def _safe_search(self, pattern: str, text: str, flags: int = 0):
        try:
            return re.search(pattern, text, flags=flags)
        except re.error as e:
            logger.warning(f"[GIT_DIFF_DATAFLOW] Invalid regex pattern skipped: {pattern!r} ({e})")
            return None

    def _extract_patterns_from_diff(self, diff: str) -> DiffDataFlow:
        # Only consider added lines for heuristics, but filter out obvious noise.
        lines = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        lines = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith(("from ", "import "))]
        added = "\n".join(lines)

        flow = DiffDataFlow()

        # Reads
        read_patterns = [
            (r"\bspark\.read\.\w+\(\s*['\"]([^'\"]+)['\"]", "spark.read"),
            (r"\bread\.(?:parquet|csv|json|orc|table)\(\s*['\"]([^'\"]+)['\"]", "read"),
            (r"\bspark\.table\(\s*['\"]([^'\"]+)['\"]", "spark.table"),
            (r"\bread\.format\(\s*['\"]([^'\"]+)['\"]\)\.load\(\s*['\"]([^'\"]+)['\"]", "read.format.load"),
            (r"\bLOAD\s+DATA\s+INPATH\s+['\"]([^'\"]+)['\"]", "hive_load"),
        ]
        for pat, kind in read_patterns:
            for m in self._safe_finditer(pat, added, flags=re.IGNORECASE):
                src = m.group(2) if kind == "read.format.load" else m.group(1)
                flow.reads.append({"source": src, "evidence": m.group(0)[:200]})

        # Writes
        write_patterns = [
            (r"\bwrite\.(?:parquet|csv|json|orc)\(\s*['\"]([^'\"]+)['\"]", "write"),
            (r"\bwrite\.save\(\s*['\"]([^'\"]+)['\"]", "write.save"),
            (r"\bwrite\.saveAsTable\(\s*['\"]([^'\"]+)['\"]", "saveAsTable"),
            (r"\bINSERT\s+INTO\s+([a-zA-Z0-9_\.]+)", "sql_insert"),
            (r"\bCREATE\s+TABLE\s+([a-zA-Z0-9_\.]+)", "sql_create_table"),
        ]
        for pat, kind in write_patterns:
            for m in self._safe_finditer(pat, added, flags=re.IGNORECASE):
                sink = m.group(1)
                flow.writes.append({"sink": sink, "evidence": m.group(0)[:200]})

        # Joins
        for m in self._safe_finditer(r"\b\.join\(", added):
            snippet = added[m.start() : m.start() + 300]
            keys = []
            m_on = self._safe_search(r"\bon\s*=\s*\[([^\]]+)\]", snippet)
            if m_on:
                keys = [k.strip().strip("'\"") for k in m_on.group(1).split(",") if k.strip()]
            flow.joins.append({"type": "dataframe_join", "keys": keys, "evidence": snippet[:200]})

        for m in self._safe_finditer(r"\bJOIN\b", added, flags=re.IGNORECASE):
            snippet = added[m.start() : m.start() + 300]
            keys = []
            m_on = self._safe_search(r"\bON\b\s+([^\n;]+)", snippet, flags=re.IGNORECASE)
            if m_on:
                keys = [m_on.group(1)[:120]]
            flow.joins.append({"type": "sql_join", "keys": keys, "evidence": snippet[:200]})

        # Transformations
        transform_map = [
            (r"\b\.filter\(", "filter"),
            (r"\b\.where\(", "filter"),
            (r"\b\.select\(", "select"),
            (r"\b\.withColumn\(", "withColumn"),
            (r"\b\.groupBy\(", "groupBy"),
            (r"\b\.agg\(", "agg"),
            (r"\b\.union(?:All)?\(", "union"),
            (r"\b\.dropDuplicates\(", "dropDuplicates"),
            (r"\b\.distinct\(\)", "distinct"),
            (r"\b\.orderBy\(", "orderBy"),
            (r"\b\.sort\(", "sort"),
            (r"\b\.repartition\(", "repartition"),
            (r"\b\.coalesce\(", "coalesce"),
        ]
        for pat, ttype in transform_map:
            if self._safe_search(pat, added):
                # capture a small snippet around first match
                m = self._safe_search(pat, added)
                snippet = added[m.start() : m.start() + 220] if m else pat
                flow.transformations.append({"type": ttype, "details": "", "evidence": snippet[:200]})

        if not flow.reads and not flow.writes and not flow.joins and not flow.transformations:
            flow.notes.append("No dataflow patterns detected by heuristics in added lines")

        flow.reads = self._dedupe_dict_list(flow.reads, "source")
        flow.writes = self._dedupe_dict_list(flow.writes, "sink")
        flow.transformations = self._dedupe_dict_list(flow.transformations, "type")

        return flow

    def _dedupe_dict_list(self, items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for it in items:
            v = it.get(key)
            if not v or v in seen:
                continue
            seen.add(v)
            out.append(it)
        return out

    def _should_call_llm(self, heuristic: DiffDataFlow, diff: str) -> bool:
        # LLM is valuable when diffs contain SQL strings or non-trivial pipeline code.
        # We call LLM when there is some signal in the diff and/or heuristics are uncertain.
        if len(diff) <= 200:
            return False

        relevant = self._extract_relevant_diff_text(diff)
        if len(relevant) <= 120:
            return False

        # If heuristics already found strong sources/sinks, we still allow LLM to enrich joins/transformations.
        return True

    async def _llm_extract_json_async(self, file_path: str, commit: Dict[str, Any], diff: str) -> DiffDataFlow:
        user_payload = {
            "file_path": file_path,
            "commit": {
                "commit_hash": commit.get("commit_hash"),
                "message": commit.get("message"),
                "author": commit.get("author"),
                "date": commit.get("date"),
            },
            "diff": diff,
        }
        user_prompt = "Extract dataflow patterns from this diff.\n\n" + json.dumps(user_payload)
        raw = await self._call_llm(GIT_DIFF_DATAFLOW_PROMPT, user_prompt)

        try:
            parsed = json.loads(raw)
        except Exception:
            # try to salvage JSON substring
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
            else:
                raise

        flow = DiffDataFlow()
        for r in parsed.get("reads", []) or []:
            if r.get("source"):
                flow.reads.append({"source": r.get("source"), "evidence": r.get("evidence", "")})
        for w in parsed.get("writes", []) or []:
            if w.get("sink"):
                flow.writes.append({"sink": w.get("sink"), "evidence": w.get("evidence", "")})
        for j in parsed.get("joins", []) or []:
            flow.joins.append(
                {
                    "type": j.get("type", ""),
                    "keys": j.get("keys", []) or [],
                    "evidence": j.get("evidence", ""),
                }
            )
        for t in parsed.get("transformations", []) or []:
            if t.get("type"):
                flow.transformations.append(
                    {
                        "type": t.get("type"),
                        "details": t.get("details", ""),
                        "evidence": t.get("evidence", ""),
                    }
                )
        for n in parsed.get("notes", []) or []:
            if isinstance(n, str) and n.strip():
                flow.notes.append(n.strip())

        flow.reads = self._dedupe_dict_list(flow.reads, "source")
        flow.writes = self._dedupe_dict_list(flow.writes, "sink")
        return flow

    def _merge_flows(self, a: DiffDataFlow, b: DiffDataFlow) -> DiffDataFlow:
        out = DiffDataFlow(
            reads=a.reads + b.reads,
            writes=a.writes + b.writes,
            joins=a.joins + b.joins,
            transformations=a.transformations + b.transformations,
            notes=a.notes + b.notes,
        )
        out.reads = self._dedupe_dict_list(out.reads, "source")
        out.writes = self._dedupe_dict_list(out.writes, "sink")
        out.transformations = self._dedupe_dict_list(out.transformations, "type")
        return out

    def _summarize_flows(self, flows: List[Dict[str, Any]]) -> tuple[str, List[str], str]:
        reads = set()
        writes = set()
        joins = 0
        transforms = 0

        for item in flows:
            df = item.get("dataflow")
            if isinstance(df, dict):
                for r in df.get("reads", []) or []:
                    if r.get("source"):
                        reads.add(r["source"])
                for w in df.get("writes", []) or []:
                    if w.get("sink"):
                        writes.add(w["sink"])
                joins += len(df.get("joins", []) or [])
                transforms += len(df.get("transformations", []) or [])

        summary = f"Extracted dataflow patterns from {len(flows)} commit diff(s)."
        key_findings = [
            f"Reads detected: {len(reads)}",
            f"Writes detected: {len(writes)}",
            f"Joins detected: {joins}",
            f"Transformations detected: {transforms}",
        ]

        explanation = json.dumps({"results": flows}, indent=2)
        return summary, key_findings, explanation


# Patch LLM usage: override _extract_from_git_artifacts to use async LLM when enabled
# (kept here to avoid calling async from sync context)
async def _extract_from_git_artifacts_with_llm(
    agent: GitDiffDataFlowAgent,
    payload: Dict[str, Any],
    max_commits: int,
    max_chars_per_diff: int,
    always_use_llm: bool,
) -> List[Dict[str, Any]]:
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("Invalid git_artifacts payload: missing 'files' list")

    results: List[Dict[str, Any]] = []
    commits_seen = 0

    for file_entry in files:
        file_path = file_entry.get("file_path")
        commit_list = file_entry.get("commits") or []
        if not file_path or not isinstance(commit_list, list):
            continue

        if not agent._is_relevant_file(file_path):
            continue

        logger.info(f"[GIT_DIFF_DATAFLOW] File: {file_path} ({len(commit_list)} commits)")

        for c in commit_list:
            if commits_seen >= max_commits:
                return results

            commit_hash = c.get("commit_hash")
            logger.info(f"[GIT_DIFF_DATAFLOW]  Commit: {commit_hash} | {c.get('message')}")

            diff = c.get("diff") or ""
            if not isinstance(diff, str) or not diff.strip():
                continue

            diff = agent._truncate_diff(diff, max_chars_per_diff)

            # Heuristic pass (fast, deterministic)
            heuristic = agent._extract_patterns_from_diff(diff)

            relevant = agent._extract_relevant_diff_text(diff)
            llm_chunks = agent._chunk_text(relevant, max_chars=min(max_chars_per_diff, 5000)) if relevant else []

            use_llm = always_use_llm or agent._should_call_llm(heuristic, diff)
            if use_llm and llm_chunks:
                logger.info(f"[GIT_DIFF_DATAFLOW]   LLM enabled: {len(llm_chunks)} chunk(s)")
                llm_merged = DiffDataFlow()
                for idx, chunk in enumerate(llm_chunks, start=1):
                    # Feed only the filtered chunk to reduce noise and token usage.
                    logger.info(f"[GIT_DIFF_DATAFLOW]    Processing chunk {idx}/{len(llm_chunks)} ({len(chunk)} chars)")
                    llm_flow = await agent._llm_extract_json_async(file_path, c, chunk)
                    llm_merged = agent._merge_flows(llm_merged, llm_flow)
                merged = agent._merge_flows(heuristic, llm_merged)
            else:
                logger.info("[GIT_DIFF_DATAFLOW]   LLM disabled or no relevant diff signal")
                merged = heuristic

            results.append(
                {
                    "file_path": file_path,
                    "commit_hash": c.get("commit_hash"),
                    "author": c.get("author"),
                    "date": c.get("date"),
                    "message": c.get("message"),
                    "dataflow": merged.to_dict(),
                }
            )
            commits_seen += 1

    return results
