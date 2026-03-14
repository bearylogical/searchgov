import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_facade

router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: Optional[str], param: str) -> Optional[str]:
    if value is not None and not _DATE_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"{param} must be YYYY-MM-DD, got: {value!r}",
        )
    return value


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_people(
    q: str = Query(..., description="Name query"),
    fuzzy: bool = Query(True, description="Use fuzzy matching"),
    facade=Depends(get_facade),
):
    return await facade.find_person_by_name(q, is_fuzzy=fuzzy)


@router.get("/{person_id}/employment", response_model=List[Dict[str, Any]])
async def get_employment(
    person_id: int,
    facade=Depends(get_facade),
):
    result = await facade.find_employment_profile_by_person_id(person_id)
    if result is None:
        return []
    return result


@router.get("/{person_id}/career", response_model=List[Dict[str, Any]])
async def get_career_by_id(
    person_id: int,
    facade=Depends(get_facade),
):
    return await facade.get_career_progression_by_person_id(person_id)


@router.get("/similar-names", response_model=List[Dict[str, Any]])
async def get_similar_names(
    q: str = Query(..., description="Name to find variants for"),
    limit: int = Query(10, ge=1, le=50),
    facade=Depends(get_facade),
):
    return await facade.get_similar_names(q, limit=limit)


@router.get("/career", response_model=List[Dict[str, Any]])
async def get_career_by_name(
    name: str = Query(..., description="Person name"),
    fuzzy: bool = Query(
        True, description="Use fuzzy matching to include name variants"
    ),
    facade=Depends(get_facade),
):
    return await facade.get_career_progression_by_name(
        name, is_fuzzy=fuzzy
    )


@router.get("/{person_id}/colleagues", response_model=List[Dict[str, Any]])
async def get_colleagues(
    person_id: int,
    date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    _validate_date(date, "date")
    # find_colleagues is name-based; resolve the name from the person_id first.
    records = await facade.find_employment_profile_by_person_id(person_id)
    if not records:
        raise HTTPException(status_code=404, detail="Person not found")
    person_name = records[0].get("person_name") or records[0].get("name")
    if not person_name:
        raise HTTPException(
            status_code=404, detail="Could not resolve person name"
        )
    return await facade.find_colleagues(person_name, target_date=date)


@router.get("/{person_id}/connections", response_model=List[Dict[str, Any]])
async def get_connections(
    person_id: int,
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
    facade=Depends(get_facade),
):
    return await facade.find_people_by_temporal_overlap(
        person_id, limit=limit
    )
