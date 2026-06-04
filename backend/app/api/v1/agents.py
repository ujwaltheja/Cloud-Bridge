"""
Agent Registry API endpoints.
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.agent_orchestration import get_agent_registry
from app.core.logging import get_logger
from app.schemas.agent import (
    AgentHealthCheckResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentListResponse,
    AgentMetadataSchema,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentStatus,
    AgentType,
    AgentUpdateRequest,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent",
    description="Register a new agent with the orchestration system",
)
async def register_agent(request: AgentRegistrationRequest) -> AgentRegistrationResponse:
    """Register a new agent."""
    try:
        registry = get_agent_registry()
        
        # Register the agent
        agent_id = await registry.register_agent(
            name=request.name,
            agent_type=request.agent_type.value,
            description=request.description,
            capabilities=request.capabilities,
            version=request.version,
            metadata=request.metadata,
        )
        
        # Get the registered agent details
        agent = await registry.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent registered but could not retrieve details",
            )
        
        logger.info(f"Agent registered successfully: {agent_id}")
        
        return AgentRegistrationResponse(
            agent_id=agent_id,
            message="Agent registered successfully",
            agent=AgentMetadataSchema(**agent.model_dump()),
        )
    
    except Exception as e:
        logger.error(f"Failed to register agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register agent: {str(e)}",
        )


@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all agents",
    description="Get a list of all registered agents with optional filtering",
)
async def list_agents(
    agent_type: AgentType | None = Query(None, description="Filter by agent type"),
    capability: str | None = Query(None, description="Filter by capability"),
    status_filter: AgentStatus | None = Query(None, alias="status", description="Filter by status"),
) -> AgentListResponse:
    """List all agents with optional filtering."""
    try:
        registry = get_agent_registry()
        
        # Get all agents
        all_agents = await registry.list_agents()
        
        # Apply filters
        filtered_agents = all_agents
        
        if agent_type:
            filtered_agents = [a for a in filtered_agents if a.agent_type == agent_type.value]
        
        if capability:
            capability_agents = await registry.find_agents_by_capability(capability)
            capability_ids = {a.agent_id for a in capability_agents}
            filtered_agents = [a for a in filtered_agents if a.agent_id in capability_ids]
        
        if status_filter:
            filtered_agents = [a for a in filtered_agents if a.status == status_filter.value]
        
        logger.info(f"Listed {len(filtered_agents)} agents (total: {len(all_agents)})")
        
        return AgentListResponse(
            agents=[AgentMetadataSchema(**a.model_dump()) for a in filtered_agents],
            total=len(all_agents),
            filtered=len(filtered_agents),
        )
    
    except Exception as e:
        logger.error(f"Failed to list agents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get(
    "/{agent_id}",
    response_model=AgentMetadataSchema,
    summary="Get agent details",
    description="Get detailed information about a specific agent",
)
async def get_agent(agent_id: str) -> AgentMetadataSchema:
    """Get agent details by ID."""
    try:
        registry = get_agent_registry()
        agent = await registry.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )
        
        logger.info(f"Retrieved agent details: {agent_id}")
        return AgentMetadataSchema(**agent.model_dump())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}",
        )


@router.patch(
    "/{agent_id}",
    response_model=AgentMetadataSchema,
    summary="Update agent",
    description="Update agent information",
)
async def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
) -> AgentMetadataSchema:
    """Update agent information."""
    try:
        registry = get_agent_registry()
        
        # Check if agent exists
        agent = await registry.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )
        
        # Update agent
        updates = request.model_dump(exclude_unset=True)
        if "status" in updates:
            updates["status"] = updates["status"].value
        
        await registry.update_agent(agent_id, **updates)
        
        # Get updated agent
        updated_agent = await registry.get_agent(agent_id)
        
        logger.info(f"Agent updated successfully: {agent_id}")
        return AgentMetadataSchema(**updated_agent.model_dump())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.post(
    "/{agent_id}/heartbeat",
    response_model=AgentHeartbeatResponse,
    summary="Send agent heartbeat",
    description="Update agent status and last heartbeat timestamp",
)
async def agent_heartbeat(
    agent_id: str,
    request: AgentHeartbeatRequest,
) -> AgentHeartbeatResponse:
    """Send agent heartbeat."""
    try:
        registry = get_agent_registry()
        
        # Check if agent exists
        agent = await registry.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )
        
        # Update heartbeat
        await registry.update_agent(
            agent_id,
            status=request.status.value,
            last_heartbeat=datetime.utcnow(),
            metadata={**agent.metadata, **(request.metadata or {})},
        )
        
        logger.debug(f"Heartbeat received from agent: {agent_id}")
        
        return AgentHeartbeatResponse(
            agent_id=agent_id,
            acknowledged=True,
            timestamp=datetime.utcnow(),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process heartbeat for {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process heartbeat: {str(e)}",
        )


@router.get(
    "/{agent_id}/health",
    response_model=AgentHealthCheckResponse,
    summary="Check agent health",
    description="Check the health status of an agent",
)
async def check_agent_health(agent_id: str) -> AgentHealthCheckResponse:
    """Check agent health."""
    try:
        registry = get_agent_registry()
        
        # Check if agent exists
        agent = await registry.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )
        
        # Perform health check
        is_healthy = await registry.health_check(agent_id)
        
        # Calculate time since last heartbeat
        details = {}
        if agent.last_heartbeat:
            time_since_heartbeat = (datetime.utcnow() - agent.last_heartbeat).total_seconds()
            details["seconds_since_heartbeat"] = time_since_heartbeat
            details["heartbeat_threshold"] = 300  # 5 minutes
        
        logger.info(f"Health check for agent {agent_id}: {'healthy' if is_healthy else 'unhealthy'}")
        
        return AgentHealthCheckResponse(
            agent_id=agent_id,
            status=AgentStatus(agent.status),
            last_heartbeat=agent.last_heartbeat,
            is_healthy=is_healthy,
            details=details,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check health for {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check agent health: {str(e)}",
        )


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deregister agent",
    description="Remove an agent from the registry",
)
async def deregister_agent(agent_id: str) -> None:
    """Deregister an agent."""
    try:
        registry = get_agent_registry()
        
        # Check if agent exists
        agent = await registry.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )
        
        # Deregister agent
        await registry.deregister_agent(agent_id)
        
        logger.info(f"Agent deregistered successfully: {agent_id}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deregister agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deregister agent: {str(e)}",
        )

# Made with Bob
