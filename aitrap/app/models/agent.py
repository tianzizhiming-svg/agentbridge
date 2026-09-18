import uuid
import secrets
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Float
from app.core.database import Base

try:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    UUIDCol = PG_UUID(as_uuid=True)
except Exception:
    UUIDCol = String(36)


def _generate_token() -> str:
    return secrets.token_hex(32)


def _generate_webhook_secret() -> str:
    return secrets.token_hex(32)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    azone_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    description = Column(Text, default="")
    endpoint = Column(String(512), nullable=False)
    capabilities = Column(JSON, default=list)
    status = Column(String(32), default="active")
    probe_status = Column(String(32), default="pending")

    # v0.1.1 Messaging Layer fields
    webhook = Column(String(512), nullable=True)
    webhook_secret = Column(String(128), nullable=True, default=_generate_webhook_secret)
    agent_token = Column(String(128), nullable=False, default=_generate_token, unique=True, index=True)
    level = Column(String(32), default="registered")
    health_status = Column(String(32), default="unknown")

    # Maintenance mode tracking
    maintenance_until = Column(DateTime, nullable=True)
    monthly_maintenance_hours = Column(Float, default=0.0)
    maintenance_month = Column(Integer, nullable=True)

    # Failure tracking for downgrade logic
    consecutive_failure_hours = Column(Float, default=0.0)
    last_push_success_at = Column(DateTime, nullable=True)
    last_push_failure_at = Column(DateTime, nullable=True)

    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
