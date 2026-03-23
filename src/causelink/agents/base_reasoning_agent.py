"""
causelink/agents/base_reasoning_agent.py

BaseReasoningAgent — abstract base class for all LLM-powered CauseLink agents.

Each subclass implements:
  - agent_name (property) — stable identifier string
  - phase (property)      — which SSE phase this agent runs in
  - build_prompt()        — constructs the LLM prompt given state + context
  - parse_response()      — parses the LLM response into InvestigationState updates

The base class handles:
  - Streaming anthropic call with temperature=0
  - Stateful XML tag parsing as tokens arrive
  - Emitting ThoughtStep objects to thought_queue as tags complete
  - Metrics / logging instrumentation
  - Graceful fallback when anthropic is not installed or no API key

Fallback behaviour:
  When anthropic is not installed or ANTHROPIC_API_KEY is not set,
  the agent calls build_fallback_thoughts() to produce deterministic
  synthetic thought steps and calls parse_response("", state) so the
  phase still produces correct state updates via the existing pattern-based
  logic in the subclass.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from causelink.reasoning.thought_trace import ThoughtStep, ThoughtTrace
from causelink.state.investigation import AuditTraceEntry, InvestigationState

if TYPE_CHECKING:
    from src.infrastructure.base_adapter import InfrastructureAdapter

# Anthropic — optional import
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

# Observability — optional import
try:
    from src.observability.metrics import M as _M
    from src.observability.logger import get_logger as _get_logger, LogEvent
    _OBS_AVAILABLE = True
except ImportError:
    _OBS_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt shared by all reasoning agents
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """You are a CauseLink RCA agent. You reason step by step about banking
compliance failures. You are precise, regulatory-grounded, and evidence-first.

CRITICAL OUTPUT FORMAT:
You must wrap every reasoning step in XML tags. The tags stream to a live
UI — users are watching you think in real time. Be explicit about why you
are accepting or rejecting each piece of evidence or each hypothesis.

Use these tags:
<observe>  — describe what you see in the evidence, logs, or data       </observe>
<hypothesise> — form a candidate explanation                          </hypothesise>
<test>     — check the hypothesis against ontology, evidence, or rules  </test>
<reject>   — explain why you are discarding an alternative              </reject>
<accept>   — explain why you are promoting a hypothesis to SUPPORTED    </accept>
<warn>     — flag an anomaly or edge case you noticed                   </warn>
<conclude> — state your final determination for this phase              </conclude>

After all reasoning tags, output a final JSON block:
```json
{ ...your structured output for this agent's phase... }
```

