from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Literal
from datetime import datetime as dt

from database import get_db
from dependencies import get_current_user, require_role
from services.auth import AuthService
from models import (
    User,
    UserProgrammeRole,
    Role,
    AcadYear,
    StudyProgramme,
    Course,
    ProgrammeCourse,
    CourseCoordinator,
    LearningGoal,
    GoalCategory,
    GoalCourseMatrix,
    GoalStaffAssignment,
    Rubric,
    RubricTrait,
    Assessment,
    AssessmentResult,
    LearningMethod,
    AssessmentMethod,
    Technology,
    ProgrammeCourseMetadata,
    CourseLearningMethod,
    CourseAssessmentMethod,
    CourseTechnology,
)

router = APIRouter(prefix="/aol", tags=["AOL"])


# ============================================
# Pydantic Models
# ============================================

class ProgrammeResponse(BaseModel):
    id: int
    programme_code: str
    name_no: str
    name_eng: str | None
    goal_count: int = 0
    course_count: int = 0

    class Config:
        from_attributes = True


class CourseResponse(BaseModel):
    id: int
    course_code: str
    course_version: str
    name_no: str | None
    name_eng: str | None
    ects: float
    prme_report: bool = False

    class Config:
        from_attributes = True


class GoalCategoryResponse(BaseModel):
    id: int
    name_no: str
    name_eng: str | None

    class Config:
        from_attributes = True


class LearningGoalCreate(BaseModel):
    goal_no: str | None = None
    goal_eng: str | None = None
    goal_category: int
    measure_direct: bool = False
    measure_indirect: bool = False
    target_percentage: float = 80.0


class LearningGoalUpdate(BaseModel):
    goal_no: str | None = None
    goal_eng: str | None = None
    goal_category: int | None = None
    measure_direct: bool | None = None
    measure_indirect: bool | None = None
    target_percentage: float | None = None
    revision_type: Literal["minor", "major"] = "minor"


class LearningGoalResponse(BaseModel):
    id: int
    goal_no: str | None
    goal_eng: str | None
    category: GoalCategoryResponse
    programme_id: int
    measure_direct: bool = False
    measure_indirect: bool = False
    target_percentage: float
    assigned_staff: list[dict] = []
    sort_order: int = 0
    archived: bool = False
    archived_at: dt | None = None
    superseded_by: int | None = None

    class Config:
        from_attributes = True


class GoalReorderItem(BaseModel):
    id: int
    sort_order: int


class MatrixEntryUpdate(BaseModel):
    learning_level: int = 0  # 0=None, 1=Introduced, 2=Developing, 3=Mastery
    is_assessed: bool = False


class CourseMetadataUpdate(BaseModel):
    learning_methods: list[str] = []  # List of method codes
    assessment_methods: list[str] = []  # List of method codes
    technologies: list[str] = []  # List of tech codes
    sdgs: list[int] = []  # List of SDG numbers (1-17)


class MatrixEntryResponse(BaseModel):
    goal_id: int
    course_id: int
    introduced: bool
    practiced: bool
    reinforced: bool

    class Config:
        from_attributes = True


class RubricCreate(BaseModel):
    name: str
    description: str | None = None
    rubric_type: Literal["holistic", "analytic"] = "analytic"
    measure_type: Literal["direct", "indirect"] = "direct"


class RubricUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    measure_type: Literal["direct", "indirect"] | None = None


class TraitCreate(BaseModel):
    name: str
    description: str | None = None
    sort_order: int = 0
    level_does_not_meet: str | None = None
    level_meets: str | None = None
    level_exceeds: str | None = None


class TraitUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None
    level_does_not_meet: str | None = None
    level_meets: str | None = None
    level_exceeds: str | None = None


class TraitResponse(BaseModel):
    id: int
    name: str
    description: str | None
    sort_order: int
    level_does_not_meet: str | None
    level_meets: str | None
    level_exceeds: str | None

    class Config:
        from_attributes = True


class RubricResponse(BaseModel):
    id: int
    goal_id: int
    name: str
    description: str | None
    rubric_type: str
    measure_type: str = "direct"
    active: bool
    traits: list[TraitResponse] = []

    class Config:
        from_attributes = True


class AssessmentCreate(BaseModel):
    rubric_id: int
    course_id: int
    academic_year_id: int
    semester_id: int | None = None
    assessment_date: str | None = None
    total_students: int = 0
    notes: str | None = None


class AssessmentResultCreate(BaseModel):
    trait_id: int
    count_does_not_meet: int = 0
    count_meets: int = 0
    count_exceeds: int = 0


class AssessmentResultResponse(BaseModel):
    trait_id: int
    trait_name: str
    count_does_not_meet: int
    count_meets: int
    count_exceeds: int
    meets_or_exceeds_pct: float

    class Config:
        from_attributes = True


class AssessmentResponse(BaseModel):
    id: int
    rubric_id: int
    course_id: int
    course_code: str
    academic_year_id: int
    semester_id: int | None
    assessment_date: str | None
    total_students: int
    notes: str | None
    results: list[AssessmentResultResponse] = []

    class Config:
        from_attributes = True


# ============================================
# Helper Functions
# ============================================

def is_course_coordinator(user: User, course_id: int, db: Session) -> bool:
    """Check if user is the active coordinator of a course."""
    from datetime import date
    today = date.today()
    cc = (
        db.query(CourseCoordinator)
        .filter(
            CourseCoordinator.course_id == course_id,
            CourseCoordinator.user_id == user.uuid,
        )
        .first()
    )
    if not cc:
        return False
    return (
        (cc.start_date is None or cc.start_date <= today)
        and (cc.end_date is None or cc.end_date >= today)
    )


def is_programme_admin(user: User, programme_id: int, db: Session) -> bool:
    """Check if user has admin_staff programme-level role for a specific programme."""
    return (
        db.query(UserProgrammeRole)
        .join(Role, Role.role_id == UserProgrammeRole.role_id)
        .filter(
            UserProgrammeRole.user_id == user.uuid,
            UserProgrammeRole.programme_id == programme_id,
            Role.role_name == "admin_staff",
        )
        .first() is not None
    )


