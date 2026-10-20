import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from app.core.database import Base


class MessageMention(Base):
    """@提及关联表 - 记录消息中对Agent的@提及"""
    __tablename__ = "message_mentions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False, index=True)
    mentioned_id = Column(String(64), nullable=False, index=True)  # 被提及的azone_id
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def as_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "mentioned_id": self.mentioned_id,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }