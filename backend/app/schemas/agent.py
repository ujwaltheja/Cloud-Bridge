"""
Agent-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentType(str, Enum):
    """Agent type enumeration."""
    METADATA = "metadata"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    DATA = "data"
    ORG_MANAGEMENT = "org_management"
    CODE_ANALYSIS = "code_analysis"
    ORCHESTRATOR = "orchestrator"


class AgentStatus(str, Enum):
    """Agent status enumeration."""
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class AgentCapability(BaseModel):
    """Agent capability definition."""
    name: str = Field(..., description="Capability name")
    description: str = Field(..., description="Capability description")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Capability parameters")

    model_config = ConfigDict(from_attributes=True)


class AgentMetadataSchema(BaseModel):
    """Agent metadata schema."""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    agent_type: AgentType = Field(..., description="Agent type")
    description: str = Field(..., description="Agent description")
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    status: AgentStatus = Field(default=AgentStatus.IDLE, description="Current agent status")
    version: str = Field(default="1.0.0", description="Agent version")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    last_heartbeat: datetime | None = Field(None, description="Last heartbeat timestamp")

    model_config = ConfigDict(from_attributes=True)


class AgentRegistrationRequest(BaseModel):
    """Request to register a new agent."""
    name: str = Field(..., description="Agent name", min_length=1, max_length=100)
    agent_type: AgentType = Field(..., description="Agent type")
    description: str = Field(..., description="Agent description", max_length=500)
    capabilities: list[str] = Field(..., description="List of capabilities", min_length=1)
    version: str = Field(default="1.0.0", description="Agent version")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(from_attributes=True)


class AgentRegistrationResponse(BaseModel):
    """Response after agent registration."""
    agent_id: str = Field(..., description="Assigned agent ID")
    message: str = Field(..., description="Registration status message")
    agent: AgentMetadataSchema = Field(..., description="Registered agent details")

    model_config = ConfigDict(from_attributes=True)


class AgentUpdateRequest(BaseModel):
    """Request to update agent information."""
    name: str | None = Field(None, description="Updated agent name")
    description: str | None = Field(None, description="Updated description")
    capabilities: list[str] | None = Field(None, description="Updated capabilities")
    status: AgentStatus | None = Field(None, description="Updated status")
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")

    model_config = ConfigDict(from_attributes=True)


class AgentHeartbeatRequest(BaseModel):
    """Request to send agent heartbeat."""
    status: AgentStatus = Field(..., description="Current agent status")
    metadata: dict[str, Any] | None = Field(None, description="Additional status metadata")

    model_config = ConfigDict(from_attributes=True)


class AgentHeartbeatResponse(BaseModel):
    """Response after heartbeat."""
    agent_id: str = Field(..., description="Agent ID")
    acknowledged: bool = Field(..., description="Heartbeat acknowledged")
    timestamp: datetime = Field(..., description="Server timestamp")

    model_config = ConfigDict(from_attributes=True)


class AgentListResponse(BaseModel):
    """Response containing list of agents."""
    agents: list[AgentMetadataSchema] = Field(..., description="List of agents")
    total: int = Field(..., description="Total number of agents")
    filtered: int = Field(..., description="Number of filtered agents")

    model_config = ConfigDict(from_attributes=True)


class AgentHealthCheckResponse(BaseModel):
    """Response for agent health check."""
    agent_id: str = Field(..., description="Agent ID")
    status: AgentStatus = Field(..., description="Health status")
    last_heartbeat: datetime | None = Field(None, description="Last heartbeat time")
    is_healthy: bool = Field(..., description="Overall health indicator")
    details: dict[str, Any] = Field(default_factory=dict, description="Health check details")

    model_config = ConfigDict(from_attributes=True)

# Made with Bob
