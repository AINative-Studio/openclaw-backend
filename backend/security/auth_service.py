"""
JWT Authentication Service

Provides JWT token generation, validation, and user authentication for the OpenClaw Backend.
Implements secure password hashing with bcrypt and JWT token management with configurable expiration.

Security Features:
- Bcrypt password hashing with automatic salting
- HS256 JWT signing with configurable secret key
- Token expiration and validation
- Automatic token refresh mechanism
- User authentication and authorization
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
import httpx

from backend.models.user import User
from backend.db.base import get_db, get_async_db


# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token authentication scheme
security = HTTPBearer()

# JWT configuration from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY"))
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY or SECRET_KEY environment variable is required for JWT authentication. "
        "Generate a secure key: openssl rand -hex 32"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# AINative API Configuration
AINATIVE_API_URL = os.getenv("AINATIVE_API_URL", "https://api.ainative.studio")


class AuthService:
    """
    Authentication service for password hashing and JWT token management

    This service provides methods for:
    - Password hashing and verification
    - JWT token creation and validation
    - User authentication
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a plain text password using bcrypt

        Args:
            password: Plain text password to hash

        Returns:
            Hashed password string
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain text password against a hashed password

        Args:
            plain_password: Plain text password to verify
            hashed_password: Hashed password to compare against

        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token

        Args:
            data: Payload data to encode in the token
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token string
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        })

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """
        Create a JWT refresh token with extended expiration

        Args:
            data: Payload data to encode in the token

        Returns:
            Encoded JWT refresh token string
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh"
        })

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """
        Verify and decode a JWT token

        Args:
            token: JWT token string to verify

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    async def _authenticate_with_ainative(email: str, password: str) -> Optional[dict]:
        """
        Authenticate user with AINative API

        Args:
            email: User email
            password: Plain text password

        Returns:
            User data dictionary if successful, None otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{AINATIVE_API_URL}/v1/public/auth/login",
                    data={"username": email, "password": password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "email": email,
                        "full_name": data.get("user", {}).get("fullName", email.split("@")[0]),
                        "is_active": True
                    }
        except Exception:
            # Silently fail and fall back to local authentication
            pass

        return None

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user by email and password

        Tries AINative API first, then falls back to local database authentication.
        Auto-creates user if AINative authentication succeeds but user doesn't exist locally.

        Args:
            db: Async database session
            email: User email
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        # Try AINative API authentication first
        ainative_data = await AuthService._authenticate_with_ainative(email, password)

        if ainative_data:
            # AINative authentication successful - check if user exists locally
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalars().first()

            if not user:
                # Auto-create user from AINative authentication
                # Get or create default workspace
                from backend.models.workspace import Workspace
                workspace_result = await db.execute(select(Workspace).limit(1))
                workspace = workspace_result.scalars().first()

                if not workspace:
                    # Create default workspace if none exists
                    workspace = Workspace(
                        name="Default Workspace",
                        comment="Auto-created default workspace"
                    )
                    db.add(workspace)
                    await db.flush()  # Flush to get workspace.id

                # Create user with workspace and hashed password
                user = User(
                    email=ainative_data["email"],
                    full_name=ainative_data["full_name"],
                    is_active=True,
                    password_hash=AuthService.hash_password(password),  # Hash the password
                    workspace_id=workspace.id  # Required field
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            return user if user.is_active else None

        # Fall back to local database authentication
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if not user:
            return None

        if not user.password_hash:
            # User doesn't have a password set yet
            return None

        if not AuthService.verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        return user

    @staticmethod
    def authenticate_user_sync(db: Session, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user by email and password (synchronous version)

        Args:
            db: Database session
            email: User email
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        user = db.query(User).filter(User.email == email).first()

        if not user:
            return None

        if not user.password_hash:
            # User doesn't have a password set yet
            return None

        if not AuthService.verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token

    Args:
        credentials: HTTP Bearer token credentials
        db: Async database session

    Returns:
        Current authenticated User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Verify and decode token
    payload = AuthService.verify_token(token)

    # Extract user ID from token
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token type
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_async_db)
) -> Optional[User]:
    """
    Dependency to optionally get the current authenticated user

    Returns None if no token is provided instead of raising an error.
    Useful for endpoints that have optional authentication.

    Args:
        credentials: Optional HTTP Bearer token credentials
        db: Async database session

    Returns:
        Current authenticated User object or None
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


def get_current_user_sync(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token (synchronous version)

    Args:
        credentials: HTTP Bearer token credentials
        db: Database session

    Returns:
        Current authenticated User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Verify and decode token
    payload = AuthService.verify_token(token)

    # Extract user ID from token
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token type
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


async def verify_refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to verify a refresh token

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Decoded refresh token payload

    Raises:
        HTTPException: If token is invalid or not a refresh token
    """
    token = credentials.credentials
    payload = AuthService.verify_token(token)

    # Verify token type
    token_type = payload.get("type")
    if token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Refresh token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
