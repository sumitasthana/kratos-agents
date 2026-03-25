# Moved from: src\agents\git_diff_dataflow.py
# Import updates applied by migrate step.
import json
import logging
import re
import time
from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentResponse, AgentType
from core.instructions import load_prompt_content

logger = logging.getLogger(__name__)


# 1. ENHANCED PROMPT: Explicitly allows code/config as data sources
# Prompt loaded from prompts/git_diff_dataflow.yaml
GIT_DIFF_DATAFLOW_PROMPT = load_prompt_content("git_diff_dataflow")


@dataclass
class DiffDataFlow:
    intent_categories: List[str] = field(default_factory=list)
    process_name: str = ""
    data_domains: List[str] = field(default_factory=list)
    reads: List[Dict[str, str]] = field(default_factory=list)
    writes: List[Dict[str, str]] = field(default_factory=list)
    joins: List[Dict[str, Any]] = field(default_factory=list)
    transformations: List[Dict[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GitDiffDataFlowAgent(BaseAgent):
    def __init__(self, llm_config=None) -> None:
        from core.llm import LLMConfig
        self.llm_config  = llm_config or LLMConfig()
        self._name       = "GitDiffDataFlowAgent"
        self._llm_client = None
        self._tools      = []

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

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        max_commits: int = 25,
        max_chars_per_diff: int = 8000,
        always_use_llm: bool = True,
        **kwargs,
    ) -> List[str]:
        mode = "LLM" if always_use_llm else "heuristic"
        return [
            "Validate git_artifacts payload (files + commits + diffs)",
            f"Iterate commits (max_commits={max_commits}) and truncate diffs (max_chars_per_diff={max_chars_per_diff})",
            "Run heuristic extraction (reads/writes/joins/transformations)",
            f"Optionally enrich with {mode} extraction on relevant diff chunks",
            "Merge heuristic + LLM signals into a single dataflow result",
            "Summarize counts and write JSON output",
        ]

    async def invoke(self, context: Any) -> Any:
        """Satisfy BaseAgent.invoke() by delegating to analyze()."""
        from core.base_agent import AgentResult
        from tools.base_tool import agent_response_to_evidence
        fingerprint_data: Dict[str, Any] = (
            context.metadata.get("fingerprint_data")
            or context.metadata.get("git_artifacts")
            or context.metadata
        )
        response = await self.analyze(fingerprint_data=fingerprint_data)
        evidence = agent_response_to_evidence(response, tool_name="GitDiffTool")
        return AgentResult(
            agent_name=self.agent_name,
            evidence=evidence,
            metadata=response.metadata,
        )

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
        # [LOGGING] Cool log added
        logger.info(f"Thinking if this file is relevant or not: {file_path}")
        
        lowered = file_path.lower()
        include_docs = bool(getattr(self, "include_docs", False))
        if not include_docs and lowered.endswith((
            ".md", ".rst", ".txt",
        )):
            return False
        if lowered.endswith((
            ".pyc", ".pyo", ".class", ".jar", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        )):
            return False
        return True

    def _extract_relevant_diff_text(self, diff: str) -> str:
        """
        Reduce diff to lines most likely to carry dataflow signal.
        UPDATED: Now preserves Python structure (classes/defs) to capture logic-as-data pipelines.
        """
        kept: List[str] = []
        for raw in diff.splitlines():
            # Skip diff headers
            if raw.startswith("+++ ") or raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
                continue
            if raw.startswith("@@"):
                continue
            # Must be an added/removed line
            if not (raw.startswith("+") or raw.startswith("-")):
                continue
            # Skip double markers
            if raw.startswith("+++") or raw.startswith("---"):
                continue

            line = raw[1:].strip()
            if not line:
                continue

            # 1. Allow Python Structure (The Fix): 
            # Capture defs, classes, returns, and control flow to see the "Logic Pipeline"
            if re.search(r"^\s*(def |class |return |if |else|elif |with open|try:|except:)", line):
                kept.append(raw)
                continue

            # 2. Allow Variable Assignments that might contain data/SQL
            if re.search(r"=\s*(\"\"\"|'''|\"|')", line): # String assignments
                kept.append(raw)
                continue

            # 3. Filter out noise imports, but keep Schema/Config imports
            if (line.startswith("from ") or line.startswith("import ")):
                # Keep imports if they look like schema or config references
                if not any(k in line.lower() for k in ["schema", "config", "definition", "spark", "select"]):
                    continue

            # 4. Standard Heuristic for SQL/Spark (Original Logic)
            if re.search(
                r"spark\.|\.read\.|\.write\.|\.saveAsTable\(|\.save\(|\.load\(|\.join\(|\.groupBy\(|\.agg\(|\.filter\(|\.where\(|\bselect\b|\bfrom\b|\bjoin\b|\binsert\b|\bmerge\b|\bcreate\b",
                line,
                flags=re.IGNORECASE,
            ):
                kept.append(raw)
                continue
                
            # 5. Catch Orchestration Keywords (New)
            if re.search(r"\b(pipeline|convert|transform|map|analyze)\b", line, flags=re.IGNORECASE):
                kept.append(raw)
                continue

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
        # [LOGGING] Cool log added
        logger.debug(f"Searching for the text: pattern='{pattern[:20]}...'")
        
        try:
            return re.search(pattern, text, flags=flags)
        except re.error as e:
            logger.warning(f"[GIT_DIFF_DATAFLOW] Invalid regex pattern skipped: {pattern!r} ({e})")
            return None

    def _extract_patterns_from_diff(self, diff: str) -> DiffDataFlow:
        # [LOGGING] Cool log added
        logger.info("Finding patterns in Git diff")

        # Only consider added lines for heuristics, but filter out obvious noise.
        lines = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        lines = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith(("from ", "import "))]
        added = "\n".join(lines)

        flow = DiffDataFlow()

        # Lightweight intent/domain classification.
        intent, process_name, domains = self._heuristic_intent_and_domain(diff)
        flow.intent_categories = intent
        flow.process_name = process_name
        flow.data_domains = domains

        # Reads
        read_patterns = [
            (r"\bspark\.read\.\w+\(\s*['\"]([^'\"]+)['\"]", "spark.read"),
            (r"\bread\.(?:parquet|csv|json|orc|table)\(\s*['\"]([^'\"]+)['\"]", "read"),
            (r"\bspark\.table\(\s*['\"]([^'\"]+)['\"]", "spark.table"),
            (r"\bread\.format\(\s*['\"]([^'\"]+)['\"]\)\.load\(\s*['\"]([^'\"]+)['\"]", "read.format.load"),
            (r"\bLOAD\s+DATA\s+INPATH\s+['\"]([^'\"]+)['\"]", "hive_load"),
            # New: Capture open() calls for file reading
            (r"\bopen\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]r['\"]", "file_read"),
        ]
        for pat, kind in read_patterns:
            for m in self._safe_finditer(pat, added, flags=re.IGNORECASE):
                src = m.group(1)
                flow.reads.append({"source": src, "evidence": m.group(0)[:200]})

        # Writes
        write_patterns = [
            (r"\bwrite\.(?:parquet|csv|json|orc)\(\s*['\"]([^'\"]+)['\"]", "write"),
            (r"\bwrite\.save\(\s*['\"]([^'\"]+)['\"]", "write.save"),
            (r"\bwrite\.saveAsTable\(\s*['\"]([^'\"]+)['\"]", "saveAsTable"),
            (r"\bINSERT\s+INTO\s+([a-zA-Z0-9_\.]+)", "sql_insert"),
            (r"\bCREATE\s+TABLE\s+([a-zA-Z0-9_\.]+)", "sql_create_table"),
            # New: Capture json.dump for config writing
            (r"\bjson\.dump\(\s*.*,\s*f\s*\)", "json_file_write"),
        ]
        for pat, kind in write_patterns:
            for m in self._safe_finditer(pat, added, flags=re.IGNORECASE):
                # For json.dump we might not have a clean sink name in the regex, so we handle loosely
                sink = m.group(1) if len(m.groups()) > 0 else "json_output"
                flow.writes.append({"sink": sink, "evidence": m.group(0)[:200]})

        # Joins (Existing logic)
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
                m = self._safe_search(pat, added)
                snippet = added[m.start() : m.start() + 220] if m else pat
                flow.transformations.append({"type": ttype, "details": "", "evidence": snippet[:200]})

        if not flow.reads and not flow.writes and not flow.joins and not flow.transformations:
            flow.notes.append("No dataflow patterns detected by heuristics in added lines")

        flow.reads = self._dedupe_dict_list(flow.reads, "source")
        flow.writes = self._dedupe_dict_list(flow.writes, "sink")
        flow.transformations = self._dedupe_dict_list(flow.transformations, "type")

        return flow

    def _heuristic_intent_and_domain(self, diff: str) -> tuple[List[str], str, List[str]]:
        text = diff.lower()

        intent_hits: List[str] = []
        domain_hits: List[str] = []
        process_name = ""

        intent_keywords = {
            "feature_engineering": ["feature", "feature store", "embedding", "vector", "risk score", "scoring"],
            "validation": ["validate", "validation", "assert", "expectation", "great expectations", "dq", "data quality"],
            "reconciliation": ["reconcile", "reconciliation", "balance", "tie out", "tie-out"],
            "audit_trail": ["audit", "audit trail", "lineage", "provenance"],
            "remediation": ["remed", "backfill", "fixup", "hotfix", "repair"],
            "transformation": ["transform", "normalize", "standardize", "mapping", "udf"],
            "aggregation": ["groupby", "group by", "agg(", "aggregate", "rollup", "summary"],
            "masking": ["mask", "redact", "tokenize", "hash", "encrypt", "pii"],
            "archival": ["archive", "retention", "purge", "cold storage"],
            # NEW: Metadata Management
            "metadata_management": ["generator", "template", "schema", "config", "json", "yaml", "convert", "mapper"],
        }

        domain_keywords = {
            "accounts": ["account", "acct", "iban"],
            "customers": ["customer", "client", "kyc", "cif"],
            "transactions": ["transaction", "txn", "payment", "transfer", "posting"],
            "limits": ["limit", "exposure", "threshold"],
            "collateral": ["collateral", "security", "lien"],
            "regulatory_reporting": ["regulatory", "reporting", "basel", "ccar", "sox", "aml", "ofac"],
            # NEW: Data Governance
            "data_governance": ["quality", "lineage", "catalog", "policy", "standard", "great expectations", "gex"],
        }

        for intent, kws in intent_keywords.items():
            if any(kw in text for kw in kws):
                intent_hits.append(intent)

        for dom, kws in domain_keywords.items():
            if any(kw in text for kw in kws):
                domain_hits.append(dom)

        # Process name guessing
        if "sanction" in text or "ofac" in text or "aml" in text:
            process_name = "sanctions screening"
        elif "kyc" in text:
            process_name = "KYC refresh"
        elif "risk" in text and "score" in text:
            process_name = "account risk scoring"
        elif "generator" in text and "config" in text:
            process_name = "configuration generation"

        def _dedupe(xs: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for x in xs:
                if x in seen:
                    continue
                seen.add(x)
                out.append(x)
            return out

        return _dedupe(intent_hits), process_name, _dedupe(domain_hits)

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
        
        # 1. Base length check (keep existing)
        if len(diff) <= 200:
            return False

        relevant = self._extract_relevant_diff_text(diff)
        if len(relevant) <= 120:
            return False

        # 2. [NEW] Trigger for Orchestration/Pipeline Logic
        # This ensures files like "main.py" or "etl.py" get analyzed even if they don't have SQL
        if re.search(r"(import|from)\s+.*\b(pipeline|orchestration|flow|etl|converter|mapper|generator)\b", diff, re.IGNORECASE):
            return True
        
        # 3. [NEW] Trigger for Schema/Config Definitions
        if re.search(r"class\s+\w+(Schema|Definition|Config)\b", diff):
            return True

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
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
            else:
                raise

        flow = DiffDataFlow()

        # Added new allowed values for metadata pipeline support
        allowed_intents = {
            "feature_engineering",
            "validation",
            "reconciliation",
            "audit_trail",
            "remediation",
            "transformation",
            "aggregation",
            "masking",
            "archival",
            "metadata_management", # New
        }
        allowed_domains = {
            "accounts",
            "customers",
            "transactions",
            "limits",
            "collateral",
            "regulatory_reporting",
            "data_governance", # New
        }

        intents = [i for i in (parsed.get("intent_categories") or []) if isinstance(i, str)]
        flow.intent_categories = [i for i in intents if i in allowed_intents]

        pn = parsed.get("process_name")
        if isinstance(pn, str):
            flow.process_name = pn.strip()[:120]

        domains = [d for d in (parsed.get("data_domains") or []) if isinstance(d, str)]
        flow.data_domains = [d for d in domains if d in allowed_domains]

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
            intent_categories=a.intent_categories + b.intent_categories,
            process_name=a.process_name or b.process_name,
            data_domains=a.data_domains + b.data_domains,
            reads=a.reads + b.reads,
            writes=a.writes + b.writes,
            joins=a.joins + b.joins,
            transformations=a.transformations + b.transformations,
            notes=a.notes + b.notes,
        )
        out.intent_categories = list(dict.fromkeys([x for x in out.intent_categories if x]))
        out.data_domains = list(dict.fromkeys([x for x in out.data_domains if x]))
        out.reads = self._dedupe_dict_list(out.reads, "source")
        out.writes = self._dedupe_dict_list(out.writes, "sink")
        out.transformations = self._dedupe_dict_list(out.transformations, "type")
        return out

    def _summarize_flows(self, flows: List[Dict[str, Any]]) -> tuple[str, List[str], str]:
        reads = set()
        writes = set()
        joins = 0
        transforms = 0
        intents = set()
        domains = set()
        process_names = set()

        for item in flows:
            df = item.get("dataflow")
            if isinstance(df, dict):
                for ic in df.get("intent_categories", []) or []:
                    if isinstance(ic, str) and ic:
                        intents.add(ic)
                for dd in df.get("data_domains", []) or []:
                    if isinstance(dd, str) and dd:
                        domains.add(dd)
                pn = df.get("process_name")
                if isinstance(pn, str) and pn.strip():
                    process_names.add(pn.strip())
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
            f"Intent categories detected: {len(intents)}",
            f"Data domains detected: {len(domains)}",
            f"Process names inferred: {len(process_names)}",
            f"Reads detected: {len(reads)}",
            f"Writes detected: {len(writes)}",
            f"Joins detected: {joins}",
            f"Transformations detected: {transforms}",
        ]

        explanation = json.dumps({"results": flows}, indent=2)
        return summary, key_findings, explanation


# Patch LLM usage: override _extract_from_git_artifacts to use async LLM when enabled
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

            # NOTE: Logic Updated in _extract_relevant_diff_text to include Python structure
            relevant = agent._extract_relevant_diff_text(diff)
            llm_chunks = agent._chunk_text(relevant, max_chars=min(max_chars_per_diff, 5000)) if relevant else []

            # NOTE: Logic Updated in _should_call_llm to trigger on Pipeline code
            use_llm = always_use_llm or agent._should_call_llm(heuristic, diff)
            
            if use_llm and llm_chunks:
                logger.info(f"[GIT_DIFF_DATAFLOW]   LLM enabled: {len(llm_chunks)} chunk(s)")
                llm_merged = DiffDataFlow()
                for idx, chunk in enumerate(llm_chunks, start=1):
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


# ── BaseTool adapter ─────────────────────────────────────────────────────────

from tools.base_tool import BaseTool, agent_response_to_evidence  # noqa: E402
from core.models import IncidentContext, EvidenceObject  # noqa: E402


class GitDiffTool(BaseTool):
    """
    BaseTool-conforming wrapper around ``GitDiffDataFlowAgent``.

    Reads ``context.metadata["git_artifacts"]`` (a dict with a ``files``
    list of commit/diff entries) and produces EvidenceObjects describing
    which data-flow patterns changed and which controls are at risk.
    """

    def __init__(self, llm_config=None) -> None:
        from core.llm import LLMConfig
        self._agent = GitDiffDataFlowAgent(llm_config or LLMConfig())

    @property
    def name(self) -> str:
        return "GitDiffTool"

    @property
    def description(self) -> str:
        return (
            "Extracts data-flow patterns (reads/writes/joins/transforms) from git diff "
            "artifacts to trace code changes to control failures."
        )

    def _parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Unique incident identifier",
                },
                "git_artifacts": {
                    "type": "object",
                    "description": (
                        "Git diff artifacts: changed files, commit history, "
                        "contributor map, and churn metrics over the failure window"
                    ),
                },
                "time_window_hours": {
                    "type": "integer",
                    "description": "Lookback window in hours (default 72)",
                    "default": 72,
                },
            },
            "required": ["incident_id"],
        }

    async def run(self, context: IncidentContext) -> list[EvidenceObject]:
        git_artifacts = (
            context.metadata.get("git_artifacts")
            or context.metadata.get("fingerprint")
            or {}
        )
        if not isinstance(git_artifacts, dict):
            logger.warning("%s: git_artifacts is not a dict, returning empty", self.name)
            return []
        try:
            response = await self._agent.analyze(fingerprint_data=git_artifacts)
            return agent_response_to_evidence(
                response,
                tool_name=self.name,
                regulation_ref=context.metadata.get("regulation_ref"),
            )
        except Exception as exc:
            logger.warning("%s.run failed: %s", self.name, exc, exc_info=True)
            return []
