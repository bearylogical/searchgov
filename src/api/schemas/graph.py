from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PathNode(BaseModel):
    node_id: Optional[str] = None
    node_type: Optional[str] = None  # person | organization
    name: Optional[str] = None
    employment_profile: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True


class ShortestPathResponse(BaseModel):
    nodes: List[Dict[str, Any]] = []
    length: int = 0

    class Config:
        orm_mode = True


class NetworkSnapshotEntry(BaseModel):
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    rank: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    class Config:
        orm_mode = True


class CentralityResponse(BaseModel):
    date: Optional[str] = None
    metrics: Dict[str, Any] = {}

    class Config:
        orm_mode = True
