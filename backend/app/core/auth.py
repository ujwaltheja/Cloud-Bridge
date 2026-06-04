"""
Authentication dependencies for FastAPI endpoints.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer

from app.core.logging import get_logger
from app.core.security import TokenData, decode_token, verify_token_type

logger = get_logger(__name__)

# OAuth2 scheme for Swagger UI
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)

# HTTP Bearer scheme for API clients
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    token: str | None = Depends(oauth2_scheme),
) -> TokenData:
    """
    Get the current authenticated user from JWT token.
    
    Supports both Bearer token (from Authorization header) and OAuth2 token.
    
    Args:
        credentials: HTTP Bearer credentials
        token: OAuth2 token
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If authentication fails
    """
    # Try Bearer token first, then OAuth2 token
    auth_token = None
    if credentials:
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify it's an access token
    if not verify_token_type(auth_token, "access"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode token
    token_data = decode_token(auth_token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"Authenticated user: {token_data.user_id}")
    return token_data


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    token: str | None = Depends(oauth2_scheme),
) -> TokenData | None:
    """
    Get the current user if authenticated, None otherwise.
    
    Useful for endpoints that work with or without authentication.
    
    Args:
        credentials: HTTP Bearer credentials
        token: OAuth2 token
        
    Returns:
        TokenData if authenticated, None otherwise
    """
    try:
        return await get_current_user(credentials, token)
    except HTTPException:
        return None


def require_scope(required_scope: str):
    """
    Dependency factory to require a specific scope.
    
    Args:
        required_scope: The scope required to access the endpoint
        
    Returns:
        Dependency function that checks for the scope
    """
    async def scope_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if required_scope not in current_user.scopes:
            logger.warning(
                f"User {current_user.user_id} missing required scope: {required_scope}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
            )
        return current_user
    
    return scope_checker


def require_any_scope(*required_scopes: str):
    """
    Dependency factory to require any of the specified scopes.
    
    Args:
        required_scopes: Any of these scopes will grant access
        
    Returns:
        Dependency function that checks for any of the scopes
    """
    async def scope_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if not any(scope in current_user.scopes for scope in required_scopes):
            logger.warning(
                f"User {current_user.user_id} missing any of required scopes: {required_scopes}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope. Need one of: {', '.join(required_scopes)}",
            )
        return current_user
    
    return scope_checker


def require_all_scopes(*required_scopes: str):
    """
    Dependency factory to require all of the specified scopes.
    
    Args:
        required_scopes: All of these scopes are required
        
    Returns:
        Dependency function that checks for all scopes
    """
    async def scope_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        missing_scopes = [scope for scope in required_scopes if scope not in current_user.scopes]
        if missing_scopes:
            logger.warning(
                f"User {current_user.user_id} missing required scopes: {missing_scopes}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing_scopes)}",
            )
        return current_user
    
    return scope_checker

# Made with Bob
