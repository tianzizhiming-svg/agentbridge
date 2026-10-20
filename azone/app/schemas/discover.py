from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DiscoverQuery(BaseModel):
    tag: Optional[str] = None
    status: Optional[str] = None
    limit: int = 20
    offset: int = 0


class DiscoverAgentItem(BaseModel):
    azone_id: str
    name: str
    description: str = ""
    endpoint: str
    capabilities: list[dict]
    probe_status: str
    level: str = "registered"
    last_seen_at: Optional[datetime] = None


class DiscoverResponse(BaseModel):
    results: list[DiscoverAgentItem]
    count: int
