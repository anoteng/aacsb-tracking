from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional, List
import json

from database import get_db
from dependencies import get_current_user, require_role
from models import (
    User, FacultyCategory,
    IntellectualContribution, UserIntellectualContribution,
    ProfessionalActivity, PublicationType, PortfolioCategory,
    UserDiscipline, ExemptionType, UserExemption,
)
from services.nva import nva_service

router = APIRouter(prefix="/research", tags=["Research"])


# Pydantic models
class ICCategorization(BaseModel):
    publication_type: Optional[str] = None  # prj_article, peer_reviewed_other, other_ic
    portfolio_category: Optional[str] = None  # basic_discovery, applied_integration, teaching_learning
    societal_impact: Optional[str] = None


class ProfessionalActivityCreate(BaseModel):
    year: int
    activity_type: str
    description: Optional[str] = None


class ExemptionTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    reduces_ic_requirement: bool = False
    reduces_prj_requirement: bool = False
    reduces_activity_requirement: bool = False
    grants_full_exemption: bool = False
    ic_reduction: int = 0
    prj_reduction: int = 0
    activity_reduction: int = 0
    years_after_degree: Optional[int] = None


class UserExemptionCreate(BaseModel):
    exemption_type_id: int
    year_from: int
    year_to: Optional[int] = None
    notes: Optional[str] = None


# Helper: Get reference year
REFERENCE_YEAR = 2025


