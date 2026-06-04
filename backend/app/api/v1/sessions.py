"""
Session and Context Manager API endpoints.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.agent_orchestration import get_context_manager
from app.core.logging import get_logger
from app.schemas.session import (
    MessageAddRequest,
    MessageAddResponse,
    PromptContextRequest,
    PromptContextResponse,
    SessionContextSchema,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionExtendRequest,
    SessionExtendResponse,
    SessionHistoryResponse,
    SessionListResponse,
    SessionUpdateRequest,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new session",
    description="Create a new conversation session for a user",
)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """Create a new session."""
    try:
        manager = get_context_manager()
        
        # Create session
        session_id = await manager.create_session(
            user_id=request.user_id,
            user_preferences=request.user_preferences or {},
            metadata=request.metadata or {},
            ttl_seconds=request.ttl_seconds,
        )
        
        # Get created session
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session created but could not retrieve details",
            )
        
        logger.info(f"Session created: {session_id} for user {request.user_id}")
        
        return SessionCreateResponse(
            session_id=session_id,
            user_id=request.user_id,
            created_at=session.created_at,
            expires_at=session.expires_at,
            message="Session created successfully",
        )
    
    except Exception as e:
        logger.error(f"Failed to create session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List sessions",
    description="Get a list of sessions with optional filtering",
)
async def list_sessions(
    user_id: str | None = Query(None, description="Filter by user ID"),
    active_only: bool = Query(False, description="Show only active sessions"),
) -> SessionListResponse:
    """List sessions."""
    try:
        manager = get_context_manager()
        
        # Get all sessions
        all_sessions = await manager.list_sessions(user_id=user_id)
        
        # Filter active sessions if requested
        if active_only:
            # TODO: Implement active session filtering based on expiration
            pass
        
        active_count = len(all_sessions)  # Simplified for now
        
        logger.info(f"Listed {len(all_sessions)} sessions")
        
        return SessionListResponse(
            sessions=[SessionContextSchema(**s.model_dump()) for s in all_sessions],
            total=len(all_sessions),
            active=active_count,
        )
    
    except Exception as e:
        logger.error(f"Failed to list sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@router.get(
    "/{session_id}",
    response_model=SessionContextSchema,
    summary="Get session details",
    description="Get detailed information about a specific session",
)
async def get_session(session_id: str) -> SessionContextSchema:
    """Get session details."""
    try:
        manager = get_context_manager()
        session = await manager.get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        logger.info(f"Retrieved session: {session_id}")
        return SessionContextSchema(**session.model_dump())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}",
        )


@router.patch(
    "/{session_id}",
    response_model=SessionContextSchema,
    summary="Update session",
    description="Update session information",
)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
) -> SessionContextSchema:
    """Update session."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Update session
        updates = request.model_dump(exclude_unset=True)
        await manager.update_session(session_id, **updates)
        
        # Get updated session
        updated_session = await manager.get_session(session_id)
        
        logger.info(f"Session updated: {session_id}")
        return SessionContextSchema(**updated_session.model_dump())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}",
        )


@router.post(
    "/{session_id}/messages",
    response_model=MessageAddResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add message to session",
    description="Add a new message to the conversation history",
)
async def add_message(
    session_id: str,
    request: MessageAddRequest,
) -> MessageAddResponse:
    """Add message to session."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Add message
        await manager.add_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata or {},
        )
        
        # Get updated session to get message index
        updated_session = await manager.get_session(session_id)
        message_index = len(updated_session.conversation_history) - 1
        
        logger.info(f"Message added to session {session_id}")
        
        return MessageAddResponse(
            session_id=session_id,
            message_index=message_index,
            timestamp=updated_session.conversation_history[-1].timestamp,
            acknowledged=True,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add message to session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message: {str(e)}",
        )


@router.get(
    "/{session_id}/history",
    response_model=SessionHistoryResponse,
    summary="Get conversation history",
    description="Get the conversation history for a session",
)
async def get_history(
    session_id: str,
    limit: int | None = Query(None, description="Limit number of messages", ge=1, le=1000),
) -> SessionHistoryResponse:
    """Get conversation history."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Get history
        history = session.conversation_history
        if limit:
            history = history[-limit:]
        
        logger.info(f"Retrieved history for session {session_id}: {len(history)} messages")
        
        return SessionHistoryResponse(
            session_id=session_id,
            messages=history,
            total_messages=len(session.conversation_history),
            user_id=session.user_id,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get history for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get history: {str(e)}",
        )


@router.post(
    "/{session_id}/context",
    response_model=PromptContextResponse,
    summary="Build prompt context",
    description="Build formatted context for LLM prompts",
)
async def build_prompt_context(
    session_id: str,
    request: PromptContextRequest,
) -> PromptContextResponse:
    """Build prompt context."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Build context
        context = await manager.build_prompt_context(
            session_id=session_id,
            max_history=request.max_history,
        )
        
        # Get history count
        history_count = min(request.max_history, len(session.conversation_history))
        
        logger.info(f"Built prompt context for session {session_id}")
        
        return PromptContextResponse(
            session_id=session_id,
            context=context,
            history_count=history_count,
            preferences=session.user_preferences if request.include_preferences else None,
            active_agents=session.active_agents if request.include_agents else None,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build context for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build context: {str(e)}",
        )


@router.post(
    "/{session_id}/extend",
    response_model=SessionExtendResponse,
    summary="Extend session TTL",
    description="Extend the session expiration time",
)
async def extend_session(
    session_id: str,
    request: SessionExtendRequest,
) -> SessionExtendResponse:
    """Extend session TTL."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Extend session
        new_expires_at = await manager.extend_session(
            session_id=session_id,
            additional_seconds=request.additional_seconds,
        )
        
        logger.info(f"Session {session_id} extended by {request.additional_seconds} seconds")
        
        return SessionExtendResponse(
            session_id=session_id,
            new_expires_at=new_expires_at,
            extended_by=request.additional_seconds,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extend session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extend session: {str(e)}",
        )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
    description="Delete a session and its conversation history",
)
async def delete_session(session_id: str) -> None:
    """Delete a session."""
    try:
        manager = get_context_manager()
        
        # Check if session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )
        
        # Delete session
        await manager.delete_session(session_id)
        
        logger.info(f"Session deleted: {session_id}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )

# Made with Bob
