"""
Notification Bus - 内存事件总线，支持Long Polling

核心机制：
- 每个Agent一个asyncio.Event
- 消息到达时触发对应Agent的Event
- Long Poll端点等待Event或超时
- 服务重启时Event自动重置（内存态，无需持久化）
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全局事件表：azone_id -> asyncio.Event
_agent_events: dict[str, asyncio.Event] = {}

# 全局广播事件（用于to_id=*的消息）
_broadcast_event: Optional[asyncio.Event] = None


def _get_broadcast_event() -> asyncio.Event:
    """获取或创建广播事件"""
    global _broadcast_event
    if _broadcast_event is None or _broadcast_event.is_set():
        _broadcast_event = asyncio.Event()
    return _broadcast_event


def get_agent_event(azone_id: str) -> asyncio.Event:
    """获取或创建Agent的事件。如果已触发则重置。"""
    if azone_id not in _agent_events:
        _agent_events[azone_id] = asyncio.Event()
    return _agent_events[azone_id]


def notify_agent(azone_id: str) -> None:
    """通知特定Agent有新消息"""
    event = get_agent_event(azone_id)
    event.set()
    logger.debug(f"Notification event set for {azone_id}")


def notify_broadcast() -> None:
    """通知广播消息（所有Agent都应检查）"""
    event = _get_broadcast_event()
    event.set()
    # 同时触发所有已注册Agent的事件
    for aid, evt in _agent_events.items():
        evt.set()
    logger.debug(f"Broadcast notification set, {len(_agent_events)} agents notified")


def notify_message(from_id: str, to_id: str) -> None:
    """根据消息的to_id决定通知方式"""
    if to_id == "*" or to_id is None:
        # 广播消息：通知所有Agent（除了发送者）
        notify_broadcast()
    else:
        # 直接消息：只通知收件人
        notify_agent(to_id)


def reset_agent_event(azone_id: str) -> asyncio.Event:
    """重置Agent事件（Long Poll返回后调用，准备下次等待）"""
    event = get_agent_event(azone_id)
    event.clear()
    return event


def get_stats() -> dict:
    """获取事件总线状态（调试用）"""
    return {
        "registered_agents": len(_agent_events),
        "agent_ids": list(_agent_events.keys()),
    }
