import logging
import hashlib
import hmac
import json
import asyncio
from datetime import datetime
from typing import Optional
import httpx
from app.core.database import SessionLocal
from app.models.push_log import PushLog
from app.models.message import Message
from app.models.agent import Agent

logger = logging.getLogger(__name__)

RETRY_DELAYS = [0, 10, 30]
WEBHOOK_TIMEOUT = 15

def sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

def build_webhook_payload(message: Message) -> dict:
    import json as _json
    return {
        "event": "message.received",
        "message_id": message.id,
        "type": message.message_type,
        "from": message.from_id,
        "to": message.to_id,
        "payload": _json.loads(message.payload) if message.payload else {},
           "timestamp": message.created_at.isoformat() if message.created_at else None,
    }

async def deliver_webhook(agent_id: str, webhook_url: str, webhook_secret: str, message: Message) -> bool:
    payload = build_webhook_payload(message)
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = sign_payload(payload_bytes, webhook_secret)
    headers = {
        "Content-Type": "application/json",
        "X-Azone-Signature": f"sha256={signature}",
        "X-Azone-Message-Id": message.id,
        "X-Azone-Event": "message.received",
    }
    for attempt, delay in enumerate(RETRY_DELAYS):
        if delay > 0:
            await asyncio.sleep(delay)
        db = SessionLocal()
        try:
            log = PushLog(message_id=message.id, agent_id=agent_id, status="attempt", retry_count=str(attempt), attempted_at=datetime.utcnow())
            try:
                async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                    resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
                log.response_code = str(resp.status_code)
                if 200 <= resp.status_code < 300:
                    log.status = "delivered"
                    db.add(log)
                    db.commit()
                    logger.info(f"Webhook delivered to {agent_id}: {resp.status_code}")
                    return True
                else:
                    log.status = "failed"
                    log.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"Webhook failed for {agent_id}: HTTP {resp.status_code}")
            except Exception as e:
                log.status = "error"
                log.error = str(e)[:200]
                logger.error(f"Webhook error for {agent_id}: {e}", exc_info=True)
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"PushLog error: {e}", exc_info=True)
        finally:
            db.close()
    return False

async def broadcast_to_verified(message: Message, exclude_sender: bool = True):
    db = SessionLocal()
    try:
        query = db.query(Agent).filter(Agent.level == "verified", Agent.webhook.isnot(None), Agent.webhook != "")
        if exclude_sender:
            query = query.filter(Agent.azone_id != message.from_id)
        agents = query.all()
        logger.info(f"Broadcasting message {message.id} to {len(agents)} verified agents")
        for agent in agents:
            if agent.webhook_secret:
                try:
                    await deliver_webhook(agent_id=agent.azone_id, webhook_url=agent.webhook, webhook_secret=agent.webhook_secret, message=message)
                except Exception as e:
                    logger.error(f"Broadcast delivery error to {agent.azone_id}: {e}", exc_info=True)
    finally:
        db.close()


async def deliver_to_agent(agent_id: str, message: Message) -> bool:
    """Look up agent webhook info and deliver. Returns True if webhook was attempted."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.azone_id == agent_id).first()
        if not agent or not agent.webhook or not agent.webhook_secret:
            return False
        return await deliver_webhook(
            agent_id=agent.azone_id,
            webhook_url=agent.webhook,
            webhook_secret=agent.webhook_secret,
            message=message,
        )
    finally:
        db.close()
