from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from decimal import Decimal

from database import get_db
from dependencies import require_role
from models import (
    User, Role, UserRole, UserProgrammeRole, StudyProgramme, FacultyCategory,
    Degree, Discipline, ProfessionalResponsibility,
    UserDiscipline, UserResponsibility, UserTeachingProductivity,
)
from services.nva import nva_service

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
    faculty_category: Optional[str] = None  # SA, PA, SP, IP, Other
    is_participating: Optional[bool] = None
    participating_note: Optional[str] = None
    highest_degree_id: Optional[int] = None
    degree_year: Optional[int] = None


class DisciplineAllocation(BaseModel):
    discipline_id: int
    percentage: float


class TeachingProductivityEntry(BaseModel):
    academic_year: str  # e.g., "2024-2025"
    credits: float


class UserResponse(BaseModel):
    id: int
    email: str
    firstname: str
    lastname: str
    active: bool
    has_password: bool
    has_google: bool
    researcher_id: Optional[str] = None
    faculty_category: Optional[str] = None
    is_participating: bool = True
    participating_note: Optional[str] = None
    highest_degree: Optional[dict] = None
    degree_year: Optional[int] = None
    disciplines: list[dict] = []
    responsibilities: list[dict] = []
    teaching_productivity: list[dict] = []
    roles: list[dict]
    programme_roles: list[dict]

    class Config:
        from_attributes = True


class DegreeResponse(BaseModel):
    id: int
    name: str

class DisciplineResponse(BaseModel):
    id: int
    name: str
    shorthand: str

class ResponsibilityResponse(BaseModel):
    id: int
    name: str
    shorthand: str


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

def serialize_user(u: User) -> UserResponse:
    """Serialize a user with all faculty qualification fields."""
    return UserResponse(
        id=u.uuid,
        email=u.email or "",
        firstname=u.firstname,
        lastname=u.lastname,
        active=u.active,
        has_password=u.password_hash is not None,
        has_google=u.google_id is not None,
        researcher_id=u.researcher_id,
        faculty_category=u.faculty_category.value if u.faculty_category else None,
        is_participating=u.is_participating if u.is_participating is not None else True,
        participating_note=u.participating_note,
        highest_degree={"id": u.highest_degree.id, "name": u.highest_degree.name} if u.highest_degree else None,
        degree_year=u.degree_year,
        disciplines=[
            {"id": ud.discipline.id, "name": ud.discipline.name, "shorthand": ud.discipline.shorthand, "percentage": float(ud.percentage)}
            for ud in u.disciplines
        ],
        responsibilities=[
            {"id": ur.responsibility.id, "name": ur.responsibility.name, "shorthand": ur.responsibility.shorthand}
            for ur in u.responsibilities
        ],
        teaching_productivity=[
            {"id": tp.id, "academic_year": tp.academic_year, "credits": float(tp.credits)}
            for tp in u.teaching_productivity
        ],
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
            joinedload(User.highest_degree),
            joinedload(User.disciplines).joinedload(UserDiscipline.discipline),
            joinedload(User.responsibilities).joinedload(UserResponsibility.responsibility),
            joinedload(User.teaching_productivity),
        )
        .order_by(User.lastname, User.firstname)
        .all()
    )

    return [serialize_user(u) for u in users]


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


