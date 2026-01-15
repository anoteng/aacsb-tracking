from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from database import get_db
from dependencies import require_role
from models import User, Role, UserRole, UserProgrammeRole, StudyProgramme

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================
# Pydantic Models
# ============================================

class UserCreate(BaseModel):
    email: EmailStr
    firstname: str
    lastname: str
    active: bool = True


class UserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[EmailStr] = None
    active: Optional[bool] = None
    researcher_id: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    firstname: str
    lastname: str
    active: bool
    has_password: bool
    has_google: bool
    researcher_id: Optional[str] = None
    roles: list[dict]
    programme_roles: list[dict]

    class Config:
        from_attributes = True


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_root: bool

    class Config:
        from_attributes = True


class RoleAssignment(BaseModel):
    role_id: int


class ProgrammeRoleAssignment(BaseModel):
    programme_id: int
    role_id: int


# ============================================
# Users
# ============================================

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all users. System admin only."""
    users = (
        db.query(User)
        .options(
            joinedload(User.roles).joinedload(UserRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.programme),
        )
        .order_by(User.lastname, User.firstname)
        .all()
    )

    return [
        UserResponse(
            id=u.uuid,
            email=u.email or "",
            firstname=u.firstname,
            lastname=u.lastname,
            active=u.active,
            has_password=u.password_hash is not None,
            has_google=u.google_id is not None,
            researcher_id=u.researcher_id,
            roles=[
                {"id": ur.role.role_id, "name": ur.role.role_name}
                for ur in u.roles
            ],
            programme_roles=[
                {
                    "id": pr.id,
                    "programme_id": pr.programme_id,
                    "programme_code": pr.programme.programme_code,
                    "role_id": pr.role_id,
                    "role_name": pr.role.role_name,
                }
                for pr in u.programme_roles
            ],
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Create a new user. System admin only."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )

    user = User(
        email=request.email,
        firstname=request.firstname,
        lastname=request.lastname,
        active=request.active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.uuid,
        email=user.email or "",
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        has_password=False,
        has_google=False,
        researcher_id=user.researcher_id,
        roles=[],
        programme_roles=[],
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Get a specific user. System admin only."""
    user = (
        db.query(User)
        .options(
            joinedload(User.roles).joinedload(UserRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.programme),
        )
        .filter(User.uuid == user_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user.uuid,
        email=user.email or "",
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        has_password=user.password_hash is not None,
        has_google=user.google_id is not None,
        roles=[
            {"id": ur.role.role_id, "name": ur.role.role_name}
            for ur in user.roles
        ],
        programme_roles=[
            {
                "id": pr.id,
                "programme_id": pr.programme_id,
                "programme_code": pr.programme.programme_code,
                "role_id": pr.role_id,
                "role_name": pr.role.role_name,
            }
            for pr in user.programme_roles
        ],
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Update a user. System admin only."""
    user = (
        db.query(User)
        .options(
            joinedload(User.roles).joinedload(UserRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.programme),
        )
        .filter(User.uuid == user_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.firstname is not None:
        user.firstname = request.firstname
    if request.lastname is not None:
        user.lastname = request.lastname
    if request.email is not None:
        user.email = request.email
    if request.active is not None:
        user.active = request.active
    if request.researcher_id is not None:
        user.researcher_id = request.researcher_id

    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.uuid,
        email=user.email or "",
        firstname=user.firstname,
        lastname=user.lastname,
        active=user.active,
        has_password=user.password_hash is not None,
        has_google=user.google_id is not None,
        researcher_id=user.researcher_id,
        roles=[
            {"id": ur.role.role_id, "name": ur.role.role_name}
            for ur in user.roles
        ],
        programme_roles=[
            {
                "id": pr.id,
                "programme_id": pr.programme_id,
                "programme_code": pr.programme.programme_code,
                "role_id": pr.role_id,
                "role_name": pr.role.role_name,
            }
            for pr in user.programme_roles
        ],
    )


# ============================================
# Roles
# ============================================

@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all roles. System admin only."""
    roles = db.query(Role).order_by(Role.role_name).all()

    return [
        RoleResponse(
            id=r.role_id,
            name=r.role_name,
            description=r.role_desc,
            is_root=r.root or False,
        )
        for r in roles
    ]


# ============================================
# User Role Assignments (Global Roles)
# ============================================

@router.post("/users/{user_id}/roles")
async def assign_role(
    user_id: int,
    request: RoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Assign a global role to a user. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = db.query(Role).filter(Role.role_id == request.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if already assigned
    existing = (
        db.query(UserRole)
        .filter(UserRole.uuid == user_id, UserRole.role_id == request.role_id)
        .first()
    )
    if existing:
        return {"message": "Role already assigned"}

    user_role = UserRole(uuid=user_id, role_id=request.role_id)
    db.add(user_role)
    db.commit()

    return {"message": f"Role '{role.role_name}' assigned to user"}


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Remove a global role from a user. System admin only."""
    # Prevent removing own system_admin role
    if user_id == current_user.uuid:
        role = db.query(Role).filter(Role.role_id == role_id).first()
        if role and role.role_name == "system_admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own system_admin role",
            )

    deleted = (
        db.query(UserRole)
        .filter(UserRole.uuid == user_id, UserRole.role_id == role_id)
        .delete()
    )
    db.commit()

    if deleted:
        return {"message": "Role removed"}
    return {"message": "Role was not assigned"}


# ============================================
# User Programme Role Assignments
# ============================================

@router.post("/users/{user_id}/programme-roles")
async def assign_programme_role(
    user_id: int,
    request: ProgrammeRoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Assign a programme-specific role to a user. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    programme = db.query(StudyProgramme).filter(StudyProgramme.id == request.programme_id).first()
    if not programme:
        raise HTTPException(status_code=404, detail="Programme not found")

    role = db.query(Role).filter(Role.role_id == request.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if already assigned
    existing = (
        db.query(UserProgrammeRole)
        .filter(
            UserProgrammeRole.user_id == user_id,
            UserProgrammeRole.programme_id == request.programme_id,
            UserProgrammeRole.role_id == request.role_id,
        )
        .first()
    )
    if existing:
        return {"message": "Programme role already assigned"}

    prog_role = UserProgrammeRole(
        user_id=user_id,
        programme_id=request.programme_id,
        role_id=request.role_id,
        assigned_by=current_user.uuid,
    )
    db.add(prog_role)
    db.commit()

    return {"message": f"Role '{role.role_name}' assigned for programme '{programme.programme_code}'"}


@router.delete("/users/{user_id}/programme-roles/{programme_role_id}")
async def remove_programme_role(
    user_id: int,
    programme_role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Remove a programme-specific role from a user. System admin only."""
    deleted = (
        db.query(UserProgrammeRole)
        .filter(
            UserProgrammeRole.id == programme_role_id,
            UserProgrammeRole.user_id == user_id,
        )
        .delete()
    )
    db.commit()

    if deleted:
        return {"message": "Programme role removed"}
    return {"message": "Programme role was not assigned"}


# ============================================
# Programmes (for dropdowns)
# ============================================

@router.get("/programmes")
async def list_programmes_for_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all programmes for admin dropdowns. System admin only."""
    programmes = db.query(StudyProgramme).order_by(StudyProgramme.programme_code).all()

    return [
        {
            "id": p.id,
            "programme_code": p.programme_code,
            "name_no": p.name_no,
            "name_eng": p.name_eng,
        }
        for p in programmes
    ]
