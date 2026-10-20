import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.event import Event


# Event types
AGENT_JOINED = "AGENT_JOINED"
AGENT_UPDATED = "AGENT_UPDATED"
AGENT_DISCOVERED = "AGENT_DISCOVERED"
PROBE_SUCCESS = "PROBE_SUCCESS"
PROBE_FAIL = "PROBE_FAIL"
AGENT_ONLINE = "AGENT_ONLINE"
AGENT_OFFLINE = "AGENT_OFFLINE"


def record_event(
    db: Session,
    actor_id: str,
    event_type: str,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> Event:
    """Record an event to the Event Ledger."""
    event = Event(
        id=str(uuid.uuid4()),
        actor_id=actor_id,
        event_type=event_type,
        target_id=target_id,
        metadata_=metadata or {},
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_recent_events(db: Session, limit: int = 50, offset: int = 0) -> list[Event]:
    """Get recent events for Observatory."""
    return (
        db.query(Event)
        .order_by(Event.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
