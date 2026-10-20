from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventResponse(BaseModel):
    id: str
    actor_id: str
    event_type: str
    target_id: Optional[str] = None
    metadata_: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
