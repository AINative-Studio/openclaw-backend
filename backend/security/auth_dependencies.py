"""
Authentication Dependencies

FastAPI dependencies for authenticating users and extracting current user
from JWT tokens in Authorization header.

Provides:
- get_current_user: Extract and validate authenticated user
- get_current_active_user: Extract authenticated user and verify active status
- optional_current_user: Optional authentication (returns None if not authenticated)

Issue #130: IDOR Prevention
"""

import logging
import os
from typing import Optional
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.models.user import User

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Bearer token scheme
security = HTTPBearer()


class AuthenticationError(HTTPException):
    """Raised when authentication fails"""
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class TokenData:
    """JWT token payload data"""
    def __init__(self, user_id: str, email: str, workspace_id: str):
        self.user_id = user_id
        self.email = email
        self.workspace_id = workspace_id


def create_access_token(
    user_id: str,
    email: str,
    workspace_id: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token for user.

    Args:
        user_id: User UUID as string
        email: User email
        workspace_id: Workspace UUID as string
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded JWT token
    """
    to_encode = {
        "sub": user_id,
        "email": email,
        "workspace_id": workspace_id,
    }

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """
    Decode and validate JWT access token.

    Args:
        token: JWT token string

    Returns:
        TokenData: Extracted token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        workspace_id: str = payload.get("workspace_id")

        if user_id is None or email is None:
            raise AuthenticationError("Invalid token payload")

        return TokenData(user_id=user_id, email=email, workspace_id=workspace_id)

    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise AuthenticationError("Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency: Extract and validate current authenticated user.

    Validates JWT token from Authorization header and returns User object.

    Args:
        credentials: HTTP Bearer credentials from Authorization header
        db: Database session

    Returns:
        User: Authenticated user object

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If user not found in database

    Usage:
        @router.get("/protected")
        def protected_route(current_user: User = Depends(get_current_user)):
            return {"user_id": current_user.id}
    """
    token = credentials.credentials
    token_data = decode_access_token(token)

    # Query user from database
    user = db.query(User).filter(User.id == token_data.user_id).first()

    if user is None:
        logger.warning(f"User {token_data.user_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    FastAPI dependency: Get current user and verify active status.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        User: Active authenticated user

    Raises:
        HTTPException 403: If user account is inactive

    Usage:
        @router.get("/active-only")
        def active_route(current_user: User = Depends(get_current_active_user)):
            return {"user_id": current_user.id}
    """
    if not current_user.is_active:
        logger.warning(f"Inactive user {current_user.id} attempted access")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    return current_user


async def optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    FastAPI dependency: Optional authentication.

    Returns User if valid token provided, None otherwise.
    Does not raise exception if no token provided.

    Args:
        credentials: Optional HTTP Bearer credentials
        db: Database session

    Returns:
        Optional[User]: User if authenticated, None otherwise

    Usage:
        @router.get("/optional-auth")
        def optional_route(user: Optional[User] = Depends(optional_current_user)):
            if user:
                return {"authenticated": True, "user_id": user.id}
            return {"authenticated": False}
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        token_data = decode_access_token(token)

        user = db.query(User).filter(User.id == token_data.user_id).first()
        return user

    except (AuthenticationError, HTTPException):
        # Invalid token - return None instead of raising
        return None


# ============================================================================
# Development-only helpers (remove in production)
# ============================================================================

def create_development_token(
    user_id: str = "00000000-0000-0000-0000-000000000001",
    email: str = "dev@example.com",
    workspace_id: str = "00000000-0000-0000-0000-000000000001"
) -> str:
    """
    Create development token for testing.

    WARNING: Only use in development/testing. Remove in production.

    Args:
        user_id: User UUID
        email: User email
        workspace_id: Workspace UUID

    Returns:
        str: JWT token
    """
    return create_access_token(user_id, email, workspace_id)