def check_programme_access(request: Request, programme_id: int, db: Session, user: User) -> None:
    """Raise 403 if neither system_admin nor programme admin_staff for this programme.
    Always checks the real user (safe under impersonation)."""
    real_user = getattr(request.state, "real_user", user)
    auth_service = AuthService(db)
    if "system_admin" in auth_service.get_user_roles(real_user):
        return
    if not is_programme_admin(real_user, programme_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this programme")


def can_edit_goal(user: User, goal: LearningGoal, db: Session) -> bool:
    """Check if user can edit a specific goal's rubrics/traits."""
    auth_service = AuthService(db)
    roles = auth_service.get_user_roles(user)

    # System admin can do anything
    if "system_admin" in roles:
        return True

    # Programme leaders can edit
    if "programme_leader" in roles:
        return True

    # Staff can only edit assigned goals
    assignment = (
        db.query(GoalStaffAssignment)
        .filter(
            GoalStaffAssignment.goal_id == goal.id,
            GoalStaffAssignment.user_id == user.uuid,
        )
        .first()
    )
    return assignment is not None


# ============================================
# Programmes
# ============================================

@router.get("/programmes", response_model=list[ProgrammeResponse])
async def list_programmes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all study programmes with goal and course counts."""
    programmes = db.query(StudyProgramme).order_by(StudyProgramme.programme_code).all()

    result = []
    for prog in programmes:
        goal_count = db.query(LearningGoal).filter(LearningGoal.programme_id == prog.id).count()
        course_count = db.query(ProgrammeCourse).filter(ProgrammeCourse.programme_id == prog.id).count()
        result.append(
            ProgrammeResponse(
                id=prog.id,
                programme_code=prog.programme_code,
                name_no=prog.name_no,
                name_eng=prog.name_eng,
                goal_count=goal_count,
                course_count=course_count,
            )
        )
    return result


@router.get("/programmes/{programme_id}", response_model=ProgrammeResponse)
async def get_programme(
    programme_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific programme."""
    prog = db.query(StudyProgramme).filter(StudyProgramme.id == programme_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")

    goal_count = db.query(LearningGoal).filter(LearningGoal.programme_id == prog.id).count()
    course_count = db.query(ProgrammeCourse).filter(ProgrammeCourse.programme_id == prog.id).count()

    return ProgrammeResponse(
        id=prog.id,
        programme_code=prog.programme_code,
        name_no=prog.name_no,
        name_eng=prog.name_eng,
        goal_count=goal_count,
        course_count=course_count,
    )


# ============================================
# Goal Categories
# ============================================

@router.get("/categories", response_model=list[GoalCategoryResponse])
async def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all goal categories."""
    categories = db.query(GoalCategory).filter(GoalCategory.enabled == True).all()
    return [
        GoalCategoryResponse(id=c.id, name_no=c.name_no, name_eng=c.name_eng)
        for c in categories
    ]


# ============================================
# Learning Goals
# ============================================

@router.get("/programmes/{programme_id}/goals", response_model=list[LearningGoalResponse])
async def list_goals(
    programme_id: int,
    req: Request,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List learning goals for a programme. include_archived requires programme admin."""
    if include_archived:
        real_user = getattr(req.state, "real_user", user)
        auth_service = AuthService(db)
        roles = auth_service.get_user_roles(real_user)
        if "system_admin" not in roles and "programme_leader" not in roles and not is_programme_admin(real_user, programme_id, db):
            raise HTTPException(status_code=403, detail="Not authorized to view archived goals")

    query = (
        db.query(LearningGoal)
        .options(joinedload(LearningGoal.category), joinedload(LearningGoal.staff_assignments))
        .filter(LearningGoal.programme_id == programme_id)
    )
    if not include_archived:
        query = query.filter(LearningGoal.archived == False)

    goals = query.order_by(LearningGoal.goal_category, LearningGoal.sort_order, LearningGoal.id).all()

    result = []
    for g in goals:
        assigned = [
            {"user_id": a.user_id, "name": f"{a.user.firstname} {a.user.lastname}"}
            for a in g.staff_assignments
        ]
        result.append(
            LearningGoalResponse(
                id=g.id,
                goal_no=g.goal_no,
                goal_eng=g.goal_eng,
                category=GoalCategoryResponse(
                    id=g.category.id, name_no=g.category.name_no, name_eng=g.category.name_eng
                ),
                programme_id=g.programme_id,
                measure_direct=g.measure_direct, measure_indirect=g.measure_indirect,
                target_percentage=float(g.target_percentage) if g.target_percentage else 80.0,
                assigned_staff=assigned,
                sort_order=g.sort_order,
                archived=g.archived,
                archived_at=g.archived_at,
                superseded_by=g.superseded_by,
            )
        )
    return result


@router.post("/programmes/{programme_id}/goals", response_model=LearningGoalResponse)
async def create_goal(
    programme_id: int,
    req: Request,
    request: LearningGoalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new learning goal. Admin or programme admin_staff only."""
    check_programme_access(req, programme_id, db, user)
    # Verify programme exists
    prog = db.query(StudyProgramme).filter(StudyProgramme.id == programme_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")

    # Verify category exists
    cat = db.query(GoalCategory).filter(GoalCategory.id == request.goal_category).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    max_order = db.query(func.max(LearningGoal.sort_order)).filter(
        LearningGoal.programme_id == programme_id
    ).scalar() or 0

    goal = LearningGoal(
        goal_no=request.goal_no,
        goal_eng=request.goal_eng,
        goal_category=request.goal_category,
        programme_id=programme_id,
        measure_direct=request.measure_direct, measure_indirect=request.measure_indirect,
        target_percentage=request.target_percentage,
        sort_order=max_order + 1,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)

    return LearningGoalResponse(
        id=goal.id,
        goal_no=goal.goal_no,
        goal_eng=goal.goal_eng,
        category=GoalCategoryResponse(id=cat.id, name_no=cat.name_no, name_eng=cat.name_eng),
        programme_id=goal.programme_id,
        measure_direct=goal.measure_direct, measure_indirect=goal.measure_indirect,
        target_percentage=float(goal.target_percentage) if goal.target_percentage else 80.0,
        assigned_staff=[],
        sort_order=goal.sort_order,
    )


@router.patch("/goals/{goal_id}", response_model=LearningGoalResponse)
async def update_goal(
    goal_id: int,
    req: Request,
    request: LearningGoalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a learning goal. Minor revision: in-place. Major revision: archives old, creates new."""
    goal = db.query(LearningGoal).options(
        joinedload(LearningGoal.category), joinedload(LearningGoal.staff_assignments)
    ).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    check_programme_access(req, goal.programme_id, db, user)

    if request.revision_type == "major":
        new_goal = LearningGoal(
            goal_no=request.goal_no if request.goal_no is not None else goal.goal_no,
            goal_eng=request.goal_eng if request.goal_eng is not None else goal.goal_eng,
            goal_category=request.goal_category if request.goal_category is not None else goal.goal_category,
            programme_id=goal.programme_id,
            measure_direct=request.measure_direct if request.measure_direct is not None else goal.measure_direct,
            measure_indirect=request.measure_indirect if request.measure_indirect is not None else goal.measure_indirect,
            target_percentage=request.target_percentage if request.target_percentage is not None else goal.target_percentage,
            sort_order=goal.sort_order,
        )
        db.add(new_goal)
        db.flush()  # get new_goal.id

        goal.archived = True
        goal.archived_at = dt.utcnow()
        goal.superseded_by = new_goal.id
        db.commit()
        db.refresh(new_goal)

        cat = db.query(GoalCategory).filter(GoalCategory.id == new_goal.goal_category).first()
        return LearningGoalResponse(
            id=new_goal.id,
            goal_no=new_goal.goal_no,
            goal_eng=new_goal.goal_eng,
            category=GoalCategoryResponse(id=cat.id, name_no=cat.name_no, name_eng=cat.name_eng),
            programme_id=new_goal.programme_id,
            measure_direct=new_goal.measure_direct, measure_indirect=new_goal.measure_indirect,
            target_percentage=float(new_goal.target_percentage) if new_goal.target_percentage else 80.0,
            assigned_staff=[],
            sort_order=new_goal.sort_order,
        )

    # Minor revision — update in place
    if request.goal_no is not None:
        goal.goal_no = request.goal_no
    if request.goal_eng is not None:
        goal.goal_eng = request.goal_eng
    if request.goal_category is not None:
        goal.goal_category = request.goal_category
    if request.measure_direct is not None:
        goal.measure_direct = request.measure_direct
    if request.measure_indirect is not None:
        goal.measure_indirect = request.measure_indirect
    if request.target_percentage is not None:
        goal.target_percentage = request.target_percentage

    db.commit()
    db.refresh(goal)

    return LearningGoalResponse(
        id=goal.id,
        goal_no=goal.goal_no,
        goal_eng=goal.goal_eng,
        category=GoalCategoryResponse(
            id=goal.category.id, name_no=goal.category.name_no, name_eng=goal.category.name_eng
        ),
        programme_id=goal.programme_id,
        measure_direct=goal.measure_direct, measure_indirect=goal.measure_indirect,
        target_percentage=float(goal.target_percentage) if goal.target_percentage else 80.0,
        assigned_staff=[
            {"user_id": a.user_id, "name": f"{a.user.firstname} {a.user.lastname}"}
            for a in goal.staff_assignments
        ],
        sort_order=goal.sort_order,
    )


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    req: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a learning goal. Admin or programme admin_staff only."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    check_programme_access(req, goal.programme_id, db, user)

    db.delete(goal)
    db.commit()
    return {"message": "Goal deleted"}


@router.post("/goals/{goal_id}/archive")
async def archive_goal(
    goal_id: int,
    req: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Archive a goal (retire without replacement). Programme admin only."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.archived:
        raise HTTPException(status_code=400, detail="Goal is already archived")
    check_programme_access(req, goal.programme_id, db, user)
    goal.archived = True
    goal.archived_at = dt.utcnow()
    db.commit()
    return {"message": "Goal archived"}


@router.post("/goals/{goal_id}/unarchive")
async def unarchive_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Restore an archived goal. System admin only."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if not goal.archived:
        raise HTTPException(status_code=400, detail="Goal is not archived")
    goal.archived = False
    goal.archived_at = None
    goal.superseded_by = None
    db.commit()
    return {"message": "Goal restored"}


@router.put("/programmes/{programme_id}/goals/reorder")
async def reorder_goals(
    programme_id: int,
    req: Request,
    items: list[GoalReorderItem],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Batch-update sort_order for goals in a programme. Programme admin only."""
    check_programme_access(req, programme_id, db, user)
    ids = [item.id for item in items]
    goals = db.query(LearningGoal).filter(
        LearningGoal.id.in_(ids),
        LearningGoal.programme_id == programme_id,
    ).all()
    if len(goals) != len(ids):
        raise HTTPException(status_code=400, detail="Some goals do not belong to this programme")
    order_map = {item.id: item.sort_order for item in items}
    for goal in goals:
        goal.sort_order = order_map[goal.id]
    db.commit()
    return {"message": "Goals reordered"}


# ============================================
# Staff Assignments
# ============================================

@router.post("/goals/{goal_id}/assign/{user_id}")
async def assign_staff_to_goal(
    goal_id: int,
    user_id: int,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign a staff member to a goal."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    check_programme_access(req, goal.programme_id, db, current_user)

    target_user = db.query(User).filter(User.uuid == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already assigned
    existing = (
        db.query(GoalStaffAssignment)
        .filter(GoalStaffAssignment.goal_id == goal_id, GoalStaffAssignment.user_id == user_id)
        .first()
    )
    if existing:
        return {"message": "User already assigned to this goal"}

    assignment = GoalStaffAssignment(
        goal_id=goal_id,
        user_id=user_id,
        assigned_by=current_user.uuid,
    )
    db.add(assignment)
    db.commit()

    return {"message": "Staff assigned to goal"}


@router.delete("/goals/{goal_id}/assign/{user_id}")
async def unassign_staff_from_goal(
    goal_id: int,
    user_id: int,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a staff assignment from a goal."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    check_programme_access(req, goal.programme_id, db, current_user)
    db.query(GoalStaffAssignment).filter(
        GoalStaffAssignment.goal_id == goal_id,
        GoalStaffAssignment.user_id == user_id,
    ).delete()
    db.commit()
    return {"message": "Staff unassigned from goal"}


# ============================================
# Goal-Course Matrix
# ============================================

@router.get("/programmes/{programme_id}/matrix")
async def get_programme_matrix(
    programme_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get the goal-course matrix for a programme."""
    # Get all goals for this programme with categories
    goals = (
        db.query(LearningGoal)
        .options(joinedload(LearningGoal.category))
        .filter(LearningGoal.programme_id == programme_id)
        .order_by(LearningGoal.goal_category, LearningGoal.id)
        .all()
    )

    # Get all categories used by goals
    categories = {}
    for g in goals:
        if g.category and g.category.id not in categories:
            categories[g.category.id] = {
                "id": g.category.id,
                "name_no": g.category.name_no,
                "name_eng": g.category.name_eng,
            }

    # Get all courses for this programme with semester info
    programme_courses = (
        db.query(ProgrammeCourse)
        .options(joinedload(ProgrammeCourse.course))
        .filter(ProgrammeCourse.programme_id == programme_id)
        .all()
    )

    # Build course info with semester
    course_semester_map = {}
    for pc in programme_courses:
        course_semester_map[pc.course.id] = {
            "course": pc.course,
            "semester": pc.semester,  # 1, 2, 3, etc.
        }

    # Get unique courses
    courses = list({pc.course.id: pc.course for pc in programme_courses}.values())

    # Get matrix entries
    matrix = (
        db.query(GoalCourseMatrix)
        .filter(
            GoalCourseMatrix.goal_id.in_([g.id for g in goals]),
            GoalCourseMatrix.course_id.in_([c.id for c in courses]),
        )
        .all()
    )

    # Build matrix lookup
    matrix_lookup = {(m.goal_id, m.course_id): m for m in matrix}

    # Get course metadata (learning methods, assessment methods, technologies, SDGs)
    course_ids = [c.id for c in courses]

    learning_methods_data = (
        db.query(CourseLearningMethod)
        .filter(
            CourseLearningMethod.programme_id == programme_id,
            CourseLearningMethod.course_id.in_(course_ids),
        )
        .all()
    )

    assessment_methods_data = (
        db.query(CourseAssessmentMethod)
        .filter(
            CourseAssessmentMethod.programme_id == programme_id,
            CourseAssessmentMethod.course_id.in_(course_ids),
        )
        .all()
    )

    technologies_data = (
        db.query(CourseTechnology)
        .filter(
            CourseTechnology.programme_id == programme_id,
            CourseTechnology.course_id.in_(course_ids),
        )
        .all()
    )

    metadata = (
        db.query(ProgrammeCourseMetadata)
        .filter(
            ProgrammeCourseMetadata.programme_id == programme_id,
            ProgrammeCourseMetadata.course_id.in_(course_ids),
        )
        .all()
    )

    # Build lookups
    learning_by_course = {}
    for lm in learning_methods_data:
        if lm.course_id not in learning_by_course:
            learning_by_course[lm.course_id] = []
        learning_by_course[lm.course_id].append(lm.method.code)

    assessment_by_course = {}
    for am in assessment_methods_data:
        if am.course_id not in assessment_by_course:
            assessment_by_course[am.course_id] = []
        assessment_by_course[am.course_id].append(am.method.code)

    tech_by_course = {}
    for t in technologies_data:
        if t.course_id not in tech_by_course:
            tech_by_course[t.course_id] = []
        tech_by_course[t.course_id].append(t.technology.code)

    sdgs_by_course = {m.course_id: m.sdgs for m in metadata}

    # Sort courses by semester then by course code
    def course_sort_key(c):
        info = course_semester_map.get(c.id, {})
        sem = info.get("semester", 99)
        return (sem, c.course_code)

    return {
        "categories": list(categories.values()),
        "goals": [
            {
                "id": g.id,
                "goal_no": g.goal_no,
                "goal_eng": g.goal_eng,
                "category_id": g.goal_category,
                "category_name": g.category.name_eng if g.category else None,
            }
            for g in goals
        ],
        "courses": [
            {
                "id": c.id,
                "course_code": c.course_code,
                "name_no": c.name_no,
                "name_eng": c.name_eng,
                "semester": course_semester_map.get(c.id, {}).get("semester", 1),
                "learning_methods": learning_by_course.get(c.id, []),
                "assessment_methods": assessment_by_course.get(c.id, []),
                "technologies": tech_by_course.get(c.id, []),
                "sdgs": sdgs_by_course.get(c.id, ""),
            }
            for c in sorted(courses, key=course_sort_key)
        ],
        "matrix": [
            {
                "goal_id": m.goal_id,
                "course_id": m.course_id,
                "learning_level": m.learning_level or 0,
                "is_assessed": m.is_assessed or False,
            }
            for m in matrix
        ],
    }


@router.put("/matrix/{goal_id}/{course_id}")
async def update_matrix_entry(
    goal_id: int,
    course_id: int,
    request: MatrixEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a goal-course matrix entry. Admin or course coordinator."""
    auth_service = AuthService(db)
    roles = auth_service.get_user_roles(user)
    if "system_admin" not in roles and not is_course_coordinator(user, course_id, db):
        raise HTTPException(status_code=403, detail="Not authorized to update this matrix entry")
    # Get or create matrix entry
    entry = (
        db.query(GoalCourseMatrix)
        .filter(GoalCourseMatrix.goal_id == goal_id, GoalCourseMatrix.course_id == course_id)
        .first()
    )

    if not entry:
        entry = GoalCourseMatrix(
            goal_id=goal_id,
            course_id=course_id,
            learning_level=request.learning_level,
            is_assessed=request.is_assessed,
            updated_by=user.uuid,
        )
        db.add(entry)
    else:
        entry.learning_level = request.learning_level
        entry.is_assessed = request.is_assessed
        entry.updated_by = user.uuid

    db.commit()
    return {"message": "Matrix updated"}


# ============================================
# Lookup Tables (Methods, Technologies)
# ============================================

@router.get("/academic-years")
async def get_academic_years(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return academic years from 6 years ago through 6 years ahead, newest first."""
    from datetime import date
    current_year = date.today().year
    start = date(current_year - 6, 7, 1)
    end = date(current_year + 6, 7, 1)
    years = (
        db.query(AcadYear)
        .filter(AcadYear.start_date >= start, AcadYear.start_date < end)
        .order_by(AcadYear.start_date.desc())
        .all()
    )
    return [{"id": y.id, "name": y.name} for y in years]


@router.get("/methods/learning")
async def get_learning_methods(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all available learning methods."""
    methods = db.query(LearningMethod).order_by(LearningMethod.sort_order).all()
    return [
        {"id": m.id, "code": m.code, "name_eng": m.name_eng, "name_no": m.name_no}
        for m in methods
    ]


@router.get("/methods/assessment")
async def get_assessment_methods(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all available assessment methods."""
    methods = db.query(AssessmentMethod).order_by(AssessmentMethod.sort_order).all()
    return [
        {"id": m.id, "code": m.code, "name_eng": m.name_eng, "name_no": m.name_no}
        for m in methods
    ]


@router.get("/technologies")
async def get_technologies(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all available technologies."""
    techs = db.query(Technology).all()
    return [
        {"id": t.id, "code": t.code, "name_eng": t.name_eng, "name_no": t.name_no}
        for t in techs
    ]


# ============================================
# Course Metadata
# ============================================

@router.put("/programmes/{programme_id}/courses/{course_id}/metadata")
async def update_course_metadata(
    programme_id: int,
    course_id: int,
    req: Request,
    request: CourseMetadataUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update course metadata (learning methods, assessment methods, technologies, SDGs)."""
    check_programme_access(req, programme_id, db, user)
    # Update learning methods
    db.query(CourseLearningMethod).filter(
        CourseLearningMethod.programme_id == programme_id,
        CourseLearningMethod.course_id == course_id,
    ).delete()

    for code in request.learning_methods:
        method = db.query(LearningMethod).filter(LearningMethod.code == code).first()
        if method:
            db.add(CourseLearningMethod(
                programme_id=programme_id,
                course_id=course_id,
                method_id=method.id,
            ))

    # Update assessment methods
    db.query(CourseAssessmentMethod).filter(
        CourseAssessmentMethod.programme_id == programme_id,
        CourseAssessmentMethod.course_id == course_id,
    ).delete()

    for code in request.assessment_methods:
        method = db.query(AssessmentMethod).filter(AssessmentMethod.code == code).first()
        if method:
            db.add(CourseAssessmentMethod(
                programme_id=programme_id,
                course_id=course_id,
                method_id=method.id,
            ))

    # Update technologies
    db.query(CourseTechnology).filter(
        CourseTechnology.programme_id == programme_id,
        CourseTechnology.course_id == course_id,
    ).delete()

    for code in request.technologies:
        tech = db.query(Technology).filter(Technology.code == code).first()
        if tech:
            db.add(CourseTechnology(
                programme_id=programme_id,
                course_id=course_id,
                technology_id=tech.id,
            ))

    # Update SDGs
    metadata = db.query(ProgrammeCourseMetadata).filter(
        ProgrammeCourseMetadata.programme_id == programme_id,
        ProgrammeCourseMetadata.course_id == course_id,
    ).first()

    sdgs_str = ",".join(str(s) for s in request.sdgs) if request.sdgs else ""

    if not metadata:
        metadata = ProgrammeCourseMetadata(
            programme_id=programme_id,
            course_id=course_id,
            sdgs=sdgs_str,
            updated_by=user.uuid,
        )
        db.add(metadata)
    else:
        metadata.sdgs = sdgs_str
        metadata.updated_by = user.uuid

    db.commit()
    return {"message": "Course metadata updated"}


# ============================================
# Rubrics
# ============================================

@router.get("/goals/{goal_id}/rubrics", response_model=list[RubricResponse])
async def list_rubrics(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all rubrics for a goal."""
    rubrics = (
        db.query(Rubric)
        .options(joinedload(Rubric.traits))
        .filter(Rubric.goal_id == goal_id)
        .all()
    )
    return [
        RubricResponse(
            id=r.id,
            goal_id=r.goal_id,
            name=r.name,
            description=r.description,
            rubric_type=r.rubric_type.value if r.rubric_type else "analytic",
            measure_type=r.measure_type or "direct",
            active=r.active,
            traits=[
                TraitResponse(
                    id=t.id,
                    name=t.name,
                    description=t.description,
                    sort_order=t.sort_order,
                    level_does_not_meet=t.level_does_not_meet,
                    level_meets=t.level_meets,
                    level_exceeds=t.level_exceeds,
                )
                for t in sorted(r.traits, key=lambda x: x.sort_order)
            ],
        )
        for r in rubrics
    ]


@router.post("/goals/{goal_id}/rubrics", response_model=RubricResponse)
async def create_rubric(
    goal_id: int,
    request: RubricCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new rubric for a goal."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    if not can_edit_goal(user, goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to edit this goal")

    rubric = Rubric(
        goal_id=goal_id,
        name=request.name,
        description=request.description,
        rubric_type=request.rubric_type,
        measure_type=request.measure_type,
        created_by=user.uuid,
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)

    return RubricResponse(
        id=rubric.id,
        goal_id=rubric.goal_id,
        name=rubric.name,
        description=rubric.description,
        rubric_type=rubric.rubric_type.value if rubric.rubric_type else "analytic",
        measure_type=rubric.measure_type or "direct",
        active=rubric.active,
        traits=[],
    )


@router.patch("/rubrics/{rubric_id}", response_model=RubricResponse)
async def update_rubric(
    rubric_id: int,
    request: RubricUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a rubric."""
    rubric = (
        db.query(Rubric)
        .options(joinedload(Rubric.goal), joinedload(Rubric.traits))
        .filter(Rubric.id == rubric_id)
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    if not can_edit_goal(user, rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to edit this rubric")

    if request.name is not None:
        rubric.name = request.name
    if request.description is not None:
        rubric.description = request.description
    if request.active is not None:
        rubric.active = request.active
    if request.measure_type is not None:
        rubric.measure_type = request.measure_type

    db.commit()
    db.refresh(rubric)

    return RubricResponse(
        id=rubric.id,
        goal_id=rubric.goal_id,
        name=rubric.name,
        description=rubric.description,
        rubric_type=rubric.rubric_type.value if rubric.rubric_type else "analytic",
        measure_type=rubric.measure_type or "direct",
        active=rubric.active,
        traits=[
            TraitResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                sort_order=t.sort_order,
                level_does_not_meet=t.level_does_not_meet,
                level_meets=t.level_meets,
                level_exceeds=t.level_exceeds,
            )
            for t in sorted(rubric.traits, key=lambda x: x.sort_order)
        ],
    )


@router.delete("/rubrics/{rubric_id}")
async def delete_rubric(
    rubric_id: int,
    req: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a rubric. Empty rubrics: programme admins. Non-empty: system_admin only."""
    rubric = (
        db.query(Rubric)
        .options(joinedload(Rubric.goal))
        .filter(Rubric.id == rubric_id)
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    has_assessments = db.query(Assessment).filter(Assessment.rubric_id == rubric_id).count() > 0
    real_user = getattr(req.state, "real_user", user)
    auth_service = AuthService(db)

    if has_assessments:
        if "system_admin" not in auth_service.get_user_roles(real_user):
            raise HTTPException(status_code=403, detail="Only system admins can delete rubrics with assessment data")
    else:
        if not can_edit_goal(user, rubric.goal, db):
            raise HTTPException(status_code=403, detail="Not authorized to delete this rubric")

    db.delete(rubric)
    db.commit()
    return {"message": "Rubric deleted"}


# ============================================
# Traits
# ============================================

@router.post("/rubrics/{rubric_id}/traits", response_model=TraitResponse)
async def create_trait(
    rubric_id: int,
    request: TraitCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a trait to a rubric."""
    rubric = db.query(Rubric).options(joinedload(Rubric.goal)).filter(Rubric.id == rubric_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    if not can_edit_goal(user, rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to edit this rubric")

    trait = RubricTrait(
        rubric_id=rubric_id,
        name=request.name,
        description=request.description,
        sort_order=request.sort_order,
        level_does_not_meet=request.level_does_not_meet,
        level_meets=request.level_meets,
        level_exceeds=request.level_exceeds,
    )
    db.add(trait)
    db.commit()
    db.refresh(trait)

    return TraitResponse(
        id=trait.id,
        name=trait.name,
        description=trait.description,
        sort_order=trait.sort_order,
        level_does_not_meet=trait.level_does_not_meet,
        level_meets=trait.level_meets,
        level_exceeds=trait.level_exceeds,
    )


@router.patch("/traits/{trait_id}", response_model=TraitResponse)
async def update_trait(
    trait_id: int,
    request: TraitUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a trait."""
    trait = (
        db.query(RubricTrait)
        .options(joinedload(RubricTrait.rubric).joinedload(Rubric.goal))
        .filter(RubricTrait.id == trait_id)
        .first()
    )
    if not trait:
        raise HTTPException(status_code=404, detail="Trait not found")

    if not can_edit_goal(user, trait.rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to edit this trait")

    if request.name is not None:
        trait.name = request.name
    if request.description is not None:
        trait.description = request.description
    if request.sort_order is not None:
        trait.sort_order = request.sort_order
    if request.level_does_not_meet is not None:
        trait.level_does_not_meet = request.level_does_not_meet
    if request.level_meets is not None:
        trait.level_meets = request.level_meets
    if request.level_exceeds is not None:
        trait.level_exceeds = request.level_exceeds

    db.commit()
    db.refresh(trait)

    return TraitResponse(
        id=trait.id,
        name=trait.name,
        description=trait.description,
        sort_order=trait.sort_order,
        level_does_not_meet=trait.level_does_not_meet,
        level_meets=trait.level_meets,
        level_exceeds=trait.level_exceeds,
    )


@router.delete("/traits/{trait_id}")
async def delete_trait(
    trait_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a trait."""
    trait = (
        db.query(RubricTrait)
        .options(joinedload(RubricTrait.rubric).joinedload(Rubric.goal))
        .filter(RubricTrait.id == trait_id)
        .first()
    )
    if not trait:
        raise HTTPException(status_code=404, detail="Trait not found")

    if not can_edit_goal(user, trait.rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to delete this trait")

    db.delete(trait)
    db.commit()
    return {"message": "Trait deleted"}


# ============================================
# Assessments
# ============================================

@router.get("/rubrics/{rubric_id}/assessments", response_model=list[AssessmentResponse])
async def list_assessments(
    rubric_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all assessments for a rubric."""
    assessments = (
        db.query(Assessment)
        .options(joinedload(Assessment.course), joinedload(Assessment.results).joinedload(AssessmentResult.trait))
        .filter(Assessment.rubric_id == rubric_id)
        .order_by(Assessment.assessment_date.desc())
        .all()
    )

    return [
        AssessmentResponse(
            id=a.id,
            rubric_id=a.rubric_id,
            course_id=a.course_id,
            course_code=a.course.course_code,
            academic_year_id=a.academic_year_id,
            semester_id=a.semester_id,
            assessment_date=str(a.assessment_date) if a.assessment_date else None,
            total_students=a.total_students,
            notes=a.notes,
            results=[
                AssessmentResultResponse(
                    trait_id=r.trait_id,
                    trait_name=r.trait.name,
                    count_does_not_meet=r.count_does_not_meet,
                    count_meets=r.count_meets,
                    count_exceeds=r.count_exceeds,
                    meets_or_exceeds_pct=r.meets_or_exceeds_percentage,
                )
                for r in a.results
            ],
        )
        for a in assessments
    ]


@router.post("/assessments", response_model=AssessmentResponse)
async def create_assessment(
    request: AssessmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new assessment."""
    rubric = db.query(Rubric).options(joinedload(Rubric.goal)).filter(Rubric.id == request.rubric_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    if not can_edit_goal(user, rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to create assessment for this goal")

    course = db.query(Course).filter(Course.id == request.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    assessment = Assessment(
        rubric_id=request.rubric_id,
        course_id=request.course_id,
        academic_year_id=request.academic_year_id,
        semester_id=request.semester_id,
        assessment_date=request.assessment_date,
        total_students=request.total_students,
        notes=request.notes,
        created_by=user.uuid,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return AssessmentResponse(
        id=assessment.id,
        rubric_id=assessment.rubric_id,
        course_id=assessment.course_id,
        course_code=course.course_code,
        academic_year_id=assessment.academic_year_id,
        semester_id=assessment.semester_id,
        assessment_date=str(assessment.assessment_date) if assessment.assessment_date else None,
        total_students=assessment.total_students,
        notes=assessment.notes,
        results=[],
    )


@router.post("/assessments/{assessment_id}/results")
async def add_assessment_results(
    assessment_id: int,
    results: list[AssessmentResultCreate],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add or update results for an assessment."""
    assessment = (
        db.query(Assessment)
        .options(joinedload(Assessment.rubric).joinedload(Rubric.goal))
        .filter(Assessment.id == assessment_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if not can_edit_goal(user, assessment.rubric.goal, db):
        raise HTTPException(status_code=403, detail="Not authorized to edit this assessment")

    for result in results:
        existing = (
            db.query(AssessmentResult)
            .filter(
                AssessmentResult.assessment_id == assessment_id,
                AssessmentResult.trait_id == result.trait_id,
            )
            .first()
        )

        if existing:
            existing.count_does_not_meet = result.count_does_not_meet
            existing.count_meets = result.count_meets
            existing.count_exceeds = result.count_exceeds
        else:
            new_result = AssessmentResult(
                assessment_id=assessment_id,
                trait_id=result.trait_id,
                count_does_not_meet=result.count_does_not_meet,
                count_meets=result.count_meets,
                count_exceeds=result.count_exceeds,
            )
            db.add(new_result)

    # Update total students
    total = sum(r.count_does_not_meet + r.count_meets + r.count_exceeds for r in results)
    if total > 0:
        assessment.total_students = total // len(results)  # Average across traits

    db.commit()
    return {"message": "Results saved"}


# ============================================
# Programme Courses
# ============================================

@router.get("/programmes/{programme_id}/courses", response_model=list[CourseResponse])
async def list_programme_courses(
    programme_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all courses in a programme."""
    programme_courses = (
        db.query(ProgrammeCourse)
        .options(joinedload(ProgrammeCourse.course))
        .filter(ProgrammeCourse.programme_id == programme_id)
        .all()
    )

    # Get unique courses
    courses = list({pc.course.id: pc.course for pc in programme_courses}.values())

    return [
        CourseResponse(
            id=c.id,
            course_code=c.course_code,
            course_version=c.course_version,
            name_no=c.name_no,
            name_eng=c.name_eng,
            ects=float(c.ects),
        )
        for c in sorted(courses, key=lambda x: x.course_code)
    ]


class CourseSemesterUpdate(BaseModel):
    semester: int


@router.post("/programmes/{programme_id}/courses/{course_id}")
async def add_course_to_programme(
    programme_id: int,
    course_id: int,
    req: Request,
    year: int = 1,
    semester: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a course to a programme. Admin or programme admin_staff only."""
    check_programme_access(req, programme_id, db, user)
    # Verify programme and course exist
    prog = db.query(StudyProgramme).filter(StudyProgramme.id == programme_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Check if already linked
    existing = (
        db.query(ProgrammeCourse)
        .filter(
            ProgrammeCourse.programme_id == programme_id,
            ProgrammeCourse.course_id == course_id,
            ProgrammeCourse.track_id == 0,
        )
        .first()
    )
    if existing:
        return {"message": "Course already in programme"}

    link = ProgrammeCourse(
        course_id=course_id,
        programme_id=programme_id,
        track_id=0,  # Default track
        year=year,
        semester=semester,
    )
    db.add(link)
    db.commit()

    return {"message": "Course added to programme"}


@router.put("/programmes/{programme_id}/courses/{course_id}/semester")
async def update_course_semester(
    programme_id: int,
    course_id: int,
    req: Request,
    request: CourseSemesterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update the semester for a course in a programme. Admin or programme admin_staff only."""
    check_programme_access(req, programme_id, db, user)
    pc = (
        db.query(ProgrammeCourse)
        .filter(
            ProgrammeCourse.programme_id == programme_id,
            ProgrammeCourse.course_id == course_id,
        )
        .first()
    )
    if not pc:
        raise HTTPException(status_code=404, detail="Course not in programme")

    pc.semester = request.semester
    db.commit()
    return {"message": "Semester updated"}


# ============================================================
# Course administration
# ============================================================

@router.get("/courses")
async def list_courses(
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all courses with optional search filter."""
    query = db.query(Course)
    if q:
        query = query.filter(
            (Course.course_code.ilike(f"%{q}%"))
            | (Course.name_no.ilike(f"%{q}%"))
            | (Course.name_eng.ilike(f"%{q}%"))
        )
    courses = query.order_by(Course.course_code, Course.course_version).all()

    result = []
    for c in courses:
        # Current coordinator (no end_date or end_date in future)
        from datetime import date
        today = date.today()
        current_coord = next(
            (cc for cc in c.coordinators
             if (cc.start_date is None or cc.start_date <= today)
             and (cc.end_date is None or cc.end_date >= today)),
            None,
        )
        result.append({
            "id": c.id,
            "course_code": c.course_code,
            "course_version": c.course_version,
            "name_no": c.name_no,
            "name_eng": c.name_eng,
            "ects": float(c.ects),
            "prme_report": bool(c.prme_report),
            "coordinator": {
                "id": current_coord.user.uuid,
                "name": current_coord.user.full_name,
            } if current_coord else None,
        })
    return result


@router.get("/courses/search")
async def search_courses(
    q: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search courses by code or name."""
    courses = (
        db.query(Course)
        .filter(
            (Course.course_code.ilike(f"%{q}%"))
            | (Course.name_no.ilike(f"%{q}%"))
            | (Course.name_eng.ilike(f"%{q}%"))
        )
        .limit(20)
        .all()
    )

    return [
        CourseResponse(
            id=c.id,
            course_code=c.course_code,
            course_version=c.course_version,
            name_no=c.name_no,
            name_eng=c.name_eng,
            ects=float(c.ects),
        )
        for c in courses
    ]


@router.get("/courses/{course_id}")
async def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full course detail: coordinators, programmes, goal mappings."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    from datetime import date
    today = date.today()

    # Coordinator history
    coordinators = []
    for cc in sorted(course.coordinators, key=lambda x: x.start_date or date.min, reverse=True):
        coordinators.append({
            "id": cc.id,
            "user_id": cc.user.uuid,
            "name": cc.user.full_name,
            "email": cc.user.email,
            "start_date": cc.start_date.isoformat() if cc.start_date else None,
            "end_date": cc.end_date.isoformat() if cc.end_date else None,
            "is_current": (
                (cc.start_date is None or cc.start_date <= today)
                and (cc.end_date is None or cc.end_date >= today)
            ),
        })

    # Programmes this course belongs to
    programmes = []
    for pc in course.programmes:
        programmes.append({
            "programme_id": pc.programme.id,
            "programme_code": pc.programme.programme_code,
            "name_no": pc.programme.name_no,
            "semester": pc.semester,
        })

    # Learning goal mappings
    goals = []
    for gm in course.goal_mappings:
        if gm.learning_level and gm.learning_level > 0:
            goals.append({
                "goal_id": gm.goal.id,
                "goal_no": gm.goal.goal_no,
                "goal_eng": gm.goal.goal_eng,
                "programme_code": gm.goal.programme.programme_code,
                "learning_level": gm.learning_level,
                "is_assessed": gm.is_assessed,
            })

    return {
        "id": course.id,
        "course_code": course.course_code,
        "course_version": course.course_version,
        "name_no": course.name_no,
        "name_eng": course.name_eng,
        "ects": float(course.ects),
        "prme_report": bool(course.prme_report),
        "coordinators": coordinators,
        "programmes": programmes,
        "goals": goals,
    }


@router.patch("/courses/{course_id}/prme")
async def set_course_prme(
    course_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Toggle PRME reporting flag on a course (admin only)."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    course.prme_report = not course.prme_report
    db.commit()
    return {"prme_report": bool(course.prme_report)}


@router.get("/courses/{course_id}/matrix-view")
async def get_course_matrix_view(
    course_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-course view of all programmes and their learning goals with matrix values.
    Accessible by system_admin or the active course coordinator."""
    auth_service = AuthService(db)
    roles = auth_service.get_user_roles(user)
    if "system_admin" not in roles and not is_course_coordinator(user, course_id, db):
        raise HTTPException(status_code=403, detail="Not authorized")

    course = (
        db.query(Course)
        .options(
            joinedload(Course.programmes).joinedload(ProgrammeCourse.programme),
        )
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    programmes = []
    for pc in course.programmes:
        prog = pc.programme
        goals = (
            db.query(LearningGoal)
            .options(joinedload(LearningGoal.category))
            .filter(LearningGoal.programme_id == prog.id)
            .order_by(LearningGoal.goal_category, LearningGoal.id)
            .all()
        )
        matrix_entries = {
            e.goal_id: e
            for e in db.query(GoalCourseMatrix).filter(
                GoalCourseMatrix.course_id == course_id,
                GoalCourseMatrix.goal_id.in_([g.id for g in goals]),
            ).all()
        }
        goal_list = []
        for g in goals:
            entry = matrix_entries.get(g.id)
            goal_list.append({
                "goal_id": g.id,
                "goal_no": g.goal_no,
                "goal_eng": g.goal_eng,
                "category_id": g.goal_category,
                "category_name_no": g.category.name_no if g.category else None,
                "category_name_eng": g.category.name_eng if g.category else None,
                "learning_level": entry.learning_level if entry else 0,
                "is_assessed": entry.is_assessed if entry else False,
            })
        programmes.append({
            "programme_id": prog.id,
            "programme_code": prog.programme_code,
            "name_no": prog.name_no,
            "name_eng": prog.name_eng,
            "semester": pc.semester,
            "goals": goal_list,
        })

    return {
        "id": course.id,
        "course_code": course.course_code,
        "course_version": course.course_version,
        "name_no": course.name_no,
        "name_eng": course.name_eng,
        "ects": float(course.ects),
        "programmes": programmes,
    }


class CoordinatorCreate(BaseModel):
    user_id: int
    start_date: str | None = None
    end_date: str | None = None


class CoordinatorUpdate(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


@router.post("/courses/{course_id}/coordinators")
async def add_coordinator(
    course_id: int,
    body: CoordinatorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin", "admin_staff")),
):
    """Assign a coordinator to a course (admin only)."""
    from datetime import date

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    auth_service = AuthService(db)
    target = auth_service.get_user_by_id(body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    cc = CourseCoordinator(
        course_id=course_id,
        user_id=body.user_id,
        assigned_by=user.uuid,
        start_date=date.fromisoformat(body.start_date) if body.start_date else None,
        end_date=date.fromisoformat(body.end_date) if body.end_date else None,
    )
    db.add(cc)
    db.commit()
    db.refresh(cc)

    return {
        "id": cc.id,
        "user_id": cc.user_id,
        "name": cc.user.full_name,
        "start_date": cc.start_date.isoformat() if cc.start_date else None,
        "end_date": cc.end_date.isoformat() if cc.end_date else None,
    }


@router.put("/courses/{course_id}/coordinators/{coordinator_id}")
async def update_coordinator(
    course_id: int,
    coordinator_id: int,
    body: CoordinatorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin", "admin_staff")),
):
    """Update coordinator start/end dates (admin only)."""
    from datetime import date

    cc = db.query(CourseCoordinator).filter(
        CourseCoordinator.id == coordinator_id,
        CourseCoordinator.course_id == course_id,
    ).first()
    if not cc:
        raise HTTPException(status_code=404, detail="Coordinator entry not found")

    cc.start_date = date.fromisoformat(body.start_date) if body.start_date else None
    cc.end_date = date.fromisoformat(body.end_date) if body.end_date else None
    db.commit()

    return {"message": "Updated"}


@router.delete("/courses/{course_id}/coordinators/{coordinator_id}")
async def remove_coordinator(
    course_id: int,
    coordinator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin", "admin_staff")),
):
    """Remove a coordinator entry (admin only)."""
    cc = db.query(CourseCoordinator).filter(
        CourseCoordinator.id == coordinator_id,
        CourseCoordinator.course_id == course_id,
    ).first()
    if not cc:
        raise HTTPException(status_code=404, detail="Coordinator entry not found")

    db.delete(cc)
    db.commit()
    return {"message": "Removed"}
