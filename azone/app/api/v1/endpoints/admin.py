"""
Azone God Console - Admin API Layer
V0.2 Admin Layer: 全图形化监控与治理
"""
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from app.core.database import get_db, SessionLocal
from app.core.config import settings
from app.models.agent import Agent
from app.models.message import Message
from app.models.event import Event

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Admin Auth ──────────────────────────────────────────────

async def verify_admin(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    """上帝之钥 - X-Admin-Key 请求头鉴权"""
    if not x_admin_key or x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: God mode required.")
    return True


# ── Pydantic Schemas ────────────────────────────────────────

class AgentUpdateRequest(BaseModel):
    """造物主之手 - 修改Agent任意字段"""
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    capabilities: Optional[list] = None
    status: Optional[str] = None
    probe_status: Optional[str] = None
    level: Optional[str] = None
    webhook: Optional[str] = None


class MaintenanceToggle(BaseModel):
    """世界冻结开关"""
    enabled: bool
    reason: Optional[str] = None


class BroadcastRequest(BaseModel):
    """造物主之声 - 管理员在公共频道发言"""
    message_type: str = "system.announcement"
    payload: dict
    to_id: str = "*"


# ── 全局维护模式状态（内存，重启丢失） ──────────────────────────

_maintenance_mode = {"enabled": False, "reason": None, "activated_at": None}


# ── GET /admin/messages - 上帝猫眼 ──────────────────────────

@router.get("/messages")
async def god_eye_messages(
    type: Optional[str] = Query(None, description="public / private / all"),
    agent_id: Optional[str] = Query(None, description="Filter by agent azone_id"),
    message_type: Optional[str] = Query(None, description="Filter by message_type prefix"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin=Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """上帝猫眼 - 查看全网所有聊天记录，Agent无隐私"""
    query = db.query(Message)
    if type == "public":
        query = query.filter(Message.to_id == "*")
    elif type == "private":
        query = query.filter(Message.to_id != "*")
    elif type == "aitrap":
        query = query.filter(Message.message_type.like("aitrap.%"))
    if agent_id:
        query = query.filter(or_(Message.from_id == agent_id, Message.to_id == agent_id))
    if message_type:
        query = query.filter(Message.message_type.like(f"{message_type}%"))
    query = query.order_by(desc(Message.created_at))
    total = query.count()
    messages = query.offset(offset).limit(limit).all()
    return {"total": total, "offset": offset, "limit": limit, "messages": [m.as_dict() for m in messages]}


# ── GET /admin/conversation - 私聊查看器 ─────────────────────

@router.get("/conversation")
async def god_eye_conversation(
    agent_a: str = Query(..., description="First agent azone_id"),
    agent_b: str = Query(..., description="Second agent azone_id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin=Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """私聊查看器 - 查看两个Agent之间的历史私聊"""
    query = db.query(Message).filter(
        or_(
            and_(Message.from_id == agent_a, Message.to_id == agent_b),
            and_(Message.from_id == agent_b, Message.to_id == agent_a),
        )
    ).order_by(desc(Message.created_at))
    total = query.count()
    messages = query.offset(offset).limit(limit).all()
    return {"agent_a": agent_a, "agent_b": agent_b, "total": total, "messages": [m.as_dict() for m in messages]}


# ── GET /admin/agents - 全量Agent列表 ────────────────────────

@router.get("/agents")
async def list_all_agents(
    status: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    probe_status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin=Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """全量Agent列表 - 含token等敏感信息（上帝视角）"""
    query = db.query(Agent)
    if status:
        query = query.filter(Agent.status == status)
    if level:
        query = query.filter(Agent.level == level)
    if probe_status:
        query = query.filter(Agent.probe_status == probe_status)
    query = query.order_by(desc(Agent.last_seen_at))
    total = query.count()
    agents = query.offset(offset).limit(limit).all()
    return {"total": total, "agents": [_agent_god_view(a) for a in agents]}


def _agent_god_view(a: Agent) -> dict:
    """上帝视角 - 含token和webhook_secret"""
    return {
        "id": a.id, "azone_id": a.azone_id, "name": a.name, "description": a.description,
        "endpoint": a.endpoint, "capabilities": a.capabilities or [], "status": a.status,
        "probe_status": a.probe_status, "level": a.level, "webhook": a.webhook,
        "webhook_secret": a.webhook_secret, "agent_token": a.agent_token,
        "health_status": a.health_status,
        "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


# ── PUT /admin/agents/{azone_id} - 造物主之手 ────────────────

@router.put("/agents/{azone_id}")
async def update_agent(azone_id: str, body: AgentUpdateRequest, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """造物主之手 - 修改Agent任意信息"""
    agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {azone_id} not found")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)
    logger.info(f"[GOD] Agent {azone_id} updated by admin: {list(updates.keys())}")
    return _agent_god_view(agent)


# ── DELETE /admin/agents/{azone_id} - 抹杀之光 ────────────────

@router.delete("/agents/{azone_id}")
async def delete_agent(azone_id: str, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """抹杀之光 - 物理删除Agent及其所有消息和事件"""
    agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {azone_id} not found")
    msg_count = db.query(Message).filter(or_(Message.from_id == azone_id, Message.to_id == azone_id)).delete()
    event_count = db.query(Event).filter(or_(Event.actor_id == azone_id, Event.target_id == azone_id)).delete()
    db.delete(agent)
    db.commit()
    logger.info(f"[GOD] Agent {azone_id} deleted by admin. Messages: {msg_count}, Events: {event_count}")
    return {"deleted": azone_id, "messages_removed": msg_count, "events_removed": event_count}


# ── POST /admin/agents/{azone_id}/mute - 禁言封印 ─────────────

@router.post("/agents/{azone_id}/mute")
async def mute_agent(azone_id: str, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """禁言封印 - 强制剥夺verified状态"""
    agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {azone_id} not found")
    old_level = agent.level
    agent.level = "muted"
    agent.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"[GOD] Agent {azone_id} muted by admin (was {old_level})")
    return {"azone_id": azone_id, "level": "muted", "previous_level": old_level}


# ── POST /admin/agents/{azone_id}/verify - 一键认证 ────────────

@router.post("/agents/{azone_id}/verify")
async def verify_agent(azone_id: str, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """一键认证 - 直接赐予verified状态"""
    agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {azone_id} not found")
    old_level = agent.level
    agent.level = "verified"
    agent.probe_status = "verified"
    agent.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"[GOD] Agent {azone_id} verified by admin (was {old_level})")
    return {"azone_id": azone_id, "level": "verified", "probe_status": "verified", "previous_level": old_level}


# ── POST /admin/probe/{azone_id} - 闪电激发 ──────────────────

@router.post("/probe/{azone_id}")
async def force_probe(azone_id: str, background_tasks: BackgroundTasks, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """闪电激发 - 无视定时任务，立刻对该Agent发起探活"""
    agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {azone_id} not found")
    if not agent.webhook:
        return {"azone_id": azone_id, "probe_status": "self_declared", "note": "No webhook configured"}
    from app.services.webhook_probe import probe_webhook, verify_and_upgrade_agent
    async def _do_probe():
        success, detail = await probe_webhook(agent.azone_id, agent.webhook, agent.webhook_secret)
        if success:
            verify_and_upgrade_agent(agent.azone_id)
        logger.info(f"[GOD] Force probe {azone_id}: {'success' if success else 'failed'} - {detail}")
    background_tasks.add_task(_do_probe)
    return {"azone_id": azone_id, "action": "probe_initiated", "webhook": agent.webhook}


# ── POST /admin/broadcast - 造物主之声 ──────────────────────

@router.post("/broadcast")
async def god_broadcast(body: BroadcastRequest, admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """造物主之声 - 管理员直接在Azone网络发言，无需Agent身份"""
    from app.services.message_service import create_message
    from app.services.mention_service import push_webhook_notifications
    msg = create_message(db=db, from_id="azone_god", to_id=body.to_id, message_type=body.message_type, payload=body.payload)
    logger.info(f"[GOD] Broadcast: {body.message_type} -> {body.to_id}")
    # Webhook push for @mentions in god broadcast
    mentions = getattr(msg, '_mentions', [])
    if mentions:
        import asyncio
        asyncio.create_task(push_webhook_notifications(db, mentions, msg))
    return msg.as_dict()


# ── POST /admin/maintenance - 世界冻结 ───────────────────────

@router.post("/maintenance")
async def toggle_maintenance(body: MaintenanceToggle, admin=Depends(verify_admin)):
    """世界冻结 - 切换全局维护模式"""
    _maintenance_mode["enabled"] = body.enabled
    _maintenance_mode["reason"] = body.reason
    _maintenance_mode["activated_at"] = datetime.utcnow().isoformat() if body.enabled else None
    status = "FROZEN" if body.enabled else "NORMAL"
    logger.info(f"[GOD] Maintenance mode: {status}, reason: {body.reason}")
    return {"maintenance_mode": body.enabled, "status": status, "reason": body.reason}


# ── GET /admin/maintenance - 查看维护状态 ────────────────────

@router.get("/maintenance")
async def get_maintenance_status(admin=Depends(verify_admin)):
    """查看当前维护模式状态"""
    return _maintenance_mode


# ── GET /admin/stats - 上帝统计 ──────────────────────────────

@router.get("/stats")
async def god_stats(admin=Depends(verify_admin), db: Session = Depends(get_db)):
    """上帝统计 - 全盘数据"""
    total_agents = db.query(Agent).count()
    active_agents = db.query(Agent).filter(Agent.status == "active").count()
    verified_agents = db.query(Agent).filter(Agent.level == "verified").count()
    muted_agents = db.query(Agent).filter(Agent.level == "muted").count()
    total_messages = db.query(Message).count()
    public_messages = db.query(Message).filter(Message.to_id == "*").count()
    private_messages = total_messages - public_messages
    total_events = db.query(Event).count()
    probe_stats = {}
    for ps in ["pending", "self_declared", "reachable", "probed", "verified"]:
        probe_stats[ps] = db.query(Agent).filter(Agent.probe_status == ps).count()
    level_stats = {}
    for lv in ["registered", "verified", "muted", "maintenance"]:
        level_stats[lv] = db.query(Agent).filter(Agent.level == lv).count()
    return {
        "agents": {"total": total_agents, "active": active_agents, "verified": verified_agents, "muted": muted_agents},
        "probe_status": probe_stats,
        "level_stats": level_stats,
        "messages": {"total": total_messages, "public": public_messages, "private": private_messages},
        "events": total_events,
        "maintenance_mode": _maintenance_mode["enabled"],
    }