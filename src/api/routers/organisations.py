import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_facade

router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: str, param: str) -> str:
    if not _DATE_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"{param} must be YYYY-MM-DD, got: {value!r}",
        )
    return value


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
    _validate_date(date, "date")
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
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    return await facade.get_org_descendants_diff_between_dates(
        org_id, start_date, end_date
    )
