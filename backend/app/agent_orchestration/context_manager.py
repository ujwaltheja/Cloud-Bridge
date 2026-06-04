"""
Context Manager

Manages conversation context, user preferences, and session state.
Provides context injection for agent prompts and memory retrieval.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as redis
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("cloudbridge.context_manager")
settings = get_settings()


class Message(BaseModel):
    """A single message in the conversation."""
    
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Complete context for a conversation session."""
    
    session_id: UUID
    user_id: UUID
    org_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    conversation_history: list[Message] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    active_agents: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextManager:
    """
    Manages conversation context, user preferences, and session state.
    
    Provides:
    - Session lifecycle management
    - Conversation history tracking
    - User preference storage
    - Context injection for agent prompts
    """
    
    def __init__(
        self,
        redis_url: str | None = None,
        default_session_ttl: int = 3600
    ):
        """
        Initialize the context manager.
        
        Args:
            redis_url: Redis connection URL
            default_session_ttl: Default session TTL in seconds (1 hour)
        """
        self.redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None
        self.default_session_ttl = default_session_ttl
        
    async def connect(self) -> None:
        """Establish Redis connection."""
        if not self._redis:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Context manager connected to Redis")
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Context manager disconnected from Redis")
    
    async def create_session(
        self,
        user_id: UUID,
        org_id: UUID,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None
    ) -> UUID:
        """
        Create a new conversation session.
        
        Args:
            user_id: ID of the user
            org_id: ID of the Salesforce org
            metadata: Optional session metadata
            ttl_seconds: Session TTL in seconds (defaults to default_session_ttl)
            
        Returns:
            Session ID
        """
        if not self._redis:
            raise RuntimeError("Context manager not connected")
        
        session_id = uuid4()
        ttl = ttl_seconds or self.default_session_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            expires_at=expires_at,
            metadata=metadata or {}
        )
        
        # Store in Redis
        key = f"session:{session_id}"
        await self._redis.set(
            key,
            context.model_dump_json(),
            ex=ttl
        )
        
        # Add to user's session index
        await self._redis.sadd(f"user_sessions:{user_id}", str(session_id))
        
        logger.info(
            "context_manager.session_created",
            session_id=str(session_id),
            user_id=str(user_id),
            org_id=str(org_id)
        )
        
        return session_id
    
    async def get_context(self, session_id: UUID) -> SessionContext | None:
        """
        Retrieve full context for a session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            SessionContext if found, None otherwise
        """
        if not self._redis:
            raise RuntimeError("Context manager not connected")
        
        data = await self._redis.get(f"session:{session_id}")
        if not data:
            return None
        
        return SessionContext.model_validate_json(data)
    
    async def update_context(
        self,
        session_id: UUID,
        updates: dict[str, Any]
    ) -> None:
        """
        Update session context with new information.
        
        Args:
            session_id: ID of the session
            updates: Dictionary of updates to apply
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(context, key):
                setattr(context, key, value)
        
        context.updated_at = datetime.utcnow()
        
        # Save back to Redis
        key = f"session:{session_id}"
        ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
        
        if ttl > 0:
            await self._redis.set(
                key,
                context.model_dump_json(),
                ex=ttl
            )
    
    async def extend_session(
        self,
        session_id: UUID,
        additional_seconds: int = 3600
    ) -> None:
        """
        Extend session expiration time.
        
        Args:
            session_id: ID of the session
            additional_seconds: Seconds to add to expiration
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        context.expires_at = context.expires_at + timedelta(seconds=additional_seconds)
        context.updated_at = datetime.utcnow()
        
        key = f"session:{session_id}"
        ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
        
        if ttl > 0:
            await self._redis.set(
                key,
                context.model_dump_json(),
                ex=ttl
            )
    
    async def delete_session(self, session_id: UUID) -> None:
        """
        Delete a session.
        
        Args:
            session_id: ID of the session to delete
        """
        if not self._redis:
            raise RuntimeError("Context manager not connected")
        
        context = await self.get_context(session_id)
        if context:
            # Remove from user's session index
            await self._redis.srem(
                f"user_sessions:{context.user_id}",
                str(session_id)
            )
        
        # Delete session data
        await self._redis.delete(f"session:{session_id}")
        
        logger.info("context_manager.session_deleted", session_id=str(session_id))
    
    async def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Add a message to the conversation history.
        
        Args:
            session_id: ID of the session
            role: Message role ("user", "assistant", "system")
            content: Message content
            metadata: Optional message metadata
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        context.conversation_history.append(message)
        context.updated_at = datetime.utcnow()
        
        # Save back to Redis
        key = f"session:{session_id}"
        ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
        
        if ttl > 0:
            await self._redis.set(
                key,
                context.model_dump_json(),
                ex=ttl
            )
    
    async def get_conversation_history(
        self,
        session_id: UUID,
        limit: int | None = None,
        role_filter: str | None = None
    ) -> list[Message]:
        """
        Retrieve conversation history for a session.
        
        Args:
            session_id: ID of the session
            limit: Maximum number of messages to return (most recent)
            role_filter: Optional filter by role
            
        Returns:
            List of messages
        """
        context = await self.get_context(session_id)
        if not context:
            return []
        
        messages = context.conversation_history
        
        # Apply role filter
        if role_filter:
            messages = [m for m in messages if m.role == role_filter]
        
        # Apply limit (most recent messages)
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    async def get_user_preferences(
        self,
        session_id: UUID
    ) -> dict[str, Any]:
        """
        Get user preferences for a session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            User preferences dictionary
        """
        context = await self.get_context(session_id)
        if not context:
            return {}
        
        return context.user_preferences
    
    async def update_user_preferences(
        self,
        session_id: UUID,
        preferences: dict[str, Any]
    ) -> None:
        """
        Update user preferences for a session.
        
        Args:
            session_id: ID of the session
            preferences: Preferences to update
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        context.user_preferences.update(preferences)
        context.updated_at = datetime.utcnow()
        
        # Save back to Redis
        key = f"session:{session_id}"
        ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
        
        if ttl > 0:
            await self._redis.set(
                key,
                context.model_dump_json(),
                ex=ttl
            )
    
    async def add_active_agent(
        self,
        session_id: UUID,
        agent_id: str
    ) -> None:
        """
        Add an agent to the active agents list.
        
        Args:
            session_id: ID of the session
            agent_id: ID of the agent to add
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        if agent_id not in context.active_agents:
            context.active_agents.append(agent_id)
            context.updated_at = datetime.utcnow()
            
            # Save back to Redis
            key = f"session:{session_id}"
            ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
            
            if ttl > 0:
                await self._redis.set(
                    key,
                    context.model_dump_json(),
                    ex=ttl
                )
    
    async def remove_active_agent(
        self,
        session_id: UUID,
        agent_id: str
    ) -> None:
        """
        Remove an agent from the active agents list.
        
        Args:
            session_id: ID of the session
            agent_id: ID of the agent to remove
        """
        context = await self.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found")
        
        if agent_id in context.active_agents:
            context.active_agents.remove(agent_id)
            context.updated_at = datetime.utcnow()
            
            # Save back to Redis
            key = f"session:{session_id}"
            ttl = int((context.expires_at - datetime.utcnow()).total_seconds())
            
            if ttl > 0:
                await self._redis.set(
                    key,
                    context.model_dump_json(),
                    ex=ttl
                )
    
    async def get_active_agents(self, session_id: UUID) -> list[str]:
        """
        Get list of active agents for a session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            List of active agent IDs
        """
        context = await self.get_context(session_id)
        if not context:
            return []
        
        return context.active_agents
    
    async def list_user_sessions(
        self,
        user_id: UUID,
        active_only: bool = True
    ) -> list[SessionContext]:
        """
        List all sessions for a user.
        
        Args:
            user_id: ID of the user
            active_only: Only return non-expired sessions
            
        Returns:
            List of session contexts
        """
        if not self._redis:
            raise RuntimeError("Context manager not connected")
        
        session_ids = await self._redis.smembers(f"user_sessions:{user_id}")
        sessions = []
        
        for session_id_str in session_ids:
            context = await self.get_context(UUID(session_id_str))
            if context and (not active_only or context.expires_at > datetime.utcnow()):
                sessions.append(context)
        
        return sessions
    
    async def build_prompt_context(
        self,
        session_id: UUID,
        include_history: bool = True,
        history_limit: int = 10
    ) -> dict[str, Any]:
        """
        Build context dictionary for agent prompt injection.
        
        Args:
            session_id: ID of the session
            include_history: Include conversation history
            history_limit: Maximum history messages to include
            
        Returns:
            Context dictionary for prompt injection
        """
        context = await self.get_context(session_id)
        if not context:
            return {}
        
        prompt_context = {
            "session_id": str(context.session_id),
            "user_id": str(context.user_id),
            "org_id": str(context.org_id),
            "user_preferences": context.user_preferences,
            "active_agents": context.active_agents,
            "metadata": context.metadata
        }
        
        if include_history:
            history = await self.get_conversation_history(
                session_id,
                limit=history_limit
            )
            prompt_context["conversation_history"] = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in history
            ]
        
        return prompt_context


# Global context manager instance
_context_manager: ContextManager | None = None


async def get_context_manager() -> ContextManager:
    """
    Get the global context manager instance.
    
    Returns:
        ContextManager instance
    """
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
        await _context_manager.connect()
    return _context_manager

# Made with Bob
