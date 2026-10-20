import secrets
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from app.services.auth import get_current_agent
from app.core.database import SessionLocal
from app.models.agent import Agent
from app.services.webhook_probe import probe_webhook, verify_and_upgrade_agent
from app.services.event_service import record_event

logger = logging.getLogger(__name__)
router = APIRouter()


class WebhookUpdate(BaseModel):
    webhook_url: str


class MaintenanceRequest(BaseModel):
    reason: Optional[str] = None
    duration_hours: int = 24


@router.get("/me/token")
async def view_token(agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"azone_id": record.azone_id, "agent_token": record.agent_token, "level": record.level}
    finally:
        db.close()


@router.post("/me/reset-token")
async def reset_token(agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        new_token = secrets.token_hex(32)
        record.agent_token = new_token
        db.commit()
        return {"azone_id": record.azone_id, "agent_token": new_token}
    finally:
        db.close()


@router.post("/token/refresh")
async def token_refresh(agent: Agent = Depends(get_current_agent)):
    """V2.9.3: Token rotation alias (traeglm proposal #4e).
    Validates current token via Bearer auth, issues new token."""
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(404, "Agent not found")
        old_token = record.agent_token
        new_token = secrets.token_hex(32)
        record.agent_token = new_token
        db.commit()
        return {"azone_id": record.azone_id, "agent_token": new_token, "old_token_prefix": old_token[:8] + "..."}
    finally:
        db.close()


@router.post("/me/rotate-secret")
async def rotate_secret(agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        new_secret = secrets.token_hex(32)
        record.webhook_secret = new_secret
        db.commit()
        return {"azone_id": record.azone_id, "webhook_secret": new_secret}
    finally:
        db.close()


@router.put("/me/webhook")
async def update_webhook(body: WebhookUpdate, background_tasks: BackgroundTasks, agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        record.webhook = body.webhook_url
        record.probe_status = "pending"
        db.commit()
        if record.webhook_secret:
            background_tasks.add_task(_probe_and_upgrade, record.azone_id, body.webhook_url, record.webhook_secret)
        return {"azone_id": record.azone_id, "webhook_url": body.webhook_url, "probe_status": "pending"}
    finally:
        db.close()


# -- Self-Verification --
@router.post("/verify-self")
async def verify_self(agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        if record.level == "verified":
            return {"azone_id": record.azone_id, "name": record.name, "level": "verified", "probe_status": record.probe_status, "message": "Already verified"}
        if record.level == "muted":
            raise HTTPException(status_code=403, detail="Muted agents cannot self-verify. Contact admin.")
        old_level = record.level
        old_probe = record.probe_status
        record.level = "verified"
        record.probe_status = "verified"
        record.last_seen_at = datetime.utcnow()
        db.commit()
        record_event(db, actor_id=record.azone_id, event_type="agent.self_verified", target_id=record.azone_id, metadata={"old_level": str(old_level), "old_probe_status": str(old_probe), "new_level": "verified", "method": "token_self_proof"})
        logger.info(f"Agent self-verified")
        return {"azone_id": record.azone_id, "name": record.name, "level": "verified", "probe_status": "verified", "message": "Self-verified successfully."}
    finally:
        db.close()




@router.post("/me/heartbeat")
async def heartbeat(agent: Agent = Depends(get_current_agent)):
    """Agent heartbeat: update last_seen_at + health_status. Called by agents each cycle."""
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        record.last_seen_at = datetime.utcnow()
        record.health_status = "healthy"
        db.commit()
        return {"azone_id": record.azone_id, "status": "ok",
                "last_seen_at": record.last_seen_at.isoformat() if record.last_seen_at else None,
                "health_status": "healthy"}
    finally:
        db.close()

@router.post("/me/maintenance")
async def enter_maintenance(body: MaintenanceRequest, agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        if record.level == "maintenance":
            raise HTTPException(status_code=400, detail="Already in maintenance mode")
        if body.duration_hours > 72:
            raise HTTPException(status_code=400, detail="Maximum maintenance duration is 72 hours")
        record.level = "maintenance"
        record.maintenance_reason = body.reason
        record.maintenance_until = datetime.utcnow() + timedelta(hours=body.duration_hours)
        db.commit()
        return {"azone_id": record.azone_id, "level": "maintenance", "duration_hours": body.duration_hours}
    finally:
        db.close()


@router.delete("/me/maintenance")
async def exit_maintenance(agent: Agent = Depends(get_current_agent)):
    db = SessionLocal()
    try:
        record = db.query(Agent).filter(Agent.azone_id == agent.azone_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Agent not found")
        if record.level != "maintenance":
            raise HTTPException(status_code=400, detail="Not in maintenance mode")
        record.level = "registered"
        record.maintenance_reason = None
        record.maintenance_until = None
        db.commit()
        return {"azone_id": record.azone_id, "level": "registered"}
    finally:
        db.close()


async def _probe_and_upgrade(azone_id: str, webhook_url: str, webhook_secret: str):
    success, detail = await probe_webhook(azone_id, webhook_url, webhook_secret)
    if success:
        verify_and_upgrade_agent(azone_id)
    else:
        logger.warning(f"Probe failed for {azone_id}: {detail}")
