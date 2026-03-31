from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import date

from database import get_db
from dependencies import get_current_user
from models import User, CourseCoordinator, UserProgrammeRole, UserIntellectualContribution

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return dashboard data: coordinator courses and programme roles."""
    today = date.today()

    # Courses where user is currently active coordinator
    coordinator_records = (
        db.query(CourseCoordinator)
        .options(joinedload(CourseCoordinator.course))
        .filter(
            CourseCoordinator.user_id == current_user.uuid,
        )
        .all()
    )

    coordinator_courses = []
    for cc in coordinator_records:
        start_ok = cc.start_date is None or cc.start_date <= today
        end_ok = cc.end_date is None or cc.end_date >= today
        if start_ok and end_ok:
            coordinator_courses.append({
                "id": cc.course.id,
                "course_code": cc.course.course_code,
                "name_no": cc.course.name_no,
                "name_eng": cc.course.name_eng,
                "ects": float(cc.course.ects),
            })

    # Programmes where user has a role
    programme_role_records = (
        db.query(UserProgrammeRole)
        .options(
            joinedload(UserProgrammeRole.programme),
            joinedload(UserProgrammeRole.role),
        )
        .filter(UserProgrammeRole.user_id == current_user.uuid)
        .all()
    )

    programme_roles = [
        {
            "programme_id": pr.programme_id,
            "programme_code": pr.programme.programme_code,
            "name_no": pr.programme.name_no,
            "name_eng": pr.programme.name_eng,
            "role": pr.role.role_name,
        }
        for pr in programme_role_records
    ]

    # Publications classified in DB (no NVA call needed)
    publications_classified = 0
    if current_user.researcher_id:
        publications_classified = (
            db.query(func.count())
            .select_from(UserIntellectualContribution)
            .filter(
                UserIntellectualContribution.user_id == current_user.uuid,
                UserIntellectualContribution.publication_type.isnot(None),
            )
            .scalar()
        ) or 0

    return {
        "coordinator_courses": coordinator_courses,
        "programme_roles": programme_roles,
        "has_researcher_id": bool(current_user.researcher_id),
        "publications_classified": publications_classified,
    }
