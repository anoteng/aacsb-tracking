from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import httpx

from database import get_db
from services.auth import AuthService
from services.email import EmailService
from dependencies import get_current_user
from models import User
from config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


class MagicLinkRequest(BaseModel):
    email: EmailStr


class PasswordLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SetPasswordRequest(BaseModel):
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    firstname: str
    lastname: str
    roles: list[str]
    has_password: bool = False
    has_google: bool = False

    class Config:
        from_attributes = True


@router.post("/magic-link")
async def request_magic_link(
    request: MagicLinkRequest,
    db: Session = Depends(get_db),
):
    """Request a magic link to be sent to the user's email."""
    auth_service = AuthService(db)
    user = auth_service.get_user_by_email(request.email)

    if not user:
        # Don't reveal if user exists or not
        return {"message": "If an account exists, a login link has been sent."}

    if not user.active:
        return {"message": "If an account exists, a login link has been sent."}

    token = auth_service.create_magic_link_token(
        user, expires_minutes=settings.magic_link_expire_minutes
    )

    try:
        await EmailService.send_magic_link(
            to=user.email,
            token=token,
            name=user.firstname,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}",
        )

    return {"message": "If an account exists, a login link has been sent."}


@router.get("/verify")
async def verify_magic_link(
    token: str,
    response: Response,
    req: Request,
    db: Session = Depends(get_db),
):
    """Verify a magic link token and create a session."""
    auth_service = AuthService(db)
    user = auth_service.verify_magic_link_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired link",
        )

    session_token = auth_service.create_session(
        user,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    # Redirect to app with session cookie
    redirect = RedirectResponse(url=f"{settings.app_url}/aol", status_code=302)
    redirect.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 1 week
    )
    return redirect


@router.post("/login")
async def login_with_password(
    request: PasswordLoginRequest,
    response: Response,
    req: Request,
    db: Session = Depends(get_db),
):
    """Login with email and password."""
    auth_service = AuthService(db)
    user = auth_service.get_user_by_email(request.email)

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not auth_service.verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    session_token = auth_service.create_session(
        user,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return {
        "token": session_token,
        "user": UserResponse(
            id=user.uuid,
            email=user.email,
            firstname=user.firstname,
            lastname=user.lastname,
            roles=auth_service.get_user_roles(user),
        ),
    }


@router.post("/set-password")
async def set_password(
    request: SetPasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or update password for the current user."""
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    auth_service = AuthService(db)
    auth_service.set_user_password(user, request.password)
    return {"message": "Password set successfully"}


@router.get("/google/enabled")
async def google_enabled():
    """Check if Google OAuth is configured (public endpoint)."""
    return {"enabled": bool(settings.google_client_id)}


@router.get("/google")
async def google_login():
    """Initiate Google OAuth flow."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login is not configured",
        )

    redirect_uri = f"{settings.app_url}/api/auth/google/callback"
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login is not configured",
        )

    redirect_uri = f"{settings.app_url}/api/auth/google/callback"

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token",
            )

        tokens = token_response.json()

        # Get user info
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info",
            )

        google_user = userinfo_response.json()

    auth_service = AuthService(db)

    # Try to find user by Google ID first
    user = auth_service.get_user_by_google_id(google_user["id"])

    # If not found by Google ID, try by email
    if not user:
        user = auth_service.get_user_by_email(google_user["email"])
        if user:
            # Link Google account to existing user
            auth_service.link_google_account(user, google_user["id"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No account found for this email. Please contact administrator.",
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    session_token = auth_service.create_session(
        user,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    redirect = RedirectResponse(url=f"{settings.app_url}/aol", status_code=302)
    redirect.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return redirect


@router.get("/google/status")
async def google_status(
    user: User = Depends(get_current_user),
):
    """Check Google OAuth status for current user."""
    return {
        "configured": bool(settings.google_client_id),
        "linked": user.google_id is not None,
    }


@router.get("/google/link")
async def google_link_start(
    user: User = Depends(get_current_user),
):
    """Start Google account linking for logged-in user."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login is not configured",
        )

    redirect_uri = f"{settings.app_url}/api/auth/google/link/callback"
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)


@router.get("/google/link/callback")
async def google_link_callback(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback for account linking."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login is not configured",
        )

    redirect_uri = f"{settings.app_url}/api/auth/google/link/callback"

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            return RedirectResponse(
                url=f"{settings.app_url}/aol/settings?error=google_link_failed",
                status_code=302,
            )

        tokens = token_response.json()

        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        if userinfo_response.status_code != 200:
            return RedirectResponse(
                url=f"{settings.app_url}/aol/settings?error=google_link_failed",
                status_code=302,
            )

        google_user = userinfo_response.json()

    auth_service = AuthService(db)

    # Check if this Google account is already linked to another user
    existing = auth_service.get_user_by_google_id(google_user["id"])
    if existing and existing.uuid != user.uuid:
        return RedirectResponse(
            url=f"{settings.app_url}/aol/settings?error=google_already_linked",
            status_code=302,
        )

    # Link the account
    auth_service.link_google_account(user, google_user["id"])

    return RedirectResponse(url=f"{settings.app_url}/aol/settings?success=google_linked", status_code=302)


@router.post("/google/unlink")
async def google_unlink(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlink Google account from current user."""
    if not user.google_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account linked",
        )

    # Make sure user has another way to log in
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unlink Google account without a password set. Set a password first.",
        )

    user.google_id = None
    db.commit()
    return {"message": "Google account unlinked"}


@router.get("/me")
async def get_current_user_info(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user information."""
    auth_service = AuthService(db)
    return UserResponse(
        id=user.uuid,
        email=user.email,
        firstname=user.firstname,
        lastname=user.lastname,
        roles=auth_service.get_user_roles(user),
        has_password=user.password_hash is not None,
        has_google=user.google_id is not None,
    )


@router.post("/logout")
async def logout(
    response: Response,
    req: Request,
    db: Session = Depends(get_db),
):
    """Logout and invalidate session."""
    token = req.cookies.get("session_token")
    if token:
        auth_service = AuthService(db)
        auth_service.invalidate_session(token)

    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}
