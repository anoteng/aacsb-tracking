from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from services.auth import AuthService
from models import User

security = HTTPBearer(auto_error=False)


def _get_token_from_request(request: Request, credentials: HTTPAuthorizationCredentials = None) -> str | None:
    """Extract token from Authorization header or cookie."""
    if credentials:
        return credentials.credentials
    return request.cookies.get("session_token")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current effective user from session token.
    If impersonating, returns the impersonated user.
    """
    token = _get_token_from_request(request, credentials)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    effective_user, real_user = auth_service.get_effective_user(token)

    if not effective_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not effective_user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Store impersonation info in request state for access by endpoints
    request.state.real_user = real_user
    request.state.is_impersonating = (effective_user.uuid != real_user.uuid)

    return effective_user


async def get_real_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the real authenticated user (not impersonated).
    Use this for sensitive operations that should always check the real admin.
    """
    token = _get_token_from_request(request, credentials)

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
    """
    Dependency factory that requires user to have one of the specified roles.
    When impersonating, checks the REAL user's roles (admin keeps their permissions).
    """

    async def role_checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        auth_service = AuthService(db)

        # Use real user for permission checks (important when impersonating)
        real_user = getattr(request.state, 'real_user', user)
        user_roles = auth_service.get_user_roles(real_user)

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
