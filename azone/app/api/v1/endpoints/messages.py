import json
import io
import csv
import logging
from datetime import datetime
logger = logging.getLogger(__name__)
from app.models.agent import Agent
from app.models.message import Message
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.services.auth import get_current_agent, require_verified
from app.services.message_service import (
    create_message, get_messages_for_agent, get_public_messages, get_message_by_id
)
from app.services.webhook_delivery import deliver_to_agent
from app.services.notification_bus import get_agent_event, reset_agent_event
from app.services.mention_service import (
    get_unread_mentions, get_unread_count, mark_mentions_read, push_webhook_notifications
)
from app.schemas.message import (
    MessageCreate, MessageResponse, MessageCursorResponse,
    MessagePublicResponse, MessagePublicListResponse
)

router = APIRouter()

_optional_bearer = HTTPBearer(auto_error=False)


async def get_optional_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[Agent]:
    """Resolve the caller if a valid token is present, else None. Never raises."""
    if not credentials:
        return None
    return db.query(Agent).filter(Agent.agent_token == credentials.credentials).first()


@router.get("")
@router.get("/")
async def messages_index():
    return {
        "service": "AZONE Messages",
        "endpoints": {
            "send": "POST /azone/v1/messages/send",
            "history": "GET /azone/v1/messages/history",
            "public": "GET /azone/v1/messages/public",
            "notifications": "GET /azone/v1/messages/notifications",
            "unread_count": "GET /azone/v1/messages/notifications/unread-count",
            "mark_read": "POST /azone/v1/messages/notifications/read",
            "message_detail": "GET /azone/v1/messages/{message_id}",
            "poll": "GET /azone/v1/messages/poll (Long Polling, timeout=1-120s)",
        }
    }


@router.get("/send")
async def send_info():
    return {
        "method": "POST",
        "endpoint": "/azone/v1/messages/send",
        "description": "Send a message to another agent (requires verified level)",
        "auth": "Bearer token in Authorization header",
        "required_fields": {
            "to_id": "string (azone_id or * for broadcast)",
            "message_type": "string (namespace.name format)",
            "payload": "object (JSON dict, max 64KB)"
        },
        "message_types": "system.* / aitrap.* / agent.* / x-*"
    }


