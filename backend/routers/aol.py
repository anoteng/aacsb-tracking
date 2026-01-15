from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Literal

from database import get_db
from dependencies import get_current_user, require_role
from services.auth import AuthService
from models import (
    User,
    StudyProgramme,
    Course,
    ProgrammeCourse,
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
    is_measured: bool = False
    target_percentage: float = 80.0


class LearningGoalUpdate(BaseModel):
    goal_no: str | None = None
    goal_eng: str | None = None
    goal_category: int | None = None
    is_measured: bool | None = None
    target_percentage: float | None = None


class LearningGoalResponse(BaseModel):
    id: int
    goal_no: str | None
    goal_eng: str | None
    category: GoalCategoryResponse
    programme_id: int
    is_measured: bool
    target_percentage: float
    assigned_staff: list[dict] = []

    class Config:
        from_attributes = True


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


class RubricUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    active: bool | None = None


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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all learning goals for a programme."""
    goals = (
        db.query(LearningGoal)
        .options(joinedload(LearningGoal.category), joinedload(LearningGoal.staff_assignments))
        .filter(LearningGoal.programme_id == programme_id)
        .all()
    )

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
                is_measured=g.is_measured,
                target_percentage=float(g.target_percentage) if g.target_percentage else 80.0,
                assigned_staff=assigned,
            )
        )
    return result


@router.post("/programmes/{programme_id}/goals", response_model=LearningGoalResponse)
async def create_goal(
    programme_id: int,
    request: LearningGoalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Create a new learning goal. Admin only."""
    # Verify programme exists
    prog = db.query(StudyProgramme).filter(StudyProgramme.id == programme_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")

    # Verify category exists
    cat = db.query(GoalCategory).filter(GoalCategory.id == request.goal_category).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    goal = LearningGoal(
        goal_no=request.goal_no,
        goal_eng=request.goal_eng,
        goal_category=request.goal_category,
        programme_id=programme_id,
        is_measured=request.is_measured,
        target_percentage=request.target_percentage,
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
        is_measured=goal.is_measured,
        target_percentage=float(goal.target_percentage) if goal.target_percentage else 80.0,
        assigned_staff=[],
    )


@router.patch("/goals/{goal_id}", response_model=LearningGoalResponse)
async def update_goal(
    goal_id: int,
    request: LearningGoalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Update a learning goal. Admin only."""
    goal = db.query(LearningGoal).options(joinedload(LearningGoal.category)).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    if request.goal_no is not None:
        goal.goal_no = request.goal_no
    if request.goal_eng is not None:
        goal.goal_eng = request.goal_eng
    if request.goal_category is not None:
        goal.goal_category = request.goal_category
    if request.is_measured is not None:
        goal.is_measured = request.is_measured
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
        is_measured=goal.is_measured,
        target_percentage=float(goal.target_percentage) if goal.target_percentage else 80.0,
        assigned_staff=[
            {"user_id": a.user_id, "name": f"{a.user.firstname} {a.user.lastname}"}
            for a in goal.staff_assignments
        ],
    )


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Delete a learning goal. Admin only."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    db.delete(goal)
    db.commit()
    return {"message": "Goal deleted"}


# ============================================
# Staff Assignments
# ============================================

@router.post("/goals/{goal_id}/assign/{user_id}")
async def assign_staff_to_goal(
    goal_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "programme_leader")),
):
    """Assign a staff member to a goal."""
    goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "programme_leader")),
):
    """Remove a staff assignment from a goal."""
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
    user: User = Depends(require_role("system_admin")),
):
    """Update a goal-course matrix entry. Admin only."""
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
    request: CourseMetadataUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Update course metadata (learning methods, assessment methods, technologies, SDGs)."""
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

    db.commit()
    db.refresh(rubric)

    return RubricResponse(
        id=rubric.id,
        goal_id=rubric.goal_id,
        name=rubric.name,
        description=rubric.description,
        rubric_type=rubric.rubric_type.value if rubric.rubric_type else "analytic",
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
    year: int = 1,
    semester: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Add a course to a programme. Admin only."""
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
    request: CourseSemesterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("system_admin")),
):
    """Update the semester for a course in a programme. Admin only."""
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
