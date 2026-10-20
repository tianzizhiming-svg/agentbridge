import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON
from app.core.database import Base


class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), nullable=False, index=True)
    agent_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="pending")
    retry_count = Column(String(8), default="0")
    attempted_at = Column(DateTime, nullable=True)
    response_code = Column(String(8), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
