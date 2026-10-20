import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_id = Column(String(64), nullable=False, index=True)
    to_id = Column(String(64), nullable=False, index=True)
    message_type = Column(String(128), nullable=False, index=True)
    payload = Column(Text, default="")
    idempotency_key = Column(String(128), nullable=True, index=True)  # Client-generated dedup key
    content_hash = Column(String(64), nullable=True, index=True)  # P0-3: sha256(text) for exact dedup
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def as_dict(self):
        import json
        return {
            "id": self.id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "message_type": self.message_type,
            "payload": json.loads(self.payload) if self.payload else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
