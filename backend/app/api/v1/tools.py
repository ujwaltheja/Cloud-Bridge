"""
Tool Registry API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status

from app.agent_orchestration import get_tool_registry
from app.core.logging import get_logger
from app.schemas.tool import (
    ToolDiscoveryRequest,
    ToolDiscoveryResponse,
    ToolInvocationRequest,
    ToolInvocationResponse,
    ToolListResponse,
    ToolMetadataSchema,
    ToolUsageStats,
    ToolValidationRequest,
    ToolValidationResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/tools", tags=["tools"])


@router.post(
    "/discover",
    response_model=ToolDiscoveryResponse,
    summary="Discover tools",
    description="Discover available tools from MCP server",
)
async def discover_tools(request: ToolDiscoveryRequest) -> ToolDiscoveryResponse:
    """Discover tools from MCP server."""
    try:
        registry = get_tool_registry()
        
        # Discover tools
        tools = await registry.discover_tools(force_refresh=request.force_refresh)
        
        # Count cached vs discovered
        cached_count = 0 if request.force_refresh else len(tools)
        discovered_count = len(tools) if request.force_refresh else 0
        
        logger.info(f"Discovered {len(tools)} tools (force_refresh={request.force_refresh})")
        
        return ToolDiscoveryResponse(
            discovered=discovered_count,
            cached=cached_count,
            tools=[tool.name for tool in tools],
        )
    
    except Exception as e:
        logger.error(f"Failed to discover tools: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover tools: {str(e)}",
        )


@router.get(
    "",
    response_model=ToolListResponse,
    summary="List all tools",
    description="Get a list of all available tools with optional filtering",
)
async def list_tools(
    category: str | None = Query(None, description="Filter by category"),
    tag: str | None = Query(None, description="Filter by tag"),
) -> ToolListResponse:
    """List all available tools."""
    try:
        registry = get_tool_registry()
        
        # Get all tools
        all_tools = await registry.list_tools()
        
        # Apply filters
        filtered_tools = all_tools
        
        if category:
            filtered_tools = [t for t in filtered_tools if t.category == category]
        
        if tag:
            filtered_tools = [t for t in filtered_tools if tag in t.tags]
        
        # Get unique categories
        categories = list({tool.category for tool in all_tools})
        
        logger.info(f"Listed {len(filtered_tools)} tools (total: {len(all_tools)})")
        
        return ToolListResponse(
            tools=[ToolMetadataSchema(**t.model_dump()) for t in filtered_tools],
            total=len(all_tools),
            categories=categories,
        )
    
    except Exception as e:
        logger.error(f"Failed to list tools: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tools: {str(e)}",
        )


@router.get(
    "/{tool_name}",
    response_model=ToolMetadataSchema,
    summary="Get tool details",
    description="Get detailed information about a specific tool",
)
async def get_tool(tool_name: str) -> ToolMetadataSchema:
    """Get tool details by name."""
    try:
        registry = get_tool_registry()
        tool = await registry.get_tool(tool_name)
        
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_name}",
            )
        
        logger.info(f"Retrieved tool details: {tool_name}")
        return ToolMetadataSchema(**tool.model_dump())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tool {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tool: {str(e)}",
        )


@router.post(
    "/{tool_name}/invoke",
    response_model=ToolInvocationResponse,
    summary="Invoke a tool",
    description="Execute a tool with provided arguments",
)
async def invoke_tool(
    tool_name: str,
    request: ToolInvocationRequest,
) -> ToolInvocationResponse:
    """Invoke a tool."""
    try:
        registry = get_tool_registry()
        
        # Validate tool exists
        tool = await registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_name}",
            )
        
        # Invoke the tool
        result = await registry.invoke_tool(
            tool_name=tool_name,
            arguments=request.arguments,
            context=request.context or {},
            timeout=request.timeout,
        )
        
        logger.info(f"Tool invoked: {tool_name} (success={result.success})")
        
        return ToolInvocationResponse(
            tool_name=tool_name,
            success=result.success,
            result=result.result,
            error=result.error,
            execution_time=result.execution_time,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invoke tool {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invoke tool: {str(e)}",
        )


@router.post(
    "/{tool_name}/validate",
    response_model=ToolValidationResponse,
    summary="Validate tool arguments",
    description="Validate arguments against tool schema",
)
async def validate_tool_arguments(
    tool_name: str,
    request: ToolValidationRequest,
) -> ToolValidationResponse:
    """Validate tool arguments."""
    try:
        registry = get_tool_registry()
        
        # Validate tool exists
        tool = await registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_name}",
            )
        
        # Validate arguments
        is_valid, errors = await registry.validate_arguments(tool_name, request.arguments)
        
        logger.info(f"Arguments validated for {tool_name}: valid={is_valid}")
        
        return ToolValidationResponse(
            valid=is_valid,
            errors=errors,
            warnings=[],
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate arguments for {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate arguments: {str(e)}",
        )


@router.get(
    "/{tool_name}/stats",
    response_model=ToolUsageStats,
    summary="Get tool usage statistics",
    description="Get usage statistics for a specific tool",
)
async def get_tool_stats(tool_name: str) -> ToolUsageStats:
    """Get tool usage statistics."""
    try:
        registry = get_tool_registry()
        
        # Validate tool exists
        tool = await registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_name}",
            )
        
        # Get statistics
        stats = await registry.get_tool_stats(tool_name)
        
        if not stats:
            # Return empty stats if none exist
            return ToolUsageStats(
                tool_name=tool_name,
                total_invocations=0,
                successful_invocations=0,
                failed_invocations=0,
                average_execution_time=0.0,
                last_invoked=None,
                success_rate=0.0,
            )
        
        logger.info(f"Retrieved stats for tool: {tool_name}")
        return ToolUsageStats(**stats)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stats for {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tool stats: {str(e)}",
        )

# Made with Bob
