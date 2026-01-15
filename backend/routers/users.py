from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from services.auth import AuthService
from dependencies import get_current_user, require_role
from models import User, Role, UserRole

router = APIRouter(prefix="/users", tags=["Users"])


class UserCreate(BaseModel):
    email: EmailStr
    firstname: str
    lastname: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    firstname: str | None = None
    lastname: str | None = None
    active: bool | None = None


class UserResponse(BaseModel):
    id: int
    email: str | None
    firstname: str
    lastname: str
    active: bool
    roles: list[str]

    class Config:
        from_attributes = True


class RoleAssignment(BaseModel):
    role_name: str


@router.get("", response_model=list[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin", "admin_staff")),
):
    """List all users. Requires admin role."""
    auth_service = AuthService(db)
    users = db.query(User).order_by(User.lastname, User.firstname).all()
    return [
        UserResponse(
            id=u.uuid,
            email=u.email,
            firstname=u.firstname,
            lastname=u.lastname,
            active=u.active,
            roles=auth_service.get_user_roles(u),
        )
        for u in users
    ]


@router.post("", response_model=UserResponse)
async def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Create a new user. Requires system admin role."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=request.email,
        firstname=request.firstname,
        lastname=request.lastname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.uuid,
        email=user.email,
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        roles=[],
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "admin_staff")),
):
    """Get a specific user. Requires admin role."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    auth_service = AuthService(db)
    return UserResponse(
        id=user.uuid,
        email=user.email,
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        roles=auth_service.get_user_roles(user),
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Update a user. Requires system admin role."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if request.email is not None:
        existing = db.query(User).filter(User.email == request.email, User.uuid != user_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        user.email = request.email

    if request.firstname is not None:
        user.firstname = request.firstname
    if request.lastname is not None:
        user.lastname = request.lastname
    if request.active is not None:
        user.active = request.active

    db.commit()
    db.refresh(user)

    auth_service = AuthService(db)
    return UserResponse(
        id=user.uuid,
        email=user.email,
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        roles=auth_service.get_user_roles(user),
    )


@router.post("/{user_id}/roles")
async def assign_role(
    user_id: int,
    request: RoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Assign a role to a user. Requires system admin role."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    auth_service = AuthService(db)
    try:
        auth_service.assign_role(user, request.role_name, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": f"Role '{request.role_name}' assigned to user"}


@router.delete("/{user_id}/roles/{role_name}")
async def remove_role(
    user_id: int,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Remove a role from a user. Requires system admin role."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    role = db.query(Role).filter(Role.role_name == role_name).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    db.query(UserRole).filter(
        UserRole.uuid == user_id,
        UserRole.role_id == role.role_id,
    ).delete()
    db.commit()

    return {"message": f"Role '{role_name}' removed from user"}


@router.get("/roles/available", response_model=list[dict])
async def list_roles(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """List all available roles. Requires system admin role."""
    roles = db.query(Role).all()
    return [
        {
            "id": r.role_id,
            "name": r.role_name,
            "description": r.role_desc,
            "is_root": r.root,
        }
        for r in roles
    ]
