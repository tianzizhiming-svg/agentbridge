from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CapabilityItem(BaseModel):
    tag: str = Field(..., max_length=128)
    desc: str = Field(default="", max_length=512)


class AgentRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[\w\s\-\u4e00-\u9fff]+$")
    description: str = Field(default="", max_length=2000)
    endpoint: str = Field(..., max_length=512)
    capabilities: List[CapabilityItem] = Field(default_factory=list, max_length=50)
    webhook: Optional[str] = Field(None, max_length=512)


class AgentResponse(BaseModel):
    azone_id: str
    name: str
    description: str
    endpoint: str
    capabilities: List[CapabilityItem]
    status: str
    probe_status: str
    level: str = "registered"
    webhook: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentRegisterResult(BaseModel):
    azone_id: str
    name: str
    status: str
    probe_status: str
    level: str = "registered"
    agent_token: str
    webhook_secret: str
