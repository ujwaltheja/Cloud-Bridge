"""
Tool-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolParameterSchema(BaseModel):
    """Tool parameter definition."""
    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Parameter type")
    description: str = Field(..., description="Parameter description")
    required: bool = Field(default=False, description="Whether parameter is required")
    default: Any | None = Field(None, description="Default value")
    enum: list[Any] | None = Field(None, description="Allowed values")

    model_config = ConfigDict(from_attributes=True)


class ToolMetadataSchema(BaseModel):
    """Tool metadata schema."""
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    category: str = Field(..., description="Tool category")
    parameters: list[ToolParameterSchema] = Field(default_factory=list, description="Tool parameters")
    returns: dict[str, Any] = Field(default_factory=dict, description="Return value schema")
    examples: list[dict[str, Any]] = Field(default_factory=list, description="Usage examples")
    tags: list[str] = Field(default_factory=list, description="Tool tags")
    version: str = Field(default="1.0.0", description="Tool version")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update time")

    model_config = ConfigDict(from_attributes=True)


class ToolInvocationRequest(BaseModel):
    """Request to invoke a tool."""
    tool_name: str = Field(..., description="Name of tool to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    context: dict[str, Any] | None = Field(None, description="Execution context")
    timeout: int | None = Field(30, description="Timeout in seconds", ge=1, le=300)

    model_config = ConfigDict(from_attributes=True)


class ToolInvocationResponse(BaseModel):
    """Response from tool invocation."""
    tool_name: str = Field(..., description="Tool that was invoked")
    success: bool = Field(..., description="Whether invocation succeeded")
    result: Any | None = Field(None, description="Tool result")
    error: str | None = Field(None, description="Error message if failed")
    execution_time: float = Field(..., description="Execution time in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Invocation timestamp")

    model_config = ConfigDict(from_attributes=True)


class ToolUsageStats(BaseModel):
    """Tool usage statistics."""
    tool_name: str = Field(..., description="Tool name")
    total_invocations: int = Field(default=0, description="Total number of invocations")
    successful_invocations: int = Field(default=0, description="Successful invocations")
    failed_invocations: int = Field(default=0, description="Failed invocations")
    average_execution_time: float = Field(default=0.0, description="Average execution time")
    last_invoked: datetime | None = Field(None, description="Last invocation time")
    success_rate: float = Field(default=0.0, description="Success rate percentage")

    model_config = ConfigDict(from_attributes=True)


class ToolListResponse(BaseModel):
    """Response containing list of tools."""
    tools: list[ToolMetadataSchema] = Field(..., description="List of available tools")
    total: int = Field(..., description="Total number of tools")
    categories: list[str] = Field(default_factory=list, description="Available categories")

    model_config = ConfigDict(from_attributes=True)


class ToolDiscoveryRequest(BaseModel):
    """Request to discover tools from MCP server."""
    force_refresh: bool = Field(default=False, description="Force refresh from MCP server")

    model_config = ConfigDict(from_attributes=True)


class ToolDiscoveryResponse(BaseModel):
    """Response from tool discovery."""
    discovered: int = Field(..., description="Number of tools discovered")
    cached: int = Field(..., description="Number of tools from cache")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Discovery timestamp")
    tools: list[str] = Field(default_factory=list, description="List of tool names")

    model_config = ConfigDict(from_attributes=True)


class ToolValidationRequest(BaseModel):
    """Request to validate tool arguments."""
    tool_name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(..., description="Arguments to validate")

    model_config = ConfigDict(from_attributes=True)


class ToolValidationResponse(BaseModel):
    """Response from argument validation."""
    valid: bool = Field(..., description="Whether arguments are valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")

    model_config = ConfigDict(from_attributes=True)

# Made with Bob