Rules:
- Every claim must reference a specific evidence_id, node_id, or log line.
- Never claim root cause without a CRITICAL-tier evidence object.
- Always explain rejected alternatives explicitly.
- Keep each <observe> / <test> / <reject> block to 2-4 sentences.
- The JSON block at the end must conform to the phase output schema.
- Do not output anything outside the XML tags and the JSON block."""

# Tag → ThoughtStep.thought_type mapping
_TAG_MAP: dict[str, str] = {
    "observe":      "OBSERVING",
    "hypothesise":  "HYPOTHESISING",
    "test":         "TESTING",
    "reject":       "REJECTING",
    "accept":       "ACCEPTING",
    "conclude":     "CONCLUDING",
    "warn":         "WARNING",
}


# ---------------------------------------------------------------------------
# Streaming XML tag parser
# ---------------------------------------------------------------------------

class StreamingTagParser:
    """
    Stateful streaming parser for XML thought tags.

    Processes text chunk by chunk as it arrives from the LLM stream.
    Emits (thought_type, content) tuples for each complete tag found.

    The parser handles tags that are split across multiple chunks.
    """

    def __init__(self) -> None:
        self._buf: str = ""
        self._in_tag: str | None = None
        self._content: str = ""

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """
        Feed a new text chunk.  Returns list of (thought_type, content)
        for any complete tags found in this or prior buffered chunks.
        """
        self._buf += chunk
        completed: list[tuple[str, str]] = []

        while True:
            if self._in_tag is None:
                # Look for an opening tag
                lt = self._buf.find("<")
                if lt == -1:
                    break
                found_tag: str | None = None
                for tag in _TAG_MAP:
                    prefix = f"<{tag}>"
                    if self._buf[lt:].startswith(prefix):
                        found_tag = tag
                        break
                if found_tag is not None:
                    self._buf = self._buf[lt + len(found_tag) + 2:]
                    self._in_tag = found_tag
                    self._content = ""
                else:
                    # Not a known tag start — skip past the <
                    self._buf = self._buf[lt + 1:]
            else:
                # Inside a tag — look for the closing tag
                close = f"</{self._in_tag}>"
                ci = self._buf.find(close)
                if ci != -1:
                    self._content += self._buf[:ci]
                    self._buf = self._buf[ci + len(close):]
                    thought_type = _TAG_MAP[self._in_tag]
                    completed.append((thought_type, self._content.strip()))
                    self._in_tag = None
                    self._content = ""
                else:
                    # Closing tag not yet arrived — accumulate, but keep a
                    # small tail buffer in case the close tag straddles chunks.
                    keep = len(close) - 1
                    if len(self._buf) > keep:
                        self._content += self._buf[:-keep]
                        self._buf = self._buf[-keep:]
                    break

        return completed


# ---------------------------------------------------------------------------
# BaseReasoningAgent
# ---------------------------------------------------------------------------

class BaseReasoningAgent(ABC):
    """
    All demo CauseLink agents inherit this.
    Provides structured LLM reasoning with streaming thought traces.
    """

    @property
    @abstractmethod
    def agent_name(self) -> str: ...

    @property
    @abstractmethod
    def phase(self) -> str: ...

    @abstractmethod
    def build_prompt(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
    ) -> str:
        """Build the LLM prompt for this agent's phase."""

    @abstractmethod
    def parse_response(
        self,
        response_text: str,
        state: InvestigationState,
    ) -> InvestigationState:
        """Parse the LLM response and update InvestigationState."""

    def build_fallback_thoughts(
        self,
        state: InvestigationState,
        context: dict,
    ) -> list[tuple[str, str]]:
        """
        Return synthetic (thought_type, content) pairs for fallback mode.
        Subclasses override this to provide deterministic reasoning steps
        that explain what the agent would have concluded.
        """
        return [
            ("CONCLUDING", f"{self.agent_name}: completed analysis (LLM unavailable — running pattern-based fallback)"),
        ]

    async def emit_thoughts(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
        thought_queue: "asyncio.Queue[ThoughtStep | None]",
    ) -> str:
        """
        Generate reasoning thoughts and emit each ``ThoughtStep`` to *thought_queue*.

        Returns the full LLM response text (empty string in fallback mode).
        Does **not** update ``InvestigationState`` — call ``parse_response()``
        separately if you need state updates too.

        The service calls this method directly when it wants to show reasoning
        for a phase that already handles its own state mutations.
        """
        start = time.perf_counter()
        trace = ThoughtTrace(
            agent=self.agent_name,
            phase=self.phase,
            investigation_id=state.investigation_input.investigation_id,
        )

        if _OBS_AVAILABLE:
            try:
                _M.agent_invocations.labels(           # type: ignore[union-attr]
                    agent_name=self.agent_name, phase=self.phase
                ).inc()
            except Exception:
                pass

        log.info(
            "[%s] starting phase=%s investigation=%s",
            self.agent_name,
            self.phase,
            state.investigation_input.investigation_id,
        )

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        use_llm = _ANTHROPIC_AVAILABLE and bool(api_key)

        full_response = ""
        step_index = 0

        if use_llm:
            try:
                prompt = self.build_prompt(state, adapter, context)
                llm_config = adapter.get_llm_config()
                client = _anthropic.AsyncAnthropic(api_key=api_key)
                parser = StreamingTagParser()

                async with client.messages.stream(
                    model=llm_config["model"],
                    max_tokens=llm_config["max_tokens"],
                    temperature=llm_config["temperature"],
                    system=AGENT_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    async for text in stream.text_stream:  # type: ignore[attr-defined]
                        full_response += text
                        for thought_type, content in parser.feed(text):
                            step = ThoughtStep(
                                step_index=step_index,
                                agent=self.agent_name,
                                phase=self.phase,
                                thought_type=thought_type,  # type: ignore[arg-type]
                                content=content,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                            )
                            trace.steps.append(step)
                            await thought_queue.put(step)
                            step_index += 1

                trace.tokens_used = len(full_response.split())  # rough estimate
            except Exception as exc:
                log.warning(
                    "[%s] LLM call failed, falling back to pattern-based: %s",
                    self.agent_name,
                    exc,
                )
                use_llm = False  # fall through to fallback

        if not use_llm:
            # Emit synthetic thought steps so the UI still shows reasoning
            for thought_type, content in self.build_fallback_thoughts(state, context):
                step = ThoughtStep(
                    step_index=step_index,
                    agent=self.agent_name,
                    phase=self.phase,
                    thought_type=thought_type,  # type: ignore[arg-type]
                    content=content,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                trace.steps.append(step)
                await thought_queue.put(step)
                step_index += 1
                # Small yield to allow SSE to flush between steps
                await asyncio.sleep(0)

        elapsed_ms = round((time.perf_counter() - start) * 1000)
        trace.total_duration_ms = elapsed_ms

        if _OBS_AVAILABLE:
            try:
                _M.agent_duration.labels(agent_name=self.agent_name).observe(elapsed_ms)  # type: ignore[union-attr]
            except Exception:
                pass

        log.info(
            "[%s] completed phase=%s steps=%d duration_ms=%d",
            self.agent_name,
            self.phase,
            len(trace.steps),
            elapsed_ms,
        )

        return full_response

    async def run(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
        thought_queue: "asyncio.Queue[ThoughtStep | None]",
    ) -> InvestigationState:
        """
        Full pipeline: emit thoughts then parse response and update state.

        Callers that want *only* thoughts (while handling state themselves)
        should call ``emit_thoughts()`` directly.
        """
        full_response = await self.emit_thoughts(state, adapter, context, thought_queue)
        updated_state = self.parse_response(full_response, state)
        updated_state.audit_trace.append(AuditTraceEntry(
            agent_type=self.agent_name,
            action=f"reasoning_complete:{self.phase}",
            inputs_summary={"phase": self.phase, "llm_used": bool(full_response)},
            outputs_summary={"response_len": len(full_response)},
            decision="llm_used" if full_response else "fallback_used",
        ))
        return updated_state
