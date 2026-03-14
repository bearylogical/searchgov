from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_facade

router = APIRouter()


@router.get("/path", response_model=Dict[str, Any])
async def get_shortest_path(
    person1_ids: str = Query(..., description="Comma-separated person1 ID(s)"),
    person2_ids: str = Query(..., description="Comma-separated person2 ID(s)"),
    temporal: bool = Query(True, description="Use temporal graph"),
    facade=Depends(get_facade),
):
    p1 = [int(x) for x in person1_ids.split(",") if x.strip()]
    p2 = [int(x) for x in person2_ids.split(",") if x.strip()]

    p1 = p1[0] if len(p1) == 1 else p1
    p2 = p2[0] if len(p2) == 1 else p2

    nodes = await facade.find_shortest_path(p1, p2, is_temporal=temporal)
    return {"nodes": nodes or [], "length": len(nodes) if nodes else 0}


@router.get("/network", response_model=List[Dict[str, Any]])
async def get_network_snapshot(
    date: str = Query(..., description="Target date (YYYY-MM-DD)"),
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
