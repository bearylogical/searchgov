from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_facade

router = APIRouter()


@router.get("/path", response_model=Dict[str, Any])
async def get_shortest_path(
    from_id: int = Query(..., description="Source person ID"),
    to_id: int = Query(..., description="Target person ID"),
    temporal: bool = Query(True, description="Use temporal graph"),
    facade=Depends(get_facade),
):
    nodes = await facade.find_shortest_path(
        from_id, to_id, is_temporal=temporal
    )
    return {"nodes": nodes or [], "length": len(nodes) if nodes else 0}


@router.get("/network", response_model=List[Dict[str, Any]])
async def get_network_snapshot(
    date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    return await facade.get_network_snapshot(date)


@router.get("/centrality", response_model=Dict[str, Any])
async def get_centrality(
    date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    facade=Depends(get_facade),
):
    metrics = await facade.calculate_centrality_metrics(date)
    return {"date": date, "metrics": metrics or {}}
