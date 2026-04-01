"""
core/llm.py
LLM configuration and async call helpers for the Kratos agent system.

Extracted from: src/agents/base.py (LLMConfig class + _get_llm / _create_chain / _call_llm methods)

Usage
-----
>>> from core.llm import LLMConfig, _call_llm_async
>>> config = LLMConfig(provider="openai", model="gpt-4.1")
>>> response = await _call_llm_async("You are...", "Analyse this...", config, "MyAgent")
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field
from dotenv import load_dotenv

if TYPE_CHECKING:
    from workflow.context_layer import AgentContext

logger = logging.getLogger(__name__)

_DOTENV_LOADED = False

# Cache: (provider, model, temperature, max_tokens) → LLM client instance
_LLM_CACHE: dict[tuple, Any] = {}


# ============================================================================
# LLM CONFIGURATION
# ============================================================================

class LLMConfig(BaseModel):
    """LLM provider configuration. Shared across all agents."""

    model_config = {"protected_namespaces": ()}

    provider:    str   = Field(default="openai",  description="openai | anthropic")
    model:       str   = Field(default="gpt-4.1", description="Model name")
    temperature: float = Field(default=0.2,       description="Sampling temperature")
    max_tokens:  int   = Field(default=4000,      description="Max response tokens")


# ============================================================================
# LLM FACTORY
# ============================================================================

def _load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        repo_root = Path(__file__).resolve().parents[1]
        load_dotenv(repo_root / ".env", override=False)
        _DOTENV_LOADED = True


def get_llm(llm_config: LLMConfig) -> Any:
    """
    Return a cached LangChain LLM client for the given config.

    Clients are keyed by (provider, model, temperature, max_tokens) so the
    same underlying HTTP connection pool is reused across calls.  This
    eliminates the ~5 s per-call overhead of constructing a new ChatOpenAI
    every time.
    """
    _load_dotenv_once()

    cache_key = (
        llm_config.provider,
        llm_config.model,
        llm_config.temperature,
        llm_config.max_tokens,
    )

    cached = _LLM_CACHE.get(cache_key)
    if cached is not None:
        return cached

    logger.info(
        "[LLM] Initializing %s | model=%s | temp=%s | max_tokens=%s",
        llm_config.provider,
        llm_config.model,
        llm_config.temperature,
        llm_config.max_tokens,
    )

    if llm_config.provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model       = llm_config.model,
            temperature = llm_config.temperature,
            max_tokens  = llm_config.max_tokens,
        )
    elif llm_config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model       = llm_config.model,
            temperature = llm_config.temperature,
            max_tokens  = llm_config.max_tokens,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider: {llm_config.provider!r}. Supported: openai, anthropic"
        )

    _LLM_CACHE[cache_key] = llm
    return llm


def build_chain(llm_config: LLMConfig, system_prompt: str) -> Any:
    """Build a LangChain chain: ChatPromptTemplate | LLM | StrOutputParser."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    llm    = get_llm(llm_config)
    # Escape any literal curly braces in the system prompt so LangChain
    # doesn't interpret them as template variables (e.g. JSON snippets,
    # code fragments in evidence text).
    safe_system = system_prompt.replace("{", "{{").replace("}", "}}")
    prompt = ChatPromptTemplate.from_messages([
        ("system", safe_system),
        ("human", "{input}"),
    ])
    return prompt | llm | StrOutputParser()


async def _call_llm_async(
    system_prompt: str,
    user_prompt:   str,
    llm_config:    LLMConfig,
    agent_name:    str = "Agent",
) -> str:
    """
    Invoke LLM asynchronously via LangChain.

    Logs prompt sizes, token estimates, elapsed time, and response size.

    Returns:
        Raw LLM response string.
    """
    est_tokens = (len(system_prompt) + len(user_prompt)) // 4
    logger.info(
        "[%s] LLM call | sys=%dc | usr=%dc | ~%d tokens",
        agent_name, len(system_prompt), len(user_prompt), est_tokens,
    )

    chain   = build_chain(llm_config, system_prompt)
    start   = time.time()
    response = await chain.ainvoke({"input": user_prompt})
    elapsed  = time.time() - start

    logger.info(
        "[%s] Response in %.2fs | %dc (~%d tokens)",
        agent_name, elapsed, len(response), len(response) // 4,
    )
    return response


# ============================================================================
# PROMPT ENRICHMENT HELPER
# ============================================================================

def _enrich_prompt_with_context(
    base_prompt: str,
    context: Optional["AgentContext"],
    agent_name: str = "Agent",
) -> str:
    """
    Append prior agent findings and focus areas to a prompt.
    Called inside BaseAgent.analyze() before the LLM call.
    """
    if not context:
        return base_prompt

    findings_summary = context.get_findings_summary()
    focus_areas      = context.get_focus_areas()
    enrichment: list[str] = []

    if findings_summary and findings_summary != "No previous findings.":
        enrichment.append(
            f"\n\n--- Previous Agent Findings ---\n{findings_summary}"
        )

    if focus_areas:
        enrichment.append(
            f"\n\n--- Focus Areas ---\n"
            f"Pay special attention to: {', '.join(focus_areas)}"
        )

    if enrichment:
        logger.info(
            "[%s] Enriching prompt with %d prior finding(s)",
            agent_name, len(context.get_findings()),
        )
        return base_prompt + "".join(enrichment)

    return base_prompt
