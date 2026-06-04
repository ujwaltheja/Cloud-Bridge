"""
Session and context-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str):
    """Message role enumeration."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationMessage(BaseModel):
    """Single conversation message."""
    role: str = Field(..., description="Message role (user/assistant/system/tool)")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(from_attributes=True)


class SessionContextSchema(BaseModel):
    """Session context schema."""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User identifier")
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list, 
        description="Conversation history"
    )
    user_preferences: dict[str, Any] = Field(
        default_factory=dict, 
        description="User preferences"
    )
    active_agents: list[str] = Field(
        default_factory=list, 
        description="Currently active agent IDs"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, 
        description="Additional session metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Session creation time"
    )
    last_activity: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Last activity timestamp"
    )
    expires_at: datetime | None = Field(None, description="Session expiration time")

    model_config = ConfigDict(from_attributes=True)


class SessionCreateRequest(BaseModel):
    """Request to create a new session."""
    user_id: str = Field(..., description="User identifier", min_length=1)
    user_preferences: dict[str, Any] | None = Field(
        None, 
        description="Initial user preferences"
    )
    metadata: dict[str, Any] | None = Field(
        None, 
        description="Additional session metadata"
    )
    ttl_seconds: int | None = Field(
        3600, 
        description="Session TTL in seconds",
        ge=60,
        le=86400
    )

    model_config = ConfigDict(from_attributes=True)


class SessionCreateResponse(BaseModel):
    """Response after session creation."""
    session_id: str = Field(..., description="Created session ID")
    user_id: str = Field(..., description="User ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    message: str = Field(..., description="Status message")

    model_config = ConfigDict(from_attributes=True)


class MessageAddRequest(BaseModel):
    """Request to add a message to session."""
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content", min_length=1)
    metadata: dict[str, Any] | None = Field(None, description="Message metadata")

    model_config = ConfigDict(from_attributes=True)


class MessageAddResponse(BaseModel):
    """Response after adding message."""
    session_id: str = Field(..., description="Session ID")
    message_index: int = Field(..., description="Message index in history")
    timestamp: datetime = Field(..., description="Message timestamp")
    acknowledged: bool = Field(..., description="Message acknowledged")

    model_config = ConfigDict(from_attributes=True)


class SessionUpdateRequest(BaseModel):
    """Request to update session."""
    user_preferences: dict[str, Any] | None = Field(None, description="Updated preferences")
    active_agents: list[str] | None = Field(None, description="Updated active agents")
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")

    model_config = ConfigDict(from_attributes=True)


class SessionHistoryResponse(BaseModel):
    """Response containing conversation history."""
    session_id: str = Field(..., description="Session ID")
    messages: list[ConversationMessage] = Field(..., description="Conversation messages")
    total_messages: int = Field(..., description="Total number of messages")
    user_id: str = Field(..., description="User ID")

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Response containing list of sessions."""
    sessions: list[SessionContextSchema] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")
    active: int = Field(..., description="Number of active sessions")

    model_config = ConfigDict(from_attributes=True)


class PromptContextRequest(BaseModel):
    """Request to build prompt context."""
    session_id: str = Field(..., description="Session ID")
    max_history: int | None = Field(10, description="Max history messages", ge=1, le=100)
    include_preferences: bool = Field(True, description="Include user preferences")
    include_agents: bool = Field(True, description="Include active agents")

    model_config = ConfigDict(from_attributes=True)


class PromptContextResponse(BaseModel):
    """Response containing prompt context."""
    session_id: str = Field(..., description="Session ID")
    context: str = Field(..., description="Formatted prompt context")
    history_count: int = Field(..., description="Number of history messages included")
    preferences: dict[str, Any] | None = Field(None, description="User preferences")
    active_agents: list[str] | None = Field(None, description="Active agent IDs")

    model_config = ConfigDict(from_attributes=True)


class SessionExtendRequest(BaseModel):
    """Request to extend session TTL."""
    additional_seconds: int = Field(
        3600, 
        description="Additional seconds to extend",
        ge=60,
        le=86400
    )

    model_config = ConfigDict(from_attributes=True)


class SessionExtendResponse(BaseModel):
    """Response after extending session."""
    session_id: str = Field(..., description="Session ID")
    new_expires_at: datetime = Field(..., description="New expiration time")
    extended_by: int = Field(..., description="Seconds extended by")

    model_config = ConfigDict(from_attributes=True)

# Made with Bob
