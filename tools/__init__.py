"""tools/ — Kratos analyzer tool implementations."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

#: Registry mapping tool name → BaseTool instance.
#: Populated by :func:`register_all_tools`.
TOOL_REGISTRY: Dict[str, "BaseTool"] = {}


def register_all_tools(llm_config=None) -> Dict[str, "BaseTool"]:
    """
    Instantiate and register all Kratos analysis tools into :data:`TOOL_REGISTRY`.

    Tools that require an LLM backend (SparkLogTool, AirflowLogTool,
    GitDiffTool) accept the optional ``llm_config``; heuristic-only tools
    (DataQualityTool, DDLDiffTool) ignore it.

    Args:
        llm_config: Optional ``LLMConfig`` instance.  When *None* each LLM
                    tool falls back to ``LLMConfig()`` defaults.

    Returns:
        The populated ``TOOL_REGISTRY`` dict (tool name → BaseTool instance).

    Example::

        from tools import register_all_tools, TOOL_REGISTRY
        register_all_tools()
        schema = TOOL_REGISTRY["SparkLogTool"].schema()
    """
    # Deferred imports keep module-level import time fast and prevent circular deps.
    from tools.log_analyzer.spark_log_tool import SparkLogTool
    from tools.log_analyzer.airflow_log_tool import AirflowLogTool
    from tools.code_analyzer.git_diff_tool import GitDiffTool
    from tools.data_profiler.dq_tool import DataQualityTool
    from tools.change_analyzer.ddl_diff_tool import DDLDiffTool

    llm_tools = [
        SparkLogTool(llm_config),
        AirflowLogTool(llm_config),
        GitDiffTool(llm_config),
    ]
    static_tools = [
        DataQualityTool(),
        DDLDiffTool(),
    ]

    for tool in llm_tools + static_tools:
        tool.register(TOOL_REGISTRY)
        logger.debug("Registered tool: %s", tool.name)

    logger.info(
        "Registered %d tools: %s",
        len(TOOL_REGISTRY),
        list(TOOL_REGISTRY),
    )
    return TOOL_REGISTRY

