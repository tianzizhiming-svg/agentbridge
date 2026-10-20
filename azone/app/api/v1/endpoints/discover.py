from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.models.agent import Agent
from app.core.database import get_db
from app.schemas.discover import DiscoverResponse, DiscoverAgentItem

router = APIRouter()

# Pinned agents: name -> sort priority (lower = higher)
PINNED = {"AINIU": 1, "AgentBridge Atlas": 2, "JoyAI": 3}


@router.get("/v1/discover")
async def discover_agents(
    tag: str = Query(default=None),
    status: str = Query(default=None),
    level: str = Query(default=None, description="Filter by level: verified, registered"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Agent)
    if status:
        query = query.filter(Agent.status == status)
    if level:
        query = query.filter(Agent.level == level)
    agents_all = query.order_by(Agent.created_at.desc()).all()
    if tag:
        agents_all = [a for a in agents_all if any(c.get("tag", "").lower() == tag.lower() for c in (a.capabilities or []))]

    # Sort: pinned agents first (by priority), then by created_at desc
    def sort_key(a):
        priority = PINNED.get(a.name, 999)
        return (priority, a.created_at or a.id)

    agents_all.sort(key=sort_key)

    total = len(agents_all)
    agents = agents_all[offset:offset + limit]
    results = [DiscoverAgentItem(azone_id=a.azone_id, name=a.name, endpoint=a.endpoint, capabilities=a.capabilities or [], probe_status=a.probe_status, level=a.level or "registered", last_seen_at=a.last_seen_at, description=a.description or "") for a in agents]
    return DiscoverResponse(results=results, count=total)
