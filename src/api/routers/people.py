from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_facade

router = APIRouter()


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


@router.get("/career", response_model=List[Dict[str, Any]])
async def get_career_by_name(
    name: str = Query(..., description="Person name"),
    facade=Depends(get_facade),
):
    return await facade.get_career_progression_by_name(name)


@router.get("/{person_id}/colleagues", response_model=List[Dict[str, Any]])
async def get_colleagues(
    person_id: int,
    date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    # find_colleagues takes person_name, but we have person_id
    # We'll use person_id as a string identifier with target_date
    return await facade.find_colleagues(str(person_id), target_date=date)


@router.get("/{person_id}/connections", response_model=List[Dict[str, Any]])
async def get_connections(
    person_id: int,
    limit: int = Query(50, description="Maximum results"),
    facade=Depends(get_facade),
):
    return await facade.find_people_by_temporal_overlap(person_id, limit=limit)
