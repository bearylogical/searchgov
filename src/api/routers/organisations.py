from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_facade

router = APIRouter()


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_organisations(
    q: str = Query(..., description="Organisation name query"),
    fuzzy: bool = Query(True, description="Use fuzzy matching"),
    facade=Depends(get_facade),
):
    return await facade.find_organisation_by_name(q, is_fuzzy=fuzzy)


@router.get("/roots", response_model=List[Dict[str, Any]])
async def get_root_organisations(
    facade=Depends(get_facade),
):
    return await facade.get_base_organizations()


@router.get("/{org_id}/tree", response_model=List[Dict[str, Any]])
async def get_org_tree(
    org_id: int,
    date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    return await facade.get_active_descendants(org_id, date)


@router.get("/{org_id}/timeline", response_model=List[str])
async def get_org_timeline(
    org_id: int,
    facade=Depends(get_facade),
):
    return await facade.get_org_timeline_dates(org_id)


@router.get("/{org_id}/diff", response_model=List[Dict[str, Any]])
async def get_org_diff(
    org_id: int,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    return await facade.get_org_descendants_diff_between_dates(
        org_id, start_date, end_date
    )
