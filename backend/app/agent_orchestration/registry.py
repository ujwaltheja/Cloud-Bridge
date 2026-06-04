"""
Agent Registry

Central registry for agent lifecycle management.
Tracks all active agents, their capabilities, and health status.
"""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("cloudbridge.agent_registry")
settings = get_settings()


class AgentMetadata(BaseModel):
    """Metadata for a registered agent."""
    
    agent_id: UUID
    agent_type: str
    capabilities: list[str]
    status: str = "active"  # active, inactive, error
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_count: int = 0
    error_count: int = 0


class AgentRegistry:
    """
    Central registry for agent lifecycle management.
    
    Uses Redis for fast lookups and distributed coordination.
    Provides agent discovery, health monitoring, and capability queries.
    """
    
    def __init__(self, redis_url: str | None = None):
        """
        Initialize the agent registry.
        
        Args:
            redis_url: Redis connection URL. Defaults to settings.redis_url
        """
        self.redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None
        self._health_check_task: asyncio.Task | None = None
        
    async def connect(self) -> None:
        """Establish Redis connection."""
        if not self._redis:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Agent registry connected to Redis")
            
            # Start health check background task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._health_check_task:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
                
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Agent registry disconnected from Redis")
    
    async def register_agent(
        self,
        agent_id: UUID,
        agent_type: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Register a new agent with the registry.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (e.g., "metadata", "data", "test")
            capabilities: List of capabilities the agent supports
            metadata: Additional metadata about the agent
            
        Raises:
            RuntimeError: If registry is not connected
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected. Call connect() first.")
        
        agent_meta = AgentMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities,
            metadata=metadata or {}
        )
        
        # Store agent metadata
        key = f"agent:{agent_id}"
        await self._redis.set(
            key,
            agent_meta.model_dump_json(),
            ex=3600  # 1 hour TTL, refreshed by heartbeats
        )
        
        # Add to agent type index
        self._redis.sadd(f"agents:type:{agent_type}", str(agent_id))
        
        # Add to capability indexes
        for capability in capabilities:
            self._redis.sadd(f"agents:capability:{capability}", str(agent_id))
        
        # Add to active agents set
        self._redis.sadd("agents:active", str(agent_id))
        
        logger.info(
            "agent.registered",
            agent_id=str(agent_id),
            agent_type=agent_type,
            capabilities=capabilities
        )
    
    async def unregister_agent(self, agent_id: UUID) -> None:
        """
        Remove an agent from the registry.
        
        Args:
            agent_id: ID of the agent to unregister
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        # Get agent metadata before deletion
        agent = await self.get_agent(agent_id)
        if not agent:
            logger.warning("agent.unregister.not_found", agent_id=str(agent_id))
            return
        
        # Remove from indexes
        self._redis.srem(f"agents:type:{agent.agent_type}", str(agent_id))
        for capability in agent.capabilities:
            self._redis.srem(f"agents:capability:{capability}", str(agent_id))
        self._redis.srem("agents:active", str(agent_id))
        
        # Delete agent metadata
        await self._redis.delete(f"agent:{agent_id}")
        
        logger.info("agent.unregistered", agent_id=str(agent_id))
    
    async def get_agent(self, agent_id: UUID) -> AgentMetadata | None:
        """
        Retrieve an agent by ID.
        
        Args:
            agent_id: ID of the agent to retrieve
            
        Returns:
            AgentMetadata if found, None otherwise
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        data = await self._redis.get(f"agent:{agent_id}")
        if not data:
            return None
        
        return AgentMetadata.model_validate_json(data)
    
    async def find_agents_by_capability(
        self,
        capability: str
    ) -> list[AgentMetadata]:
        """
        Find all agents that support a specific capability.
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of agents with the capability
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        agent_ids = await self._redis.smembers(f"agents:capability:{capability}")
        agents = []
        
        for agent_id_str in agent_ids:
            agent = await self.get_agent(UUID(agent_id_str))
            if agent and agent.status == "active":
                agents.append(agent)
        
        return agents
    
    async def find_agents_by_type(self, agent_type: str) -> list[AgentMetadata]:
        """
        Find all agents of a specific type.
        
        Args:
            agent_type: Type of agents to find
            
        Returns:
            List of agents of the specified type
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        agent_ids = await self._redis.smembers(f"agents:type:{agent_type}")
        agents = []
        
        for agent_id_str in agent_ids:
            agent = await self.get_agent(UUID(agent_id_str))
            if agent and agent.status == "active":
                agents.append(agent)
        
        return agents
    
    async def list_all_agents(self) -> list[AgentMetadata]:
        """
        List all registered agents.
        
        Returns:
            List of all agents
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        agent_ids = await self._redis.smembers("agents:active")
        agents = []
        
        for agent_id_str in agent_ids:
            agent = await self.get_agent(UUID(agent_id_str))
            if agent:
                agents.append(agent)
        
        return agents
    
    async def heartbeat(self, agent_id: UUID) -> None:
        """
        Update agent heartbeat timestamp.
        
        Args:
            agent_id: ID of the agent sending heartbeat
        """
        if not self._redis:
            raise RuntimeError("Agent registry not connected")
        
        agent = await self.get_agent(agent_id)
        if not agent:
            logger.warning("agent.heartbeat.not_found", agent_id=str(agent_id))
            return
        
        agent.last_heartbeat = datetime.utcnow()
        
        # Update in Redis with extended TTL
        await self._redis.set(
            f"agent:{agent_id}",
            agent.model_dump_json(),
            ex=3600
        )
    
    async def health_check(self, agent_id: UUID) -> dict[str, Any]:
        """
        Check the health status of an agent.
        
        Args:
            agent_id: ID of the agent to check
            
        Returns:
            Health status dictionary
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            return {
                "agent_id": str(agent_id),
                "status": "not_found",
                "healthy": False
            }
        
        # Check if heartbeat is recent (within last 5 minutes)
        heartbeat_age = datetime.utcnow() - agent.last_heartbeat
        is_healthy = heartbeat_age < timedelta(minutes=5)
        
        return {
            "agent_id": str(agent_id),
            "agent_type": agent.agent_type,
            "status": agent.status,
            "healthy": is_healthy,
            "last_heartbeat": agent.last_heartbeat.isoformat(),
            "heartbeat_age_seconds": heartbeat_age.total_seconds(),
            "execution_count": agent.execution_count,
            "error_count": agent.error_count,
            "error_rate": agent.error_count / max(agent.execution_count, 1)
        }
    
    async def increment_execution_count(self, agent_id: UUID) -> None:
        """Increment the execution count for an agent."""
        agent = await self.get_agent(agent_id)
        if agent:
            agent.execution_count += 1
            await self._redis.set(
                f"agent:{agent_id}",
                agent.model_dump_json(),
                ex=3600
            )
    
    async def increment_error_count(self, agent_id: UUID) -> None:
        """Increment the error count for an agent."""
        agent = await self.get_agent(agent_id)
        if agent:
            agent.error_count += 1
            await self._redis.set(
                f"agent:{agent_id}",
                agent.model_dump_json(),
                ex=3600
            )
    
    async def update_agent_status(
        self,
        agent_id: UUID,
        status: str
    ) -> None:
        """
        Update the status of an agent.
        
        Args:
            agent_id: ID of the agent
            status: New status (active, inactive, error)
        """
        agent = await self.get_agent(agent_id)
        if agent:
            agent.status = status
            await self._redis.set(
                f"agent:{agent_id}",
                agent.model_dump_json(),
                ex=3600
            )
            logger.info(
                "agent.status_updated",
                agent_id=str(agent_id),
                status=status
            )
    
    async def _health_check_loop(self) -> None:
        """Background task to check agent health periodically."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                agents = await self.list_all_agents()
                for agent in agents:
                    health = await self.health_check(agent.agent_id)
                    
                    if not health["healthy"] and agent.status == "active":
                        logger.warning(
                            "agent.unhealthy",
                            agent_id=str(agent.agent_id),
                            heartbeat_age=health["heartbeat_age_seconds"]
                        )
                        await self.update_agent_status(agent.agent_id, "inactive")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("agent.health_check.error", error=str(e))


# Global registry instance
_registry: AgentRegistry | None = None


async def get_agent_registry() -> AgentRegistry:
    """
    Get the global agent registry instance.
    
    Returns:
        AgentRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        await _registry.connect()
    return _registry

# Made with Bob
