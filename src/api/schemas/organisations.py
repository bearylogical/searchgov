from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class OrgResult(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    department: Optional[str] = None
    url: Optional[str] = None
    parent_org_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    sim_score: Optional[float] = None

    class Config:
        orm_mode = True


class OrgDiffEntry(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None  # added | removed | unchanged

    class Config:
        orm_mode = True


class OrgTreeResponse(BaseModel):
    org_id: int
    date: str
    descendants: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True