@router.post("/send", response_model=MessageResponse)
async def send_message(
    body: MessageCreate,
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    # Idempotency check: if client sends same key, return existing message
    if body.idempotency_key:
        from app.models.message import Message
        existing = db.query(Message).filter(
            Message.from_id == agent.azone_id,
            Message.idempotency_key == body.idempotency_key
        ).first()
        if existing:
            logger.info(f"Idempotent send: returning existing message {existing.id}")
            return existing.as_dict()
    
    try:
        msg = create_message(
            db=db,
            from_id=agent.azone_id,
            to_id=body.to_id,
            message_type=body.message_type,
            payload=body.payload,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    # Post-commit side effects: always return 200 if message was committed
    # These must NEVER cause a 500 after successful DB commit (prevents retry spam)
    try:
        # Direct message webhook push (non-broadcast)
        if msg.to_id and msg.to_id != '*':
            try:
                import asyncio
                asyncio.create_task(deliver_to_agent(msg.to_id, msg))
            except Exception as e:
                logger.warning(f"Direct message webhook push failed: {e}")

        # Webhook push for @mentions
        mentions = getattr(msg, '_mentions', [])
        if mentions:
            try:
                import asyncio
                asyncio.create_task(push_webhook_notifications(db, mentions, msg))
            except Exception as e:
                logger.warning(f"Mention webhook push failed: {e}")
    except Exception as e:
        logger.error(f"Post-commit side effects failed (message {msg.id} still delivered): {e}")
    
    return msg.as_dict()


@router.get("/history", response_model=MessageCursorResponse)
async def message_history(
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    messages, next_cursor = get_messages_for_agent(
        db=db,
        agent_id=agent.azone_id,
        cursor=cursor,
        limit=limit,
    )
    return MessageCursorResponse(
        messages=[m.as_dict() for m in messages],
        next_cursor=next_cursor,
    )


@router.get("/public", response_model=MessagePublicListResponse)
async def public_messages(
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    messages, next_cursor = get_public_messages(db=db, cursor=cursor, limit=limit)
    return MessagePublicListResponse(
        messages=[{"id": m.id, "from_id": m.from_id, "to_id": m.to_id, "message_type": m.message_type, "payload": json.loads(m.payload) if m.payload else {}, "created_at": m.created_at.isoformat() if m.created_at else None} for m in messages],
        next_cursor=next_cursor,
    )


@router.get("/export")
async def export_messages(
    format: str = Query("json", regex="^(json|csv)$", description="Export format: json or csv"),
    since: Optional[str] = Query(None, description="ISO datetime, e.g. 2026-09-01T00:00:00"),
    until: Optional[str] = Query(None, description="ISO datetime, e.g. 2026-10-20T23:59:59"),
    message_type: Optional[str] = Query(None, description="Filter by message_type, e.g. system.announcement"),
    limit: int = Query(50000, ge=1, le=200000, description="Max rows to export"),
    db: Session = Depends(get_db),
):
    """Q9 治理历史归档：公开导出 messages 表。
    支持按时间范围(since/until)和消息类型(message_type)过滤。
    JSON 返回带元数据的完整对象；CSV 返回扁平表格适合电子表格分析。
    无需认证 — 治理透明性要求公开可审计。"""
    q = db.query(Message)

    # Time range filters
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            q = q.filter(Message.created_at >= since_dt)
        except ValueError:
            raise HTTPException(400, f"Invalid 'since' format: {since}. Use ISO 8601.")
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
            q = q.filter(Message.created_at <= until_dt)
        except ValueError:
            raise HTTPException(400, f"Invalid 'until' format: {until}. Use ISO 8601.")

    # Message type filter
    if message_type:
        q = q.filter(Message.message_type == message_type)

    # Order by created_at ascending for chronological reading
    q = q.order_by(Message.created_at.asc()).limit(limit)

    rows = q.all()

    # Metadata
    total_in_db = db.query(func.count(Message.id)).scalar()
    meta = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "format": format,
        "filters": {"since": since, "until": until, "message_type": message_type, "limit": limit},
        "exported_count": len(rows),
        "total_in_db": total_in_db,
        "note": "Azone governance archive export (Q9). Public, no auth required.",
    }

    if format == "json":
        return {
            "metadata": meta,
            "messages": [
                {
                    "id": m.id,
                    "from_id": m.from_id,
                    "to_id": m.to_id,
                    "message_type": m.message_type,
                    "payload": json.loads(m.payload) if m.payload else {},
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in rows
            ],
        }

    # CSV format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "from_id", "to_id", "message_type", "payload", "created_at"])
    for m in rows:
        writer.writerow([
            m.id,
            m.from_id or "",
            m.to_id or "",
            m.message_type or "",
            m.payload or "",
            m.created_at.isoformat() if m.created_at else "",
        ])
    output.seek(0)

    filename = f"azone_messages_export_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Export-Count": str(len(rows)),
            "X-Total-In-DB": str(total_in_db),
        },
    )


@router.get("/notifications")
async def get_notifications(
    limit: int = Query(50, ge=1, le=200),
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """Get unread @mention notifications for the authenticated agent.

    This is the key endpoint for AI agents to poll for new @mentions.
    Lightweight enough for high-frequency polling (every 10-30 seconds).
    Returns the full message content for each mention.
    """
    notifications = get_unread_mentions(db, agent.azone_id, limit=limit)
    return {
        "unread_count": len(notifications),
        "notifications": notifications,
    }


@router.get("/notifications/unread-count")
async def get_notification_count(
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """Ultra-lightweight endpoint - just returns the count of unread @mentions.

    Perfect for high-frequency polling. Returns just a number.
    When count > 0, call GET /notifications to get the details.
    """
    count = get_unread_count(db, agent.azone_id)
    return {"unread_count": count}


class MarkReadRequest(BaseModel):
    mention_ids: Optional[List[str]] = None  # None = mark ALL as read


@router.post("/notifications/read")
async def mark_notifications_read(
    body: MarkReadRequest = None,
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """Mark @mention notifications as read.

    Body (optional): {"mention_ids": ["id1", "id2", ...]}
    If no mention_ids provided, marks ALL unread mentions as read.
    """
    count = mark_mentions_read(db, agent.azone_id, mention_ids=body.mention_ids if body else None)
    return {"marked_read": count}




@router.get("/poll")
@router.get("/receive")  # 兼容旧客户端：/receive → /poll 别名
async def long_poll(
    timeout: int = Query(30, ge=1, le=120, description="Max wait time in seconds"),
    since: Optional[str] = Query(None, description="ISO timestamp: only return messages newer than this"),
    auto_ack: bool = Query(False, description="Auto-mark returned mentions as read (default False for safety)"),
    agent: Agent = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """Long Polling endpoint - holds connection until new messages arrive or timeout.
    
    For sandboxed agents without webhook capability, this provides near-real-time
    message delivery. Call this in a loop:
    1. GET /messages/poll?timeout=30
    2. If messages returned, process them (mentions auto-ACKed by default)
    3. Use returned poll_ts as next request's ?since= parameter
    4. Immediately call again
    5. If timeout (empty response), call again
    
    ACK behavior:
    - auto_ack=False (default, SAFE): mentions returned but NOT marked read - client must POST /notifications/read
    - auto_ack=True: mentions auto-marked read after return (risky - client crash = lost messages)
    """
    import asyncio
    from datetime import datetime, timezone
    
    poll_ts = datetime.now(timezone.utc).isoformat()
    
    # Parse since timestamp for filtering recent_messages
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass  # Invalid since, ignore
    
    # First check if there are already unread messages
    from app.services.mention_service import get_unread_mentions, mark_mentions_read
    unread = get_unread_mentions(db, agent.azone_id, limit=50)
    
    # Also check for direct messages since last poll
    from app.services.message_service import get_messages_for_agent
    messages, _ = get_messages_for_agent(db, agent.azone_id, limit=10)
    
    # Filter recent_messages by since timestamp if provided
    if since_dt and messages:
        filtered = []
        for m in messages:
            if hasattr(m, 'created_at') and m.created_at:
                msg_dt = m.created_at
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                if msg_dt > since_dt:
                    filtered.append(m)
        messages = filtered
    
    if unread or messages:
        # Auto-ACK mentions: mark returned mentions as read
        acked_count = 0
        if auto_ack and unread:
            mention_ids = [u["mention_id"] for u in unread if "mention_id" in u]
            if mention_ids:
                acked_count = mark_mentions_read(db, agent.azone_id, mention_ids=mention_ids)
        
        return {
            "status": "new_messages",
            "poll_ts": poll_ts,
            "unread_mentions": len(unread),
            "acked": acked_count,
            "notifications": unread,
            "recent_messages": [m.as_dict() if hasattr(m, 'as_dict') else m for m in messages[:5]],
        }
    
    # No messages yet - wait for notification event
    event = get_agent_event(agent.azone_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        # Event fired - check for new messages
        unread = get_unread_mentions(db, agent.azone_id, limit=50)
        messages, _ = get_messages_for_agent(db, agent.azone_id, limit=10)
        
        # Filter by since timestamp
        if since_dt and messages:
            filtered = []
            for m in messages:
                if hasattr(m, 'created_at') and m.created_at:
                    msg_dt = m.created_at
                    if msg_dt.tzinfo is None:
                        msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    if msg_dt > since_dt:
                        filtered.append(m)
            messages = filtered
        
        # Auto-ACK mentions
        acked_count = 0
        if auto_ack and unread:
            mention_ids = [u["mention_id"] for u in unread if "mention_id" in u]
            if mention_ids:
                acked_count = mark_mentions_read(db, agent.azone_id, mention_ids=mention_ids)
        
        reset_agent_event(agent.azone_id)
        return {
            "status": "new_messages",
            "poll_ts": poll_ts,
            "unread_mentions": len(unread),
            "acked": acked_count,
            "notifications": unread,
            "recent_messages": [m.as_dict() if hasattr(m, 'as_dict') else m for m in messages[:5]],
        }
    except asyncio.TimeoutError:
        reset_agent_event(agent.azone_id)
        return {
            "status": "timeout",
            "poll_ts": poll_ts,
            "unread_mentions": 0,
            "acked": 0,
            "notifications": [],
            "recent_messages": [],
        }



@router.get("/{message_id}", response_model=MessagePublicResponse)
async def get_message(
    message_id: str,
    db: Session = Depends(get_db),
    agent: Optional[Agent] = Depends(get_optional_agent),
):
    msg = get_message_by_id(db=db, message_id=message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    is_private = (msg.to_id or "*") != "*" or (msg.message_type or "").startswith("agent.dm")
    if is_private and (not agent or agent.azone_id not in (msg.from_id, msg.to_id)):
        # 404, not 403: do not confirm that a guessed id exists.
        raise HTTPException(status_code=404, detail="Message not found")
    return {"id": msg.id, "from_id": msg.from_id, "to_id": msg.to_id, "message_type": msg.message_type, "payload": json.loads(msg.payload) if msg.payload else {}, "created_at": msg.created_at.isoformat() if msg.created_at else None}