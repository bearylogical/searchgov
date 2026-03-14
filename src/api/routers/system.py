from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies import get_facade

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    is_ready = getattr(request.app.state, "facade", None) is not None
    return {"status": "ok" if is_ready else "unavailable"}


@router.get("/stats", response_model=Dict[str, Any])
async def get_stats(facade=Depends(get_facade)):
    return await facade.get_db_stats()


@router.get("/search", response_model=Dict[str, Any])
async def search_any(
    q: str = Query(..., description="Search query"),
    facade=Depends(get_facade),
):
    return await facade.find_any(q)
