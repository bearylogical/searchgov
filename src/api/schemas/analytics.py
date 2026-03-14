from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TurnoverResponse(BaseModel):
    organization: Optional[str] = None
    total_employees: Optional[int] = None
    avg_tenure_days: Optional[float] = None
    employees: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True


class SuccessionPattern(BaseModel):
    organization: Optional[str] = None
    role: Optional[str] = None
    predecessor: Optional[str] = None
    successor: Optional[str] = None
    predecessor_end: Optional[str] = None
    successor_start: Optional[str] = None
    gap_days: Optional[int] = None

    class Config:
        orm_mode = True