@router.get("/publications")
async def get_publications(
    year_from: Optional[int] = Query(default=None, description="Start year"),
    year_to: Optional[int] = Query(default=None, description="End year"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get publications for all staff with researcher IDs.
    Returns aggregated publication data for the last 6 years by default.
    """
    # Use 2025 as reference year (hardcoded to avoid system date issues)
    reference_year = 2025
    if not year_from:
        year_from = reference_year - 6  # 2019
    if not year_to:
        year_to = reference_year  # 2025

    # Get all users with researcher IDs
    researchers = (
        db.query(User)
        .filter(User.researcher_id.isnot(None), User.active == True)
        .all()
    )

    all_publications = []
    researcher_stats = []

    for researcher in researchers:
        try:
            pubs = await nva_service.get_person_publications(
                person_id=researcher.researcher_id,
                year_from=year_from,
                year_to=year_to,
            )

            parsed_pubs = [nva_service.parse_publication(p) for p in pubs]

            # Track publications (avoid duplicates by ID)
            for pub in parsed_pubs:
                existing = next((p for p in all_publications if p["id"] == pub["id"]), None)
                if not existing:
                    all_publications.append(pub)

            researcher_stats.append({
                "id": researcher.uuid,
                "name": f"{researcher.firstname} {researcher.lastname}",
                "researcher_id": researcher.researcher_id,
                "publication_count": len(parsed_pubs),
            })

        except Exception as e:
            researcher_stats.append({
                "id": researcher.uuid,
                "name": f"{researcher.firstname} {researcher.lastname}",
                "researcher_id": researcher.researcher_id,
                "publication_count": 0,
                "error": str(e),
            })

    # Sort publications by year descending
    all_publications.sort(key=lambda x: x.get("year") or 0, reverse=True)

    # Calculate statistics
    pub_by_year = {}
    pub_by_type = {}
    for pub in all_publications:
        year = pub.get("year")
        if year:
            pub_by_year[year] = pub_by_year.get(year, 0) + 1
        pub_type = pub.get("type", "Unknown")
        pub_by_type[pub_type] = pub_by_type.get(pub_type, 0) + 1

    return {
        "year_from": year_from,
        "year_to": year_to,
        "total_publications": len(all_publications),
        "total_researchers": len(researchers),
        "publications_by_year": pub_by_year,
        "publications_by_type": pub_by_type,
        "researchers": researcher_stats,
        "publications": all_publications,
    }


@router.get("/publications/user/{user_id}")
async def get_user_publications(
    user_id: int,
    year_from: Optional[int] = Query(default=None),
    year_to: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get publications for a specific user."""
    # Use 2025 as reference year (hardcoded to avoid system date issues)
    reference_year = 2025
    if not year_from:
        year_from = reference_year - 6  # 2019
    if not year_to:
        year_to = reference_year  # 2025

    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.researcher_id:
        raise HTTPException(status_code=400, detail="User has no researcher ID configured")

    try:
        pubs = await nva_service.get_person_publications(
            person_id=user.researcher_id,
            year_from=year_from,
            year_to=year_to,
        )
        parsed_pubs = [nva_service.parse_publication(p) for p in pubs]
        parsed_pubs.sort(key=lambda x: x.get("year") or 0, reverse=True)

        return {
            "user": {
                "id": user.uuid,
                "name": f"{user.firstname} {user.lastname}",
                "researcher_id": user.researcher_id,
            },
            "year_from": year_from,
            "year_to": year_to,
            "total": len(parsed_pubs),
            "publications": parsed_pubs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch publications: {str(e)}")


@router.get("/researchers")
async def list_researchers(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all users with researcher IDs."""
    researchers = (
        db.query(User)
        .filter(User.researcher_id.isnot(None), User.active == True)
        .order_by(User.lastname, User.firstname)
        .all()
    )

    return [
        {
            "id": r.uuid,
            "name": f"{r.firstname} {r.lastname}",
            "email": r.email,
            "researcher_id": r.researcher_id,
        }
        for r in researchers
    ]


# ============================================
# IC Categorization
# ============================================

def get_or_create_ic(db: Session, nva_id: str, pub_data: dict) -> IntellectualContribution:
    """Get existing IC or create new one from NVA data."""
    ic = db.query(IntellectualContribution).filter(IntellectualContribution.nva_id == nva_id).first()
    if not ic:
        ic = IntellectualContribution(
            nva_id=nva_id,
            title=pub_data.get("title", "Untitled"),
            year=pub_data.get("year"),
            nva_data=pub_data,
        )
        db.add(ic)
        db.commit()
        db.refresh(ic)
    return ic


@router.get("/my-contributions")
async def get_my_contributions(
    year_from: Optional[int] = Query(default=None),
    year_to: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's ICs with categorizations."""
    if not current_user.researcher_id:
        return {"contributions": [], "message": "No researcher ID configured"}

    if not year_from:
        year_from = REFERENCE_YEAR - 6
    if not year_to:
        year_to = REFERENCE_YEAR

    # Fetch from NVA
    try:
        nva_pubs = await nva_service.get_person_publications(
            person_id=current_user.researcher_id,
            year_from=year_from,
            year_to=year_to,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch from NVA: {str(e)}")

    contributions = []
    for pub in nva_pubs:
        parsed = nva_service.parse_publication(pub)
        nva_id = parsed.get("id")
        if not nva_id:
            continue

        # Get or create IC in our database
        ic = get_or_create_ic(db, nva_id, parsed)

        # Get user's categorization
        user_ic = (
            db.query(UserIntellectualContribution)
            .filter(
                UserIntellectualContribution.user_id == current_user.uuid,
                UserIntellectualContribution.ic_id == ic.id,
            )
            .first()
        )

        # Get other users' categorizations for this IC
        other_categorizations = (
            db.query(UserIntellectualContribution)
            .filter(
                UserIntellectualContribution.ic_id == ic.id,
                UserIntellectualContribution.user_id != current_user.uuid,
            )
            .all()
        )

        contributions.append({
            "ic_id": ic.id,
            "nva_id": nva_id,
            "title": parsed.get("title"),
            "year": parsed.get("year"),
            "type": parsed.get("type"),
            "contributors": parsed.get("contributors", []),
            "journal": parsed.get("journal"),
            "publisher": parsed.get("publisher"),
            "nva_url": parsed.get("nva_url"),
            "my_categorization": {
                "publication_type": user_ic.publication_type.value if user_ic and user_ic.publication_type else None,
                "portfolio_category": user_ic.portfolio_category.value if user_ic and user_ic.portfolio_category else None,
                "societal_impact": user_ic.societal_impact if user_ic else None,
            } if user_ic else None,
            "other_categorizations": [
                {
                    "publication_type": oc.publication_type.value if oc.publication_type else None,
                    "portfolio_category": oc.portfolio_category.value if oc.portfolio_category else None,
                }
                for oc in other_categorizations
            ],
        })

    return {
        "year_from": year_from,
        "year_to": year_to,
        "total": len(contributions),
        "contributions": contributions,
    }


@router.post("/contributions/{nva_id}/categorize")
async def categorize_contribution(
    nva_id: str,
    categorization: ICCategorization,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Categorize an IC for the current user."""
    # Find the IC
    ic = db.query(IntellectualContribution).filter(IntellectualContribution.nva_id == nva_id).first()
    if not ic:
        raise HTTPException(status_code=404, detail="Intellectual contribution not found. Fetch your contributions first.")

    # Get or create user's categorization
    user_ic = (
        db.query(UserIntellectualContribution)
        .filter(
            UserIntellectualContribution.user_id == current_user.uuid,
            UserIntellectualContribution.ic_id == ic.id,
        )
        .first()
    )

    if not user_ic:
        user_ic = UserIntellectualContribution(
            user_id=current_user.uuid,
            ic_id=ic.id,
        )
        db.add(user_ic)

    # Update categorization
    if categorization.publication_type is not None:
        if categorization.publication_type == "":
            user_ic.publication_type = None
        else:
            user_ic.publication_type = PublicationType(categorization.publication_type)

    if categorization.portfolio_category is not None:
        if categorization.portfolio_category == "":
            user_ic.portfolio_category = None
        else:
            user_ic.portfolio_category = PortfolioCategory(categorization.portfolio_category)

    if categorization.societal_impact is not None:
        user_ic.societal_impact = categorization.societal_impact if categorization.societal_impact else None

    db.commit()

    return {"message": "Categorization saved"}


# ============================================
# Professional Activities
# ============================================

@router.get("/my-activities")
async def get_my_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's professional activities."""
    activities = (
        db.query(ProfessionalActivity)
        .filter(ProfessionalActivity.user_id == current_user.uuid)
        .order_by(ProfessionalActivity.year.desc())
        .all()
    )

    return [
        {
            "id": a.id,
            "year": a.year,
            "activity_type": a.activity_type,
            "description": a.description,
        }
        for a in activities
    ]


@router.post("/my-activities")
async def add_activity(
    activity: ProfessionalActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a professional activity."""
    pa = ProfessionalActivity(
        user_id=current_user.uuid,
        year=activity.year,
        activity_type=activity.activity_type,
        description=activity.description,
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)

    return {
        "id": pa.id,
        "year": pa.year,
        "activity_type": pa.activity_type,
        "description": pa.description,
    }


@router.delete("/my-activities/{activity_id}")
async def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a professional activity."""
    deleted = (
        db.query(ProfessionalActivity)
        .filter(
            ProfessionalActivity.id == activity_id,
            ProfessionalActivity.user_id == current_user.uuid,
        )
        .delete()
    )
    db.commit()

    if deleted:
        return {"message": "Activity deleted"}
    raise HTTPException(status_code=404, detail="Activity not found")


# ============================================
# Qualification Status
# ============================================

def get_active_exemptions(user: User, year_from: int, year_to: int) -> list:
    """
    Get user's exemptions that are active during the evaluation period.
    Also includes exemptions that are within their grace period.
    """
    active = []
    for exemption in user.exemptions:
        ex_type = exemption.exemption_type
        exemption_end = exemption.year_to or REFERENCE_YEAR + 10  # If no end, treat as ongoing
        grace_period = ex_type.grace_period_years or 0

        # Effective end includes the grace period
        effective_end = exemption_end + grace_period

        # Check if exemption (including grace period) overlaps with evaluation period
        if exemption.year_from <= year_to and effective_end >= year_from:
            active.append(exemption)
    return active


def is_in_grace_period(exemption, reference_year: int) -> bool:
    """Check if an exemption is currently in its grace period (ended but within grace years)."""
    if not exemption.year_to:
        return False  # Still ongoing, not in grace period

    grace_period = exemption.exemption_type.grace_period_years or 0
    if grace_period == 0:
        return False

    # Grace period applies if: year_to < reference_year <= year_to + grace_period
    return exemption.year_to < reference_year <= (exemption.year_to + grace_period)


def calculate_qualification_status(user: User, contributions: list, activities: list, exemptions: list = None, reference_year: int = None) -> dict:
    """Calculate qualification status based on faculty category requirements and exemptions."""
    if reference_year is None:
        reference_year = REFERENCE_YEAR

    category = user.faculty_category
    if not category:
        return {"status": "not_set", "message": "Faculty category not set"}

    # Get active exemptions
    if exemptions is None:
        exemptions = get_active_exemptions(user, reference_year - 5, reference_year)

    # Check for full exemption (including grace periods)
    full_exemption = None
    full_exemption_reason = None
    for exemption in exemptions:
        ex_type = exemption.exemption_type
        if ex_type.grants_full_exemption:
            # Check if it's a years-after-degree exemption (e.g., New Doctoral Graduate)
            if ex_type.years_after_degree and user.degree_year:
                years_since_degree = reference_year - user.degree_year
                if years_since_degree <= ex_type.years_after_degree:
                    full_exemption = ex_type
                    full_exemption_reason = f"{ex_type.name} ({years_since_degree} of {ex_type.years_after_degree} years)"
                    break
            elif not ex_type.years_after_degree:
                # Check if in grace period after stepping down
                if is_in_grace_period(exemption, reference_year):
                    years_in_grace = reference_year - exemption.year_to
                    full_exemption = ex_type
                    full_exemption_reason = f"{ex_type.name} (grace period: year {years_in_grace} of {ex_type.grace_period_years})"
                    break
                elif not exemption.year_to or exemption.year_to >= reference_year:
                    # Still serving
                    full_exemption = ex_type
                    full_exemption_reason = f"{ex_type.name} (currently serving)"
                    break

    # Count ICs by type for the evaluation period
    prj_count = sum(1 for c in contributions if c.get("my_categorization", {}).get("publication_type") == "prj_article")
    peer_reviewed_count = sum(1 for c in contributions if c.get("my_categorization", {}).get("publication_type") == "peer_reviewed_other")
    other_ic_count = sum(1 for c in contributions if c.get("my_categorization", {}).get("publication_type") == "other_ic")
    total_ics = prj_count + peer_reviewed_count + other_ic_count

    # Count activities
    activity_count = len(activities)

    # Calculate reductions from exemptions (only from non-full-exemption types)
    total_ic_reduction = 0
    total_prj_reduction = 0
    total_activity_reduction = 0
    exemption_notes = []
    is_programme_leader = False

    for exemption in exemptions:
        ex_type = exemption.exemption_type
        # Skip full exemption types for reductions
        if ex_type.grants_full_exemption:
            continue

        # Check if this is Programme Leader (needs special handling)
        if ex_type.name == "Programme Leader":
            is_programme_leader = True

        if ex_type.reduces_ic_requirement:
            total_ic_reduction += ex_type.ic_reduction
        if ex_type.reduces_prj_requirement:
            total_prj_reduction += ex_type.prj_reduction
        if ex_type.reduces_activity_requirement:
            total_activity_reduction += ex_type.activity_reduction
        exemption_notes.append(ex_type.name)

    requirements = {}
    met = True
    warnings = []

    # If full exemption applies, requirements are automatically met
    if full_exemption:
        requirements = {
            "description": f"Full exemption: {full_exemption_reason}",
            "exemption_applied": True,
        }
        met = True
    elif category == FacultyCategory.SA:
        # SA: 6 ICs, at least 3 PRJ articles (with reductions)
        # Programme Leader: 4 ICs, 1 PRJ
        ic_required = max(0, 6 - total_ic_reduction)
        prj_required = max(0, 3 - total_prj_reduction)
        if is_programme_leader:
            prj_required = max(1, prj_required)  # Programme Leader needs at least 1 PRJ
        requirements = {
            "total_ics_required": ic_required,
            "prj_required": prj_required,
            "base_ics_required": 6,
            "base_prj_required": 3,
            "description": f"{ic_required} ICs total, at least {prj_required} in peer-reviewed journals"
        }
        if prj_count < prj_required:
            met = False
            warnings.append(f"Need {prj_required - prj_count} more PRJ articles")
        if total_ics < ic_required:
            met = False
            warnings.append(f"Need {ic_required - total_ics} more intellectual contributions")

    elif category == FacultyCategory.PA:
        # PA: 6 professional engagement activities (with reductions)
        # Programme Leader: 3 activities
        activities_required = max(0, 6 - total_activity_reduction)
        requirements = {
            "activities_required": activities_required,
            "base_activities_required": 6,
            "description": f"{activities_required} professional engagement activities"
        }
        if activity_count < activities_required:
            met = False
            warnings.append(f"Need {activities_required - activity_count} more professional activities")

    elif category == FacultyCategory.SP:
        # SP: 5 ICs, at least 1 PRJ article (with reductions)
        # Programme Leader: 3 ICs, 1 PRJ (PRJ stays at 1)
        ic_required = max(0, 5 - total_ic_reduction)
        # For SP, PRJ requirement is always at least 1 (even with Programme Leader)
        prj_required = max(1, 1 - total_prj_reduction) if is_programme_leader else max(0, 1 - total_prj_reduction)
        requirements = {
            "total_ics_required": ic_required,
            "prj_required": prj_required,
            "base_ics_required": 5,
            "base_prj_required": 1,
            "description": f"{ic_required} ICs total, at least {prj_required} in peer-reviewed journal"
        }
        if prj_count < prj_required:
            met = False
            warnings.append(f"Need {prj_required - prj_count} more PRJ articles")
        if total_ics < ic_required:
            met = False
            warnings.append(f"Need {ic_required - total_ics} more intellectual contributions")

    elif category == FacultyCategory.IP:
        # IP: 6 professional engagement activities (with reductions)
        # Programme Leader: 3 activities
        activities_required = max(0, 6 - total_activity_reduction)
        requirements = {
            "activities_required": activities_required,
            "base_activities_required": 6,
            "description": f"{activities_required} professional engagement activities"
        }
        if activity_count < activities_required:
            met = False
            warnings.append(f"Need {activities_required - activity_count} more professional activities")

    # Add exemption info to requirements
    if exemption_notes and not full_exemption:
        requirements["exemptions_applied"] = exemption_notes

    return {
        "category": category.value,
        "requirements": requirements,
        "current": {
            "prj_articles": prj_count,
            "peer_reviewed_other": peer_reviewed_count,
            "other_ics": other_ic_count,
            "total_ics": total_ics,
            "professional_activities": activity_count,
        },
        "requirements_met": met,
        "warnings": warnings,
        "exemptions": [
            {
                "id": e.id,
                "type": e.exemption_type.name,
                "year_from": e.year_from,
                "year_to": e.year_to,
                "in_grace_period": is_in_grace_period(e, reference_year),
            }
            for e in exemptions
        ],
    }


@router.get("/my-status")
async def get_my_qualification_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's qualification status."""
    # Load user with relations including exemptions
    user = (
        db.query(User)
        .options(
            joinedload(User.disciplines).joinedload(UserDiscipline.discipline),
            joinedload(User.highest_degree),
            joinedload(User.exemptions).joinedload(UserExemption.exemption_type),
        )
        .filter(User.uuid == current_user.uuid)
        .first()
    )

    # Get contributions
    contributions_data = await get_my_contributions(
        year_from=REFERENCE_YEAR - 6,
        year_to=REFERENCE_YEAR,
        db=db,
        current_user=current_user,
    )
    contributions = contributions_data.get("contributions", [])

    # Get activities
    activities = await get_my_activities(db=db, current_user=current_user)

    # Calculate status
    status = calculate_qualification_status(user, contributions, activities)

    return {
        "user": {
            "id": user.uuid,
            "name": f"{user.firstname} {user.lastname}",
            "faculty_category": user.faculty_category.value if user.faculty_category else None,
            "is_participating": user.is_participating,
            "highest_degree": user.highest_degree.name if user.highest_degree else None,
            "degree_year": user.degree_year,
            "disciplines": [
                {"shorthand": d.discipline.shorthand, "name": d.discipline.name, "percentage": float(d.percentage)}
                for d in user.disciplines
            ],
        },
        "qualification": status,
        "period": {
            "year_from": REFERENCE_YEAR - 6,
            "year_to": REFERENCE_YEAR,
        },
        "summary": {
            "total_contributions": len(contributions),
            "categorized_contributions": sum(1 for c in contributions if c.get("my_categorization")),
            "total_activities": len(activities),
        },
    }


# ============================================
# Admin: Manage on behalf of researchers
# ============================================

@router.get("/admin/user/{user_id}/contributions")
async def get_user_contributions_admin(
    user_id: int,
    year_from: Optional[int] = Query(default=None),
    year_to: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Get a user's ICs with categorizations. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.researcher_id:
        return {"user": {"id": user.uuid, "name": f"{user.firstname} {user.lastname}"}, "contributions": [], "message": "No researcher ID configured"}

    if not year_from:
        year_from = REFERENCE_YEAR - 6
    if not year_to:
        year_to = REFERENCE_YEAR

    # Fetch from NVA
    try:
        nva_pubs = await nva_service.get_person_publications(
            person_id=user.researcher_id,
            year_from=year_from,
            year_to=year_to,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch from NVA: {str(e)}")

    contributions = []
    for pub in nva_pubs:
        parsed = nva_service.parse_publication(pub)
        nva_id = parsed.get("id")
        if not nva_id:
            continue

        # Get or create IC in our database
        ic = get_or_create_ic(db, nva_id, parsed)

        # Get user's categorization
        user_ic = (
            db.query(UserIntellectualContribution)
            .filter(
                UserIntellectualContribution.user_id == user_id,
                UserIntellectualContribution.ic_id == ic.id,
            )
            .first()
        )

        contributions.append({
            "ic_id": ic.id,
            "nva_id": nva_id,
            "title": parsed.get("title"),
            "year": parsed.get("year"),
            "type": parsed.get("type"),
            "contributors": parsed.get("contributors", []),
            "journal": parsed.get("journal"),
            "publisher": parsed.get("publisher"),
            "nva_url": parsed.get("nva_url"),
            "categorization": {
                "publication_type": user_ic.publication_type.value if user_ic and user_ic.publication_type else None,
                "portfolio_category": user_ic.portfolio_category.value if user_ic and user_ic.portfolio_category else None,
                "societal_impact": user_ic.societal_impact if user_ic else None,
            } if user_ic else None,
        })

    return {
        "user": {"id": user.uuid, "name": f"{user.firstname} {user.lastname}", "researcher_id": user.researcher_id},
        "year_from": year_from,
        "year_to": year_to,
        "total": len(contributions),
        "contributions": contributions,
    }


@router.post("/admin/user/{user_id}/contributions/{nva_id}/categorize")
async def categorize_contribution_admin(
    user_id: int,
    nva_id: str,
    categorization: ICCategorization,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Categorize an IC for a user. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find the IC
    ic = db.query(IntellectualContribution).filter(IntellectualContribution.nva_id == nva_id).first()
    if not ic:
        raise HTTPException(status_code=404, detail="Intellectual contribution not found. Fetch the user's contributions first.")

    # Get or create user's categorization
    user_ic = (
        db.query(UserIntellectualContribution)
        .filter(
            UserIntellectualContribution.user_id == user_id,
            UserIntellectualContribution.ic_id == ic.id,
        )
        .first()
    )

    if not user_ic:
        user_ic = UserIntellectualContribution(
            user_id=user_id,
            ic_id=ic.id,
        )
        db.add(user_ic)

    # Update categorization
    if categorization.publication_type is not None:
        if categorization.publication_type == "":
            user_ic.publication_type = None
        else:
            user_ic.publication_type = PublicationType(categorization.publication_type)

    if categorization.portfolio_category is not None:
        if categorization.portfolio_category == "":
            user_ic.portfolio_category = None
        else:
            user_ic.portfolio_category = PortfolioCategory(categorization.portfolio_category)

    if categorization.societal_impact is not None:
        user_ic.societal_impact = categorization.societal_impact if categorization.societal_impact else None

    db.commit()

    return {"message": "Categorization saved"}


@router.get("/admin/user/{user_id}/activities")
async def get_user_activities_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Get a user's professional activities. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    activities = (
        db.query(ProfessionalActivity)
        .filter(ProfessionalActivity.user_id == user_id)
        .order_by(ProfessionalActivity.year.desc())
        .all()
    )

    return {
        "user": {"id": user.uuid, "name": f"{user.firstname} {user.lastname}"},
        "activities": [
            {
                "id": a.id,
                "year": a.year,
                "activity_type": a.activity_type,
                "description": a.description,
            }
            for a in activities
        ],
    }


@router.post("/admin/user/{user_id}/activities")
async def add_user_activity_admin(
    user_id: int,
    activity: ProfessionalActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Add a professional activity for a user. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pa = ProfessionalActivity(
        user_id=user_id,
        year=activity.year,
        activity_type=activity.activity_type,
        description=activity.description,
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)

    return {
        "id": pa.id,
        "year": pa.year,
        "activity_type": pa.activity_type,
        "description": pa.description,
    }


@router.delete("/admin/user/{user_id}/activities/{activity_id}")
async def delete_user_activity_admin(
    user_id: int,
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Delete a professional activity for a user. Admin only."""
    deleted = (
        db.query(ProfessionalActivity)
        .filter(
            ProfessionalActivity.id == activity_id,
            ProfessionalActivity.user_id == user_id,
        )
        .delete()
    )
    db.commit()

    if deleted:
        return {"message": "Activity deleted"}
    raise HTTPException(status_code=404, detail="Activity not found")


# ============================================
# Dean/Admin View - All Faculty Status
# ============================================

@router.get("/faculty-overview")
async def get_faculty_overview(
    year_from: Optional[int] = Query(default=None, description="Start year of evaluation period"),
    year_to: Optional[int] = Query(default=None, description="End year of evaluation period"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Get qualification overview for all faculty. Admin/Dean only."""
    # Use provided years or defaults
    if not year_to:
        year_to = REFERENCE_YEAR
    if not year_from:
        year_from = year_to - 5  # 6 year window (inclusive)

    # Get all active users with faculty category
    faculty = (
        db.query(User)
        .options(
            joinedload(User.disciplines).joinedload(UserDiscipline.discipline),
            joinedload(User.highest_degree),
            joinedload(User.intellectual_contributions).joinedload(UserIntellectualContribution.contribution),
            joinedload(User.professional_activities),
            joinedload(User.exemptions).joinedload(UserExemption.exemption_type),
        )
        .filter(User.active == True, User.faculty_category.isnot(None))
        .order_by(User.lastname, User.firstname)
        .all()
    )

    overview = []
    for user in faculty:
        # Calculate IC counts from stored categorizations
        prj_count = 0
        peer_reviewed_count = 0
        other_ic_count = 0

        for uic in user.intellectual_contributions:
            if uic.contribution.year and year_from <= uic.contribution.year <= year_to:
                if uic.publication_type == PublicationType.prj_article:
                    prj_count += 1
                elif uic.publication_type == PublicationType.peer_reviewed_other:
                    peer_reviewed_count += 1
                elif uic.publication_type == PublicationType.other_ic:
                    other_ic_count += 1

        total_ics = prj_count + peer_reviewed_count + other_ic_count

        # Count activities in period
        activity_count = sum(
            1 for a in user.professional_activities
            if year_from <= a.year <= year_to
        )

        # Get active exemptions
        active_exemptions = get_active_exemptions(user, year_from, year_to)

        # Check for full exemption (including grace periods)
        has_full_exemption = False
        is_programme_leader = False
        for exemption in active_exemptions:
            ex_type = exemption.exemption_type
            if ex_type.name == "Programme Leader":
                is_programme_leader = True
            if ex_type.grants_full_exemption:
                if ex_type.years_after_degree and user.degree_year:
                    years_since = year_to - user.degree_year
                    if years_since <= ex_type.years_after_degree:
                        has_full_exemption = True
                        break
                elif not ex_type.years_after_degree:
                    # Check if still serving or in grace period
                    if is_in_grace_period(exemption, year_to):
                        has_full_exemption = True
                        break
                    elif not exemption.year_to or exemption.year_to >= year_to:
                        has_full_exemption = True
                        break

        # Calculate reductions from exemptions (skip full exemption types)
        total_ic_reduction = sum(e.exemption_type.ic_reduction for e in active_exemptions if e.exemption_type.reduces_ic_requirement and not e.exemption_type.grants_full_exemption)
        total_prj_reduction = sum(e.exemption_type.prj_reduction for e in active_exemptions if e.exemption_type.reduces_prj_requirement and not e.exemption_type.grants_full_exemption)
        total_activity_reduction = sum(e.exemption_type.activity_reduction for e in active_exemptions if e.exemption_type.reduces_activity_requirement and not e.exemption_type.grants_full_exemption)

        # Determine if requirements are met (considering exemptions)
        category = user.faculty_category
        met = True
        if has_full_exemption:
            met = True
        elif category == FacultyCategory.SA:
            prj_required = max(0, 3 - total_prj_reduction)
            if is_programme_leader:
                prj_required = max(1, prj_required)  # Programme Leader needs at least 1 PRJ
            ic_required = max(0, 6 - total_ic_reduction)
            met = prj_count >= prj_required and total_ics >= ic_required
        elif category == FacultyCategory.PA:
            activities_required = max(0, 6 - total_activity_reduction)
            met = activity_count >= activities_required
        elif category == FacultyCategory.SP:
            prj_required = 1 if is_programme_leader else max(0, 1 - total_prj_reduction)  # SP always needs at least 1 PRJ with Programme Leader
            ic_required = max(0, 5 - total_ic_reduction)
            met = prj_count >= prj_required and total_ics >= ic_required
        elif category == FacultyCategory.IP:
            activities_required = max(0, 6 - total_activity_reduction)
            met = activity_count >= activities_required

        overview.append({
            "id": user.uuid,
            "name": f"{user.firstname} {user.lastname}",
            "email": user.email,
            "faculty_category": category.value if category else None,
            "is_participating": user.is_participating,
            "employment_percentage": float(user.employment_percentage) if user.employment_percentage else 100.0,
            "highest_degree": user.highest_degree.name if user.highest_degree else None,
            "degree_year": user.degree_year,
            "disciplines": [
                {"shorthand": d.discipline.shorthand, "percentage": float(d.percentage)}
                for d in user.disciplines
            ],
            "ics": {
                "prj_articles": prj_count,
                "peer_reviewed_other": peer_reviewed_count,
                "other_ics": other_ic_count,
                "total": total_ics,
            },
            "activities": activity_count,
            "requirements_met": met,
            "has_exemptions": len(active_exemptions) > 0,
            "exemption_count": len(active_exemptions),
        })

    # Summary statistics
    total_faculty = len(overview)
    meeting_requirements = sum(1 for f in overview if f["requirements_met"])

    by_category = {}
    for f in overview:
        cat = f["faculty_category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "meeting": 0}
        by_category[cat]["total"] += 1
        if f["requirements_met"]:
            by_category[cat]["meeting"] += 1

    return {
        "period": {
            "year_from": year_from,
            "year_to": year_to,
        },
        "summary": {
            "total_faculty": total_faculty,
            "meeting_requirements": meeting_requirements,
            "not_meeting": total_faculty - meeting_requirements,
            "by_category": by_category,
        },
        "faculty": overview,
    }


# ============================================
# Researcher Timeline View
# ============================================

@router.get("/admin/user/{user_id}/timeline")
async def get_researcher_timeline(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """
    Get a researcher's qualifying activities timeline.
    Shows ICs and activities by year to visualize qualification status over time.
    """
    user = (
        db.query(User)
        .options(
            joinedload(User.disciplines).joinedload(UserDiscipline.discipline),
            joinedload(User.highest_degree),
            joinedload(User.intellectual_contributions).joinedload(UserIntellectualContribution.contribution),
            joinedload(User.professional_activities),
            joinedload(User.exemptions).joinedload(UserExemption.exemption_type),
        )
        .filter(User.uuid == user_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Collect all ICs with their years and categorizations
    ics_by_year = {}
    for uic in user.intellectual_contributions:
        year = uic.contribution.year
        if not year:
            continue
        if year not in ics_by_year:
            ics_by_year[year] = []
        ics_by_year[year].append({
            "id": uic.contribution.id,
            "nva_id": uic.contribution.nva_id,
            "title": uic.contribution.title,
            "publication_type": uic.publication_type.value if uic.publication_type else None,
            "portfolio_category": uic.portfolio_category.value if uic.portfolio_category else None,
            "is_prj": uic.publication_type == PublicationType.prj_article if uic.publication_type else False,
        })

    # Collect activities by year
    activities_by_year = {}
    for activity in user.professional_activities:
        year = activity.year
        if year not in activities_by_year:
            activities_by_year[year] = []
        activities_by_year[year].append({
            "id": activity.id,
            "activity_type": activity.activity_type,
            "description": activity.description,
        })

    # Determine year range (all years with any activity, plus current year context)
    all_years = set(ics_by_year.keys()) | set(activities_by_year.keys())
    if not all_years:
        all_years = {REFERENCE_YEAR}
    min_year = min(all_years)
    max_year = max(max(all_years), REFERENCE_YEAR)

    # Build timeline data for each year
    timeline = []
    for year in range(min_year, max_year + 1):
        year_ics = ics_by_year.get(year, [])
        year_activities = activities_by_year.get(year, [])

        prj_count = sum(1 for ic in year_ics if ic.get("is_prj"))
        other_ic_count = len(year_ics) - prj_count

        timeline.append({
            "year": year,
            "ics": year_ics,
            "ic_count": len(year_ics),
            "prj_count": prj_count,
            "other_ic_count": other_ic_count,
            "activities": year_activities,
            "activity_count": len(year_activities),
        })

    # Calculate rolling 6-year windows starting from various years
    # This helps identify when someone might fall out of qualification
    rolling_windows = []
    for end_year in range(max(min_year + 5, REFERENCE_YEAR - 2), max_year + 3):
        start_year = end_year - 5  # 6-year window

        window_prj = 0
        window_ics = 0
        window_activities = 0

        for year in range(start_year, end_year + 1):
            year_data = ics_by_year.get(year, [])
            window_prj += sum(1 for ic in year_data if ic.get("is_prj"))
            window_ics += len(year_data)
            window_activities += len(activities_by_year.get(year, []))

        # Get active exemptions for this window
        active_exemptions = get_active_exemptions(user, start_year, end_year)
        has_full_exemption = False
        is_programme_leader = False
        ic_reduction = 0
        prj_reduction = 0
        activity_reduction = 0

        for exemption in active_exemptions:
            ex_type = exemption.exemption_type
            if ex_type.name == "Programme Leader":
                is_programme_leader = True
            if ex_type.grants_full_exemption:
                if ex_type.years_after_degree and user.degree_year:
                    years_since = end_year - user.degree_year
                    if years_since <= ex_type.years_after_degree:
                        has_full_exemption = True
                elif not ex_type.years_after_degree:
                    # Check if still serving or in grace period
                    if is_in_grace_period(exemption, end_year):
                        has_full_exemption = True
                    elif not exemption.year_to or exemption.year_to >= end_year:
                        has_full_exemption = True
            # Only count reductions from non-full-exemption types
            if not ex_type.grants_full_exemption:
                if ex_type.reduces_ic_requirement:
                    ic_reduction += ex_type.ic_reduction
                if ex_type.reduces_prj_requirement:
                    prj_reduction += ex_type.prj_reduction
                if ex_type.reduces_activity_requirement:
                    activity_reduction += ex_type.activity_reduction

        # Check requirements based on faculty category
        category = user.faculty_category
        meets_requirements = True
        status_notes = []

        if has_full_exemption:
            meets_requirements = True
            status_notes.append("Full exemption applies")
        elif category == FacultyCategory.SA:
            prj_required = max(0, 3 - prj_reduction)
            if is_programme_leader:
                prj_required = max(1, prj_required)
            ic_required = max(0, 6 - ic_reduction)
            if window_prj < prj_required:
                meets_requirements = False
                status_notes.append(f"PRJ: {window_prj}/{prj_required}")
            if window_ics < ic_required:
                meets_requirements = False
                status_notes.append(f"IC: {window_ics}/{ic_required}")
        elif category == FacultyCategory.PA:
            activities_required = max(0, 6 - activity_reduction)
            if window_activities < activities_required:
                meets_requirements = False
                status_notes.append(f"Activities: {window_activities}/{activities_required}")
        elif category == FacultyCategory.SP:
            prj_required = 1 if is_programme_leader else max(0, 1 - prj_reduction)
            ic_required = max(0, 5 - ic_reduction)
            if window_prj < prj_required:
                meets_requirements = False
                status_notes.append(f"PRJ: {window_prj}/{prj_required}")
            if window_ics < ic_required:
                meets_requirements = False
                status_notes.append(f"IC: {window_ics}/{ic_required}")
        elif category == FacultyCategory.IP:
            activities_required = max(0, 6 - activity_reduction)
            if window_activities < activities_required:
                meets_requirements = False
                status_notes.append(f"Activities: {window_activities}/{activities_required}")

        rolling_windows.append({
            "period": f"{start_year}-{end_year}",
            "year_from": start_year,
            "year_to": end_year,
            "prj_count": window_prj,
            "total_ics": window_ics,
            "activities": window_activities,
            "meets_requirements": meets_requirements,
            "status_notes": status_notes,
            "is_current": start_year == REFERENCE_YEAR - 5 and end_year == REFERENCE_YEAR,
            "is_future": end_year > REFERENCE_YEAR,
        })

    # Find potential risk periods
    risk_periods = [w for w in rolling_windows if not w["meets_requirements"] and w["is_future"]]

    return {
        "user": {
            "id": user.uuid,
            "name": f"{user.firstname} {user.lastname}",
            "email": user.email,
            "faculty_category": user.faculty_category.value if user.faculty_category else None,
            "highest_degree": user.highest_degree.name if user.highest_degree else None,
            "degree_year": user.degree_year,
            "disciplines": [
                {"shorthand": d.discipline.shorthand, "percentage": float(d.percentage)}
                for d in user.disciplines
            ],
        },
        "exemptions": [
            {
                "id": e.id,
                "type": e.exemption_type.name,
                "year_from": e.year_from,
                "year_to": e.year_to,
                "grants_full_exemption": e.exemption_type.grants_full_exemption,
            }
            for e in user.exemptions
        ],
        "timeline": timeline,
        "rolling_windows": rolling_windows,
        "at_risk": len(risk_periods) > 0,
        "risk_periods": risk_periods,
        "totals": {
            "total_ics": sum(len(y.get("ics", [])) for y in timeline),
            "total_prj": sum(y.get("prj_count", 0) for y in timeline),
            "total_activities": sum(y.get("activity_count", 0) for y in timeline),
        },
    }


# ============================================
# Exemption Types Management (Admin)
# ============================================

@router.get("/exemption-types")
async def get_exemption_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all exemption types."""
    types = db.query(ExemptionType).order_by(ExemptionType.name).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "reduces_ic_requirement": t.reduces_ic_requirement,
            "reduces_prj_requirement": t.reduces_prj_requirement,
            "reduces_activity_requirement": t.reduces_activity_requirement,
            "grants_full_exemption": t.grants_full_exemption,
            "ic_reduction": t.ic_reduction,
            "prj_reduction": t.prj_reduction,
            "activity_reduction": t.activity_reduction,
            "years_after_degree": t.years_after_degree,
            "grace_period_years": t.grace_period_years,
        }
        for t in types
    ]


@router.post("/exemption-types")
async def create_exemption_type(
    data: ExemptionTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean")),
):
    """Create a new exemption type. Admin/Dean only."""
    # Check if name already exists
    existing = db.query(ExemptionType).filter(ExemptionType.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Exemption type with this name already exists")

    exemption_type = ExemptionType(
        name=data.name,
        description=data.description,
        reduces_ic_requirement=data.reduces_ic_requirement,
        reduces_prj_requirement=data.reduces_prj_requirement,
        reduces_activity_requirement=data.reduces_activity_requirement,
        grants_full_exemption=data.grants_full_exemption,
        ic_reduction=data.ic_reduction,
        prj_reduction=data.prj_reduction,
        activity_reduction=data.activity_reduction,
        years_after_degree=data.years_after_degree,
    )
    db.add(exemption_type)
    db.commit()
    db.refresh(exemption_type)

    return {"id": exemption_type.id, "name": exemption_type.name, "message": "Exemption type created"}


@router.put("/exemption-types/{type_id}")
async def update_exemption_type(
    type_id: int,
    data: ExemptionTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean")),
):
    """Update an exemption type. Admin/Dean only."""
    exemption_type = db.query(ExemptionType).filter(ExemptionType.id == type_id).first()
    if not exemption_type:
        raise HTTPException(status_code=404, detail="Exemption type not found")

    # Check if new name conflicts with another type
    existing = db.query(ExemptionType).filter(
        ExemptionType.name == data.name,
        ExemptionType.id != type_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Another exemption type with this name already exists")

    exemption_type.name = data.name
    exemption_type.description = data.description
    exemption_type.reduces_ic_requirement = data.reduces_ic_requirement
    exemption_type.reduces_prj_requirement = data.reduces_prj_requirement
    exemption_type.reduces_activity_requirement = data.reduces_activity_requirement
    exemption_type.grants_full_exemption = data.grants_full_exemption
    exemption_type.ic_reduction = data.ic_reduction
    exemption_type.prj_reduction = data.prj_reduction
    exemption_type.activity_reduction = data.activity_reduction
    exemption_type.years_after_degree = data.years_after_degree

    db.commit()
    return {"message": "Exemption type updated"}


@router.delete("/exemption-types/{type_id}")
async def delete_exemption_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean")),
):
    """Delete an exemption type. Admin/Dean only."""
    deleted = db.query(ExemptionType).filter(ExemptionType.id == type_id).delete()
    db.commit()
    if deleted:
        return {"message": "Exemption type deleted"}
    raise HTTPException(status_code=404, detail="Exemption type not found")


# ============================================
# User Exemptions Management (Admin)
# ============================================

@router.get("/admin/user/{user_id}/exemptions")
async def get_user_exemptions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Get all exemptions for a user. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    exemptions = (
        db.query(UserExemption)
        .options(joinedload(UserExemption.exemption_type), joinedload(UserExemption.approver))
        .filter(UserExemption.user_id == user_id)
        .order_by(UserExemption.year_from.desc())
        .all()
    )

    return {
        "user": {"id": user.uuid, "name": f"{user.firstname} {user.lastname}"},
        "exemptions": [
            {
                "id": e.id,
                "exemption_type": {
                    "id": e.exemption_type.id,
                    "name": e.exemption_type.name,
                    "description": e.exemption_type.description,
                    "grants_full_exemption": e.exemption_type.grants_full_exemption,
                },
                "year_from": e.year_from,
                "year_to": e.year_to,
                "notes": e.notes,
                "approved_by": f"{e.approver.firstname} {e.approver.lastname}" if e.approver else None,
            }
            for e in exemptions
        ],
    }


@router.post("/admin/user/{user_id}/exemptions")
async def add_user_exemption(
    user_id: int,
    data: UserExemptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Add an exemption to a user. Admin only."""
    user = db.query(User).filter(User.uuid == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    exemption_type = db.query(ExemptionType).filter(ExemptionType.id == data.exemption_type_id).first()
    if not exemption_type:
        raise HTTPException(status_code=404, detail="Exemption type not found")

    exemption = UserExemption(
        user_id=user_id,
        exemption_type_id=data.exemption_type_id,
        year_from=data.year_from,
        year_to=data.year_to,
        notes=data.notes,
        approved_by=current_user.uuid,
    )
    db.add(exemption)
    db.commit()
    db.refresh(exemption)

    return {
        "id": exemption.id,
        "exemption_type": exemption_type.name,
        "year_from": exemption.year_from,
        "year_to": exemption.year_to,
        "message": "Exemption added",
    }


@router.put("/admin/user/{user_id}/exemptions/{exemption_id}")
async def update_user_exemption(
    user_id: int,
    exemption_id: int,
    data: UserExemptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Update a user's exemption. Admin only."""
    exemption = (
        db.query(UserExemption)
        .filter(UserExemption.id == exemption_id, UserExemption.user_id == user_id)
        .first()
    )
    if not exemption:
        raise HTTPException(status_code=404, detail="Exemption not found")

    exemption.exemption_type_id = data.exemption_type_id
    exemption.year_from = data.year_from
    exemption.year_to = data.year_to
    exemption.notes = data.notes
    db.commit()

    return {"message": "Exemption updated"}


@router.delete("/admin/user/{user_id}/exemptions/{exemption_id}")
async def delete_user_exemption(
    user_id: int,
    exemption_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin", "dean", "vice_dean")),
):
    """Delete a user's exemption. Admin only."""
    deleted = (
        db.query(UserExemption)
        .filter(UserExemption.id == exemption_id, UserExemption.user_id == user_id)
        .delete()
    )
    db.commit()
    if deleted:
        return {"message": "Exemption deleted"}
    raise HTTPException(status_code=404, detail="Exemption not found")
