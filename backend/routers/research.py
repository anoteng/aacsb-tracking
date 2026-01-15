from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from dependencies import get_current_user, require_role
from models import User
from services.nva import nva_service

router = APIRouter(prefix="/research", tags=["Research"])


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
