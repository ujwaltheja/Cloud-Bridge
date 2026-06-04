"""
Agent Orchestration Module

Provides core agent orchestration capabilities including:
- Agent registry and lifecycle management
- Tool registry and discovery
- Context and memory management
- Multi-agent coordination
- Planning and execution
"""

from .context_manager import ContextManager, get_context_manager
from .registry import AgentRegistry, get_agent_registry
from .tool_registry import ToolRegistry, get_tool_registry

__all__ = [
    "AgentRegistry",
    "ToolRegistry",
    "ContextManager",
    "get_agent_registry",
    "get_tool_registry",
    "get_context_manager",
]

# Made with Bob
