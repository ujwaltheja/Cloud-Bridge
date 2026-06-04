"""
Tool Registry

Dynamic registry of available MCP tools.
Handles tool discovery, validation, and invocation tracking.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.sfdx_mcp_service import SFDXMCPService
from app.core.config import get_settings

logger = logging.getLogger("cloudbridge.tool_registry")
settings = get_settings()


class ToolMetadata(BaseModel):
    """Metadata for a registered tool."""
    
    name: str
    description: str
    toolset: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    usage_stats: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None


class ToolInvocation(BaseModel):
    """Record of a tool invocation."""
    
    tool_name: str
    org_id: UUID
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    status: str  # success, failed, timeout
    execution_time_ms: float | None = None
    error_message: str | None = None
    invoked_at: datetime = Field(default_factory=datetime.utcnow)


class ToolRegistry:
    """
    Dynamic registry of available MCP tools.
    
    Provides tool discovery, validation, invocation, and analytics.
    Uses Redis for caching and fast lookups.
    """
    
    def __init__(self, redis_url: str | None = None):
        """
        Initialize the tool registry.
        
        Args:
            redis_url: Redis connection URL. Defaults to settings.redis_url
        """
        self.redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None
        self._cache_ttl = 3600  # 1 hour cache for tool metadata
        
    async def connect(self) -> None:
        """Establish Redis connection."""
        if not self._redis:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Tool registry connected to Redis")
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Tool registry disconnected from Redis")
    
    async def discover_tools(
        self,
        org_id: UUID,
        toolsets: str = "orgs,metadata,data,testing,users",
        db: AsyncSession | None = None,
        force_refresh: bool = False
    ) -> list[ToolMetadata]:
        """
        Discover available tools from MCP server.
        
        Args:
            org_id: Organization ID to discover tools for
            toolsets: Comma-separated list of toolsets to enable
            db: Database session for MCP service
            force_refresh: Force refresh from MCP server (bypass cache)
            
        Returns:
            List of discovered tools
        """
        if not self._redis:
            raise RuntimeError("Tool registry not connected")
        
        cache_key = f"tools:discovered:{toolsets}"
        
        # Check cache first
        if not force_refresh:
            cached = await self._redis.get(cache_key)
            if cached:
                logger.debug("tool_registry.cache_hit", toolsets=toolsets)
                tools_data = json.loads(cached)
                return [ToolMetadata(**tool) for tool in tools_data]
        
        # Discover from MCP server
        logger.info("tool_registry.discovering", org_id=str(org_id), toolsets=toolsets)
        
        if not db:
            raise ValueError("Database session required for tool discovery")
        
        mcp_service = SFDXMCPService(db)
        result = await mcp_service.list_tools_for_org(org_id, toolsets=toolsets)
        
        if result.get("status") != "success":
            raise RuntimeError(f"Tool discovery failed: {result.get('error')}")
        
        # Convert to ToolMetadata objects
        tools = []
        for tool_data in result.get("tools", []):
            tool = ToolMetadata(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                toolset=self._extract_toolset(tool_data["name"]),
                input_schema=tool_data.get("inputSchema", {}),
                output_schema=None,  # MCP doesn't provide output schema
                examples=[],
                usage_stats={
                    "total_invocations": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "avg_execution_time_ms": 0.0
                }
            )
            tools.append(tool)
            
            # Store individual tool metadata
            await self._store_tool_metadata(tool)
        
        # Cache the discovered tools
        tools_json = json.dumps([tool.model_dump(mode='json') for tool in tools], default=str)
        await self._redis.set(cache_key, tools_json, ex=self._cache_ttl)
        
        logger.info("tool_registry.discovered", count=len(tools), toolsets=toolsets)
        return tools
    
    def _extract_toolset(self, tool_name: str) -> str:
        """Extract toolset from tool name (heuristic)."""
        # Common patterns: retrieve_metadata, deploy_metadata, query_data, etc.
        if "metadata" in tool_name:
            return "metadata"
        elif "data" in tool_name or "query" in tool_name:
            return "data"
        elif "test" in tool_name or "apex" in tool_name:
            return "testing"
        elif "user" in tool_name or "permission" in tool_name:
            return "users"
        elif "org" in tool_name:
            return "orgs"
        else:
            return "core"
    
    async def _store_tool_metadata(self, tool: ToolMetadata) -> None:
        """Store tool metadata in Redis."""
        if not self._redis:
            return
        
        key = f"tool:{tool.name}"
        await self._redis.set(
            key,
            tool.model_dump_json(),
            ex=self._cache_ttl
        )
    
    async def get_tool(self, tool_name: str) -> ToolMetadata | None:
        """
        Get tool metadata by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            ToolMetadata if found, None otherwise
        """
        if not self._redis:
            raise RuntimeError("Tool registry not connected")
        
        data = await self._redis.get(f"tool:{tool_name}")
        if not data:
            return None
        
        return ToolMetadata.model_validate_json(data)
    
    async def list_tools(
        self,
        toolset: str | None = None
    ) -> list[ToolMetadata]:
        """
        List all registered tools, optionally filtered by toolset.
        
        Args:
            toolset: Optional toolset filter
            
        Returns:
            List of tools
        """
        if not self._redis:
            raise RuntimeError("Tool registry not connected")
        
        # Get all tool keys
        keys = []
        async for key in self._redis.scan_iter("tool:*"):
            keys.append(key)
        
        tools = []
        for key in keys:
            data = await self._redis.get(key)
            if data:
                tool = ToolMetadata.model_validate_json(data)
                if toolset is None or tool.toolset == toolset:
                    tools.append(tool)
        
        return tools
    
    async def validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Validate tool arguments against schema.
        
        Args:
            tool_name: Name of the tool
            arguments: Arguments to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        tool = await self.get_tool(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' not found in registry"
        
        schema = tool.input_schema
        if not schema:
            return True, None  # No schema to validate against
        
        # Basic validation: check required properties
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        # Check required fields
        for field in required:
            if field not in arguments:
                return False, f"Missing required argument: {field}"
        
        # Check field types (basic validation)
        for field, value in arguments.items():
            if field not in properties:
                continue  # Allow extra fields
            
            expected_type = properties[field].get("type")
            if expected_type and not self._validate_type(value, expected_type):
                return False, f"Invalid type for '{field}': expected {expected_type}"
        
        return True, None
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate value against expected JSON schema type."""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        expected_python_type = type_map.get(expected_type)
        if not expected_python_type:
            return True  # Unknown type, skip validation
        
        return isinstance(value, expected_python_type)
    
    async def invoke_tool(
        self,
        org_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        db: AsyncSession,
        timeout: float = 120.0
    ) -> dict[str, Any]:
        """
        Invoke a tool and track the invocation.
        
        Args:
            org_id: Organization ID
            tool_name: Name of the tool to invoke
            arguments: Tool arguments
            db: Database session
            timeout: Execution timeout in seconds
            
        Returns:
            Tool execution result
        """
        # Validate arguments
        is_valid, error = await self.validate_arguments(tool_name, arguments)
        if not is_valid:
            logger.warning(
                "tool_registry.validation_failed",
                tool=tool_name,
                error=error
            )
            return {
                "status": "failed",
                "error": f"Argument validation failed: {error}"
            }
        
        # Invoke via MCP service
        start_time = datetime.utcnow()
        mcp_service = SFDXMCPService(db)
        
        try:
            result = await mcp_service.run_tool(
                org_id=org_id,
                tool_name=tool_name,
                arguments=arguments,
                timeout=timeout
            )
            
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Record invocation
            invocation = ToolInvocation(
                tool_name=tool_name,
                org_id=org_id,
                arguments=arguments,
                result=result,
                status="success" if result.get("status") == "success" else "failed",
                execution_time_ms=execution_time,
                error_message=result.get("error")
            )
            
            await self._record_invocation(invocation)
            await self._update_usage_stats(tool_name, invocation)
            
            return result
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            invocation = ToolInvocation(
                tool_name=tool_name,
                org_id=org_id,
                arguments=arguments,
                status="failed",
                execution_time_ms=execution_time,
                error_message=str(e)
            )
            
            await self._record_invocation(invocation)
            await self._update_usage_stats(tool_name, invocation)
            
            logger.error(
                "tool_registry.invocation_failed",
                tool=tool_name,
                error=str(e)
            )
            
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def _record_invocation(self, invocation: ToolInvocation) -> None:
        """Record a tool invocation for analytics."""
        if not self._redis:
            return
        
        # Store in a sorted set by timestamp
        key = f"invocations:{invocation.tool_name}"
        score = invocation.invoked_at.timestamp()
        value = invocation.model_dump_json()
        
        await self._redis.zadd(key, {value: score})
        
        # Keep only last 1000 invocations per tool
        await self._redis.zremrangebyrank(key, 0, -1001)
    
    async def _update_usage_stats(
        self,
        tool_name: str,
        invocation: ToolInvocation
    ) -> None:
        """Update usage statistics for a tool."""
        tool = await self.get_tool(tool_name)
        if not tool:
            return
        
        stats = tool.usage_stats
        stats["total_invocations"] = stats.get("total_invocations", 0) + 1
        
        if invocation.status == "success":
            stats["success_count"] = stats.get("success_count", 0) + 1
        else:
            stats["failure_count"] = stats.get("failure_count", 0) + 1
        
        # Update average execution time
        if invocation.execution_time_ms:
            current_avg = stats.get("avg_execution_time_ms", 0.0)
            total = stats["total_invocations"]
            new_avg = ((current_avg * (total - 1)) + invocation.execution_time_ms) / total
            stats["avg_execution_time_ms"] = new_avg
        
        tool.usage_stats = stats
        tool.last_used_at = invocation.invoked_at
        
        await self._store_tool_metadata(tool)
    
    async def get_tool_usage_stats(
        self,
        tool_name: str | None = None
    ) -> dict[str, Any]:
        """
        Get usage statistics for tools.
        
        Args:
            tool_name: Optional specific tool name
            
        Returns:
            Usage statistics
        """
        if tool_name:
            tool = await self.get_tool(tool_name)
            if not tool:
                return {}
            
            return {
                "tool_name": tool.name,
                "toolset": tool.toolset,
                "usage_stats": tool.usage_stats,
                "last_used_at": tool.last_used_at.isoformat() if tool.last_used_at else None
            }
        else:
            # Get stats for all tools
            tools = await self.list_tools()
            return {
                "total_tools": len(tools),
                "tools": [
                    {
                        "name": tool.name,
                        "toolset": tool.toolset,
                        "usage_stats": tool.usage_stats
                    }
                    for tool in tools
                ]
            }
    
    async def get_recent_invocations(
        self,
        tool_name: str,
        limit: int = 100
    ) -> list[ToolInvocation]:
        """
        Get recent invocations for a tool.
        
        Args:
            tool_name: Name of the tool
            limit: Maximum number of invocations to return
            
        Returns:
            List of recent invocations
        """
        if not self._redis:
            raise RuntimeError("Tool registry not connected")
        
        key = f"invocations:{tool_name}"
        
        # Get most recent invocations (highest scores)
        results = await self._redis.zrevrange(key, 0, limit - 1)
        
        invocations = []
        for data in results:
            invocation = ToolInvocation.model_validate_json(data)
            invocations.append(invocation)
        
        return invocations


# Global registry instance
_tool_registry: ToolRegistry | None = None


async def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.
    
    Returns:
        ToolRegistry instance
    """
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
        await _tool_registry.connect()
    return _tool_registry

# Made with Bob
