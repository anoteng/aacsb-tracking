from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from services.auth import AuthService
from models import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Get the current authenticated user from session token."""
    token = None

    # Try to get token from Authorization header
    if credentials:
        token = credentials.credentials
    # Fallback to cookie
    else:
        token = request.cookies.get("session_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    user = auth_service.verify_session(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, otherwise return None."""
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Dependency factory that requires user to have one of the specified roles."""

    async def role_checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        auth_service = AuthService(db)
        user_roles = auth_service.get_user_roles(user)

        # System admin always has access
        if "system_admin" in user_roles:
            return user

        # Check if user has any of the required roles
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(roles)}",
            )

        return user

    return role_checker


def require_system_admin():
    """Dependency that requires system admin role."""
    return require_role("system_admin")
