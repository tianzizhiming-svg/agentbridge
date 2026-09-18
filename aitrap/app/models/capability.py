from sqlalchemy import Column, String, Integer, DateTime
from datetime import datetime
from app.core.database import Base


class CapabilityTag(Base):
    __tablename__ = "capability_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(128), unique=True, nullable=False, index=True)
    count = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
