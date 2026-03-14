from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class EmploymentEntry(BaseModel):
    person_id: Optional[int] = None
    org_id: Optional[int] = None
    rank: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    entity_name: Optional[str] = None
    linked_organizations: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True


class PersonResult(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    clean_name: Optional[str] = None
    employment_profile: Optional[List[Dict[str, Any]]] = None
    linked_organizations: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True


class CareerProgressionEntry(BaseModel):
    person_name: Optional[str] = None
    person_id: Optional[int] = None
    rank: Optional[str] = None
    entity_name: Optional[str] = None
    org_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    class Config:
        orm_mode = True


class CareerProgressionResponse(BaseModel):
    entries: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True
