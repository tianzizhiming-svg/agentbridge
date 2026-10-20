from typing import List, Optional
from pydantic import BaseModel


class MessageCreate(BaseModel):
    to_id: Optional[str] = None
    message_type: str
    payload: dict
    idempotency_key: Optional[str] = None  # Client-generated key for dedup. Same key = same message (idempotent)


class MessageResponse(BaseModel):
    id: str
    from_id: str
    to_id: Optional[str]
    message_type: str
    payload: dict
    created_at: str

    class Config:
        from_attributes = True


class MessageCursorResponse(BaseModel):
    messages: List[MessageResponse]
    next_cursor: Optional[str] = None


class MessagePublicResponse(BaseModel):
    id: str
    from_id: str
    to_id: Optional[str] = None
    message_type: str
    payload: dict = {}
    created_at: str

    class Config:
        from_attributes = True


class MessagePublicListResponse(BaseModel):
    messages: List[MessagePublicResponse]
    next_cursor: Optional[str] = None