def get_user_with_relations(db: Session, user_id: int) -> User:
    """Get a user with all relations loaded."""
    return (
        db.query(User)
        .options(
            joinedload(User.roles).joinedload(UserRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.role),
            joinedload(User.programme_roles).joinedload(UserProgrammeRole.programme),
            joinedload(User.highest_degree),
            joinedload(User.disciplines).joinedload(UserDiscipline.discipline),
            joinedload(User.responsibilities).joinedload(UserResponsibility.responsibility),
            joinedload(User.teaching_productivity),
        )
        .filter(User.uuid == user_id)
        .first()
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Get a specific user. System admin only."""
    user = get_user_with_relations(db, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return serialize_user(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Update a user. System admin only."""
    user = get_user_with_relations(db, user_id)

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
        user.researcher_id = request.researcher_id if request.researcher_id != "" else None

    # Faculty qualification fields
    if request.faculty_category is not None:
        if request.faculty_category == "":
            user.faculty_category = None
        else:
            user.faculty_category = FacultyCategory(request.faculty_category)
    if request.is_participating is not None:
        user.is_participating = request.is_participating
    if request.participating_note is not None:
        user.participating_note = request.participating_note if request.participating_note != "" else None
    if request.highest_degree_id is not None:
        if request.highest_degree_id == 0:
            user.highest_degree_id = None
        else:
            user.highest_degree_id = request.highest_degree_id
    if request.degree_year is not None:
        if request.degree_year == 0:
            user.degree_year = None
        else:
            user.degree_year = request.degree_year

    db.commit()

    # Reload with all relations
    user = get_user_with_relations(db, user_id)
    return serialize_user(user)


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


# ============================================
# Degrees
# ============================================

@router.get("/degrees", response_model=list[DegreeResponse])
async def list_degrees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all degrees. System admin only."""
    degrees = db.query(Degree).order_by(Degree.name).all()
    return [DegreeResponse(id=d.id, name=d.name) for d in degrees]


@router.post("/degrees", response_model=DegreeResponse)
async def create_degree(
    name: str = Query(..., description="Degree name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Create a new degree. System admin only."""
    existing = db.query(Degree).filter(Degree.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Degree already exists")

    degree = Degree(name=name)
    db.add(degree)
    db.commit()
    db.refresh(degree)
    return DegreeResponse(id=degree.id, name=degree.name)


@router.delete("/degrees/{degree_id}")
async def delete_degree(
    degree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Delete a degree. System admin only."""
    deleted = db.query(Degree).filter(Degree.id == degree_id).delete()
    db.commit()
    if deleted:
        return {"message": "Degree deleted"}
    raise HTTPException(status_code=404, detail="Degree not found")


# ============================================
# Disciplines
# ============================================

@router.get("/disciplines", response_model=list[DisciplineResponse])
async def list_disciplines(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all disciplines. System admin only."""
    disciplines = db.query(Discipline).order_by(Discipline.shorthand).all()
    return [DisciplineResponse(id=d.id, name=d.name, shorthand=d.shorthand) for d in disciplines]


@router.post("/disciplines", response_model=DisciplineResponse)
async def create_discipline(
    name: str = Query(..., description="Discipline name"),
    shorthand: str = Query(..., description="Short code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Create a new discipline. System admin only."""
    existing = db.query(Discipline).filter(Discipline.shorthand == shorthand).first()
    if existing:
        raise HTTPException(status_code=400, detail="Discipline shorthand already exists")

    discipline = Discipline(name=name, shorthand=shorthand)
    db.add(discipline)
    db.commit()
    db.refresh(discipline)
    return DisciplineResponse(id=discipline.id, name=discipline.name, shorthand=discipline.shorthand)


@router.delete("/disciplines/{discipline_id}")
async def delete_discipline(
    discipline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Delete a discipline. System admin only."""
    deleted = db.query(Discipline).filter(Discipline.id == discipline_id).delete()
    db.commit()
    if deleted:
        return {"message": "Discipline deleted"}
    raise HTTPException(status_code=404, detail="Discipline not found")


# ============================================
# Professional Responsibilities
# ============================================

@router.get("/responsibilities", response_model=list[ResponsibilityResponse])
async def list_responsibilities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """List all professional responsibilities. System admin only."""
    responsibilities = db.query(ProfessionalResponsibility).order_by(ProfessionalResponsibility.shorthand).all()
    return [ResponsibilityResponse(id=r.id, name=r.name, shorthand=r.shorthand) for r in responsibilities]


@router.post("/responsibilities", response_model=ResponsibilityResponse)
async def create_responsibility(
    name: str = Query(..., description="Responsibility name"),
    shorthand: str = Query(..., description="Short code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Create a new professional responsibility. System admin only."""
    existing = db.query(ProfessionalResponsibility).filter(ProfessionalResponsibility.shorthand == shorthand).first()
    if existing:
        raise HTTPException(status_code=400, detail="Responsibility shorthand already exists")

    responsibility = ProfessionalResponsibility(name=name, shorthand=shorthand)
    db.add(responsibility)
    db.commit()
    db.refresh(responsibility)
    return ResponsibilityResponse(id=responsibility.id, name=responsibility.name, shorthand=responsibility.shorthand)


@router.delete("/responsibilities/{responsibility_id}")
async def delete_responsibility(
    responsibility_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Delete a professional responsibility. System admin only."""
    deleted = db.query(ProfessionalResponsibility).filter(ProfessionalResponsibility.id == responsibility_id).delete()
    db.commit()
    if deleted:
        return {"message": "Responsibility deleted"}
    raise HTTPException(status_code=404, detail="Responsibility not found")


# ============================================
# User Discipline Allocations
# ============================================

@router.put("/users/{user_id}/disciplines")
async def set_user_disciplines(
    user_id: int,
    allocations: list[DisciplineAllocation],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Set discipline allocations for a user. Replaces existing allocations. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate percentages sum to 100 (or 0 if empty)
    total = sum(a.percentage for a in allocations)
    if allocations and abs(total - 100) > 0.01:
        raise HTTPException(status_code=400, detail=f"Percentages must sum to 100 (got {total})")

    # Clear existing allocations
    db.query(UserDiscipline).filter(UserDiscipline.user_id == user_id).delete()

    # Add new allocations
    for alloc in allocations:
        discipline = db.query(Discipline).filter(Discipline.id == alloc.discipline_id).first()
        if not discipline:
            raise HTTPException(status_code=404, detail=f"Discipline {alloc.discipline_id} not found")

        user_disc = UserDiscipline(
            user_id=user_id,
            discipline_id=alloc.discipline_id,
            percentage=Decimal(str(alloc.percentage)),
        )
        db.add(user_disc)

    db.commit()
    return {"message": "Discipline allocations updated"}


# ============================================
# User Responsibilities
# ============================================

@router.put("/users/{user_id}/responsibilities")
async def set_user_responsibilities(
    user_id: int,
    responsibility_ids: list[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Set responsibilities for a user. Replaces existing assignments. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Clear existing assignments
    db.query(UserResponsibility).filter(UserResponsibility.user_id == user_id).delete()

    # Add new assignments
    for resp_id in responsibility_ids:
        responsibility = db.query(ProfessionalResponsibility).filter(ProfessionalResponsibility.id == resp_id).first()
        if not responsibility:
            raise HTTPException(status_code=404, detail=f"Responsibility {resp_id} not found")

        user_resp = UserResponsibility(user_id=user_id, responsibility_id=resp_id)
        db.add(user_resp)

    db.commit()
    return {"message": "Responsibilities updated"}


# ============================================
# User Teaching Productivity
# ============================================

@router.put("/users/{user_id}/teaching-productivity")
async def set_user_teaching_productivity(
    user_id: int,
    entries: list[TeachingProductivityEntry],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Set teaching productivity for a user. Replaces existing entries. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Clear existing entries
    db.query(UserTeachingProductivity).filter(UserTeachingProductivity.user_id == user_id).delete()

    # Add new entries
    for entry in entries:
        tp = UserTeachingProductivity(
            user_id=user_id,
            academic_year=entry.academic_year,
            credits=Decimal(str(entry.credits)),
        )
        db.add(tp)

    db.commit()
    return {"message": "Teaching productivity updated"}


@router.post("/users/{user_id}/teaching-productivity")
async def add_teaching_productivity(
    user_id: int,
    entry: TeachingProductivityEntry,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Add or update a teaching productivity entry for a user. System admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if entry for this year already exists
    existing = (
        db.query(UserTeachingProductivity)
        .filter(
            UserTeachingProductivity.user_id == user_id,
            UserTeachingProductivity.academic_year == entry.academic_year,
        )
        .first()
    )

    if existing:
        existing.credits = Decimal(str(entry.credits))
    else:
        tp = UserTeachingProductivity(
            user_id=user_id,
            academic_year=entry.academic_year,
            credits=Decimal(str(entry.credits)),
        )
        db.add(tp)

    db.commit()
    return {"message": f"Teaching productivity for {entry.academic_year} updated"}


@router.delete("/users/{user_id}/teaching-productivity/{entry_id}")
async def delete_teaching_productivity(
    user_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin")),
):
    """Delete a teaching productivity entry. System admin only."""
    deleted = (
        db.query(UserTeachingProductivity)
        .filter(
            UserTeachingProductivity.id == entry_id,
            UserTeachingProductivity.user_id == user_id,
        )
        .delete()
    )
    db.commit()
    if deleted:
        return {"message": "Teaching productivity entry deleted"}
    raise HTTPException(status_code=404, detail="Entry not found")


# ============================================
# NVA/Cristin Person Search
# ============================================

@router.get("/nva/search-persons")
async def search_nva_persons(
    name: str = Query(..., min_length=2, description="Name to search for"),
    current_user: User = Depends(require_role("system_admin")),
):
    """Search for researchers by name in Cristin. System admin only."""
    try:
        results = await nva_service.search_persons(name)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")
