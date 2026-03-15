import re
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

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
    date: Optional[str] = Query(
        None, description="Target date (YYYY-MM-DD); defaults to today"
    ),
    facade=Depends(get_facade),
):
    resolved = _validate_date(date, "date") if date else str(dt_date.today())
    return await facade.get_active_descendants(org_id, resolved)


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


@router.get("/{org_id}/headcount", response_model=Dict[str, int])
async def get_org_headcount(
    org_id: int,
    date: Optional[str] = Query(
        None, description="Target date (YYYY-MM-DD); defaults to today"
    ),
    facade=Depends(get_facade),
):
    """Count distinct employees active in the org subtree on a given date."""
    resolved = _validate_date(date, "date") if date else str(dt_date.today())
    headcount = await facade.get_org_headcount(org_id, resolved)
    return {"headcount": headcount, "date": resolved}


@router.get("/{org_id}/root", response_model=Dict[str, Any])
async def get_org_root(
    org_id: int,
    facade=Depends(get_facade),
):
    """Return the root (ministry-level) organisation for any org ID."""
    return await facade.get_org_root(org_id)


@router.get("/{org_id}", response_model=Dict[str, Any])
async def get_org_by_id(
    org_id: int,
    facade=Depends(get_facade),
):
    """Fetch a single organisation by its ID."""
    return await facade.get_org_by_id(org_id)
