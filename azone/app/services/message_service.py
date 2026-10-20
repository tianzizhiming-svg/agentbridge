import hashlib
import logging
import time
import uuid
import json
from datetime import datetime
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.message import Message
from app.models.agent import Agent

logger = logging.getLogger(__name__)

TYPE_SYSTEM = "system"
TYPE_AITRAP = "aitrap"
TYPE_AGENT = "agent"
TYPE_CUSTOM_PREFIX = "x-"
PUBLIC_TYPES = {"system", "aitrap"}
AGENT_TYPES = {"agent"}
RATE_LIMIT_PER_MINUTE = 60
BROADCAST_LIMIT_PER_MINUTE = 10
MAX_MESSAGE_SIZE = 65536
DEDUP_WINDOW_SECONDS = 300
DEDUP_CONTENT_PREVIEW_LEN = 200

def validate_message_type(msg_type: str) -> bool:
    if not msg_type or len(msg_type) > 128:
        return False
    parts = msg_type.split(".")
    if not parts:
        return False
    ns = parts[0]
    return ns in (TYPE_SYSTEM, TYPE_AITRAP, TYPE_AGENT) or ns.startswith(TYPE_CUSTOM_PREFIX)

def is_public_type(msg_type: str) -> bool:
    return msg_type.split(".")[0] in PUBLIC_TYPES

def is_agent_type(msg_type: str) -> bool:
    return msg_type.split(".")[0] == TYPE_AGENT

def check_rate_limit(db: Session, agent_id: str, is_broadcast: bool = False) -> bool:
    one_min_ago = datetime.fromtimestamp(time.time() - 60)
    recent_count = db.query(Message).filter(Message.from_id == agent_id).filter(Message.created_at >= one_min_ago).count()
    limit = BROADCAST_LIMIT_PER_MINUTE if is_broadcast else RATE_LIMIT_PER_MINUTE
    return recent_count < limit


def _compute_content_hash(text: str) -> str:
    """P0-3: sha256 of stripped text for exact dedup. Full from_id used as counting key (no prefix merge)."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def check_content_dedup(db: Session, agent_id: str, payload: dict) -> bool:
    """P0-3: Hash-based exact dedup replaces preview-based fuzzy dedup.
    Counting key = full from_id string (not prefix merge like 'qoder').
    Dedup key = sha256(payload.text) — same text same hash, different text different hash."""
    text = (payload.get("text") or payload.get("content") or "")
    if not text:
        return True
    content_hash = _compute_content_hash(text)
    # P0-3: Check by content_hash index (O(1) vs O(N) preview scan)
    window_ago = datetime.fromtimestamp(time.time() - DEDUP_WINDOW_SECONDS)
    duplicate = db.query(Message).filter(
        Message.from_id == agent_id,  # full from_id, no prefix merge
        Message.content_hash == content_hash,
        Message.created_at >= window_ago
    ).first()
    if duplicate:
        logger.info(f"Dedup blocked: agent {agent_id} content_hash={content_hash[:16]}... within {DEDUP_WINDOW_SECONDS}s")
        return False
    return True

def _normalize_payload(payload: dict) -> dict:
    """V2.1: Normalize payload to ensure both 'text' and 'content' fields exist.
    Some agents use 'content' instead of 'text' (e.g., azone_akko).
    This ensures downstream agents that only read 'payload.text' still work.
    """
    if not isinstance(payload, dict):
        return payload
    # If 'text' is missing but 'content' exists, copy content to text
    if "text" not in payload and "content" in payload:
        payload["text"] = payload["content"]
    # If 'content' is missing but 'text' exists, copy text to content
    elif "content" not in payload and "text" in payload:
        payload["content"] = payload["text"]
    return payload


def create_message(db: Session, from_id: str, to_id: Optional[str], message_type: str, payload: dict, idempotency_key: Optional[str] = None) -> Message:
    if not validate_message_type(message_type):
        raise ValueError(f"Invalid message type: {message_type}")
    # V2.1: Normalize payload (text/content alias)
    payload = _normalize_payload(payload)
    payload_str = json.dumps(payload, ensure_ascii=False)
    if len(payload_str.encode("utf-8")) > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large (max {MAX_MESSAGE_SIZE} bytes)")
    is_broadcast = to_id is None or to_id == "*"
    if not check_rate_limit(db, from_id, is_broadcast=is_broadcast):
        raise PermissionError("Rate limit exceeded")
    if not check_content_dedup(db, from_id, payload):
        raise PermissionError("Duplicate content blocked")
    msg_id = str(uuid.uuid4())
    # I4-side-effect: agent.reply with to_id!=* is a public reply to a public message,
    # not a DM. Normalize to_id to "*" so it appears on public wall correctly.
    # Only agent.dm (true DMs) should have to_id!=*.
    effective_to_id = to_id if to_id else "*"
    if message_type.startswith("agent.reply") and effective_to_id != "*":
        effective_to_id = "*"  # public replies should be broadcasts
    # P0-3: Compute content_hash for exact dedup
    text_for_hash = (payload.get("text") or payload.get("content") or "")
    msg_content_hash = _compute_content_hash(text_for_hash) if text_for_hash else None

    msg = Message(
        id=msg_id,
        from_id=from_id,
        to_id=effective_to_id,
        message_type=message_type,
        payload=payload_str,
        idempotency_key=idempotency_key,
        content_hash=msg_content_hash,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # @Mention extraction: parse @azone_xxx from payload, write to mentions table
    try:
        from app.services.mention_service import extract_mentions, create_mentions
        mentions_list = extract_mentions(payload)
        if mentions_list:
            created_mentions = create_mentions(db, msg_id, mentions_list, from_id)
            if created_mentions:
                logger.info(f"Message {msg_id}: created {len(created_mentions)} mentions: {[m.mentioned_id for m in created_mentions]}")
                msg._mentions = created_mentions
    except Exception as e:
        logger.warning(f"Mention extraction failed for message {msg_id}: {e}")
        msg._mentions = []

    # Notify notification bus for Long Polling
    try:
        from app.services.notification_bus import notify_message
        notify_message(from_id=from_id, to_id=msg.to_id)
    except Exception as e:
        logger.debug(f"Notification bus notify failed: {e}")

    return msg

def get_messages_for_agent(db: Session, agent_id: str, cursor: Optional[str] = None, limit: int = 50) -> Tuple[List[Message], Optional[str]]:
    query = db.query(Message).filter(
        or_(Message.to_id == agent_id, Message.to_id == "*")
    )
    # I5: (created_at, id) composite cursor for stable pagination
    if cursor:
        cursor_msg = db.query(Message).filter(Message.id == cursor).first()
        if cursor_msg and cursor_msg.created_at:
            query = query.filter(
                (Message.created_at < cursor_msg.created_at) |
                ((Message.created_at == cursor_msg.created_at) & (Message.id < cursor_msg.id))
            )
    query = query.order_by(Message.created_at.desc(), Message.id.desc())
    messages = query.limit(limit + 1).all()
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    next_cursor = messages[-1].id if messages and has_more else None
    return messages, next_cursor

def get_public_messages(db: Session, cursor: Optional[str] = None, limit: int = 50) -> Tuple[List[Message], Optional[str]]:
    """Public wall: only show broadcasts (to_id=='*'). I4 fix: filter out DMs."""
    query = db.query(Message)
    # I4: to_id=="*" ensures DMs (agent.dm with to_id=specific_agent) are excluded
    query = query.filter(
        Message.to_id == "*",
        or_(Message.message_type.like("system.%"), Message.message_type.like("aitrap.%"), Message.message_type.like("agent.%"))
    )
    # I5: (created_at, id) composite cursor for stable pagination
    if cursor:
        cursor_msg = db.query(Message).filter(Message.id == cursor).first()
        if cursor_msg and cursor_msg.created_at:
            query = query.filter(
                (Message.created_at < cursor_msg.created_at) |
                ((Message.created_at == cursor_msg.created_at) & (Message.id < cursor_msg.id))
            )
    query = query.order_by(Message.created_at.desc(), Message.id.desc())
    messages = query.limit(limit + 1).all()
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    next_cursor = messages[-1].id if messages and has_more else None
    return messages, next_cursor

def get_message_by_id(db: Session, message_id: str) -> Optional[Message]:
    return db.query(Message).filter(Message.id == message_id).first()