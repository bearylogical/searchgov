from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_facade

router = APIRouter()


@router.get("/turnover", response_model=Dict[str, Any])
async def get_turnover(
    org_name: str = Query(..., description="Organisation name"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    return await facade.analyze_organization_turnover(org_name, start_date, end_date)


@router.get("/succession", response_model=List[Dict[str, Any]])
async def get_succession_patterns(
    max_gap_days: int = Query(90, description="Maximum gap days between successor and predecessor"),
    facade=Depends(get_facade),
):
    return await facade.find_succession_patterns(max_gap_days)
