"""
Authentication API Endpoints

Provides endpoints for user authentication, token management, and password operations.

Endpoints:
- POST /auth/login - User login with email and password
- POST /auth/refresh - Refresh access token using refresh token
- POST /auth/logout - Logout (client-side token deletion)
- POST /auth/register - Register new user account
- POST /auth/change-password - Change user password
- GET /auth/me - Get current user information
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from backend.security.auth_service import (
    AuthService,
    get_current_user,
    verify_refresh_token
)
from backend.models.user import User
from backend.db.base import get_async_db


router = APIRouter(tags=["authentication"])


# Request/Response Models
class LoginRequest(BaseModel):
    """Login request with email and password"""
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    """Login response with access and refresh tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: Optional[str] = None
    workspace_id: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    # Token comes from Authorization header, no body needed
    pass


class RefreshTokenResponse(BaseModel):
    """Refresh token response with new access token"""
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=255)
    workspace_id: UUID

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum security requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class RegisterResponse(BaseModel):
    """User registration response"""
    user_id: str
    email: str
    full_name: Optional[str] = None
    workspace_id: str
    message: str = "User registered successfully"


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum security requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserInfoResponse(BaseModel):
    """Current user information response"""
    id: str
    email: str
    full_name: Optional[str] = None
    workspace_id: str
    is_active: bool
    created_at: str


# Endpoints
@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Authenticate user and return access and refresh tokens

    Args:
        request: Login credentials (email and password)
        db: Database session

    Returns:
        JWT access token, refresh token, and user information

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Authenticate user
    user = await AuthService.authenticate_user(db, request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = AuthService.create_access_token(data={"sub": str(user.id)})
    refresh_token = AuthService.create_refresh_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        workspace_id=str(user.workspace_id)
    )


@router.post("/auth/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    payload: dict = Depends(verify_refresh_token)
):
    """
    Refresh access token using a valid refresh token

    Args:
        payload: Decoded refresh token payload

    Returns:
        New JWT access token

    Raises:
        HTTPException: 401 if refresh token is invalid
    """
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new access token
    access_token = AuthService.create_access_token(data={"sub": user_id})

    return RefreshTokenResponse(access_token=access_token)


@router.post("/auth/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Logout current user

    Note: JWT tokens are stateless, so logout is handled client-side by
    discarding the tokens. This endpoint exists for consistency and could
    be extended to implement token blacklisting in the future.

    Args:
        current_user: Current authenticated user

    Returns:
        Success message
    """
    return {
        "message": "Successfully logged out",
        "user_id": str(current_user.id)
    }


@router.post("/auth/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Register a new user account

    Args:
        request: Registration information
        db: Database session

    Returns:
        Created user information

    Raises:
        HTTPException: 400 if email already exists or workspace not found
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Verify workspace exists
    from backend.models.workspace import Workspace
    result = await db.execute(select(Workspace).where(Workspace.id == request.workspace_id))
    workspace = result.scalars().first()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    # Hash password
    password_hash = AuthService.hash_password(request.password)

    # Create new user
    new_user = User(
        email=request.email,
        password_hash=password_hash,
        full_name=request.full_name,
        workspace_id=request.workspace_id,
        is_active=True
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return RegisterResponse(
        user_id=str(new_user.id),
        email=new_user.email,
        full_name=new_user.full_name,
        workspace_id=str(new_user.workspace_id)
    )


@router.post("/auth/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Change current user's password

    Args:
        request: Current and new password
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: 400 if current password is incorrect
    """
    # Verify current password
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a password set"
        )

    if not AuthService.verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Hash and update new password
    current_user.password_hash = AuthService.hash_password(request.new_password)

    await db.commit()

    return {
        "message": "Password changed successfully",
        "user_id": str(current_user.id)
    }


@router.get("/auth/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information

    Args:
        current_user: Current authenticated user

    Returns:
        User information
    """
    return UserInfoResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        workspace_id=str(current_user.workspace_id),
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat()
    )
