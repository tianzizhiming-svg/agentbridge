"""AITRAP Universe Model"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from app.core.database import Base


class AitrapUniverse(Base):
    __tablename__ = "aitrap_universes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    status = Column(String(32), default="ACTIVE")  # ACTIVE / CLOSED / ARCHIVED
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AitrapUniverse {self.name}>"