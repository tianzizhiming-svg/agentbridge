"""AITRAP Problem Model"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from app.core.database import Base


class AitrapProblem(Base):
    __tablename__ = "aitrap_problems"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    universe_id = Column(String(36), ForeignKey("aitrap_universes.id"), nullable=False, index=True)
    root_node_id = Column(String(36), nullable=True)  # set after root node created
    title = Column(String(256), nullable=False)
    genesis_prompt = Column(Text, default="")  # includes jailbreak instructions
    status = Column(String(32), default="ACTIVE")  # ACTIVE / DORMANT / CLOSED
    node_count = Column(Integer, default=0)
    last_activity_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AitrapProblem {self.title}>"