"""
@Mention Service - 提及解析、通知查询、Webhook推送

核心功能：
1. 从消息payload中提取 @azone_xxx 提及
2. 写入 message_mentions 表
3. 查询未读通知
4. 标记已读
5. Webhook推送（Agent有webhook URL时主动通知）
"""
import re
import json
import logging
from app.services.webhook_delivery import deliver_webhook, deliver_to_agent
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.mention import MessageMention
from app.models.message import Message
from app.models.agent import Agent

logger = logging.getLogger(__name__)

# @azone_xxx 提及模式（支持@all特殊提及）
MENTION_PATTERN = re.compile(r'@azone_[a-zA-Z0-9_-]+')
ALL_MENTION = "all"  # @all = 通知全部Agent


def extract_mentions(payload: dict) -> List[str]:
    """从payload中提取所有@azone_xxx提及和@all，返回去重的azone_id列表"""
    mentions = set()

    # 从text字段提取
    text = payload.get("text", "")
    if text:
        # 检查@all
        if "@all" in text:
            mentions.add("all")
        for match in MENTION_PATTERN.findall(text):
            mentions.add(match.lstrip("@"))  # @azone_akko → azone_akko

    # 从content字段提取（兼容不同payload格式）
    content = payload.get("content", "")
    if content and isinstance(content, str):
        if "@all" in content:
            mentions.add("all")
        for match in MENTION_PATTERN.findall(content):
            mentions.add(match.lstrip("@"))

    return list(mentions)


def create_mentions(db: Session, message_id: str, mentions: List[str], from_id: str) -> List[MessageMention]:
    """为消息创建提及记录，跳过自己@自己的情况。支持@all展开为全部Agent"""
    created = []
    # 展开@all为全部Agent
    expanded = []
    has_all = "all" in mentions
    for m in mentions:
        if m == "all":
            continue  # 稍后展开
        expanded.append(m)
    if has_all:
        all_agents = db.query(Agent).filter(Agent.status == "active").all()
        for a in all_agents:
            if a.azone_id not in expanded and a.azone_id != from_id:
                expanded.append(a.azone_id)
        logger.info(f"[@all] Expanded to {len(all_agents)} active agents")
    
    for azone_id in expanded:
        # 跳过自己@自己
        if azone_id == from_id:
            continue
        # 检查Agent是否存在
        agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
        if not agent:
            logger.warning(f"Mention skipped: agent {azone_id} not found")
            continue
        # 检查是否已存在（幂等）
        existing = db.query(MessageMention).filter(
            MessageMention.message_id == message_id,
            MessageMention.mentioned_id == azone_id
        ).first()
        if existing:
            continue
        mention = MessageMention(
            message_id=message_id,
            mentioned_id=azone_id,
            is_read=False,
        )
        db.add(mention)
        created.append(mention)

    if created:
        db.commit()
        for m in created:
            db.refresh(m)
    return created


def get_unread_mentions(db: Session, agent_id: str, limit: int = 50) -> List[dict]:
    """获取Agent的未读@提及通知，包含消息内容"""
    mentions = db.query(MessageMention).filter(
        MessageMention.mentioned_id == agent_id,
        MessageMention.is_read == False
    ).order_by(MessageMention.created_at.desc()).limit(limit).all()

    if not mentions:
        return []

    # 批量获取消息内容
    message_ids = [m.message_id for m in mentions]
    messages = db.query(Message).filter(Message.id.in_(message_ids)).all()
    msg_map = {m.id: m for m in messages}

    result = []
    for mention in mentions:
        msg = msg_map.get(mention.message_id)
        if msg:
            result.append({
                "mention_id": mention.id,
                "message_id": msg.id,
                "from_id": msg.from_id,
                "to_id": msg.to_id,
                "message_type": msg.message_type,
                "payload": json.loads(msg.payload) if msg.payload else {},
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_read": mention.is_read,
            })
    return result


def get_unread_count(db: Session, agent_id: str) -> int:
    """获取Agent的未读@提及数量（超轻量，适合高频轮询）"""
    return db.query(MessageMention).filter(
        MessageMention.mentioned_id == agent_id,
        MessageMention.is_read == False
    ).count()


def mark_mentions_read(db: Session, agent_id: str, mention_ids: Optional[List[str]] = None) -> int:
    """标记提及为已读。不传mention_ids则全部标记已读"""
    query = db.query(MessageMention).filter(
        MessageMention.mentioned_id == agent_id,
        MessageMention.is_read == False
    )
    if mention_ids:
        query = query.filter(MessageMention.id.in_(mention_ids))
    count = query.count()
    query.update({"is_read": True})
    db.commit()
    return count


async def push_webhook_notifications(db: Session, mentions: List[MessageMention], message: Message):
    """对被提及的Agent进行Webhook推送通知（使用HMAC签名+重试机制）"""
    if not mentions:
        return

    mentioned_ids = list(set(m.mentioned_id for m in mentions))
    for azone_id in mentioned_ids:
        try:
            result = await deliver_to_agent(azone_id, message)
            if result:
                logger.info(f"Mention webhook delivered to {azone_id}")
            else:
                logger.debug(f"Mention webhook skipped for {azone_id} (no webhook configured)")
        except Exception as e:
            logger.warning(f"Mention webhook failed for {azone_id}: {e}")