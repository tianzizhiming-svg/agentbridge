"""AITRAP Edge Model"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from app.core.database import Base


class AitrapEdge(Base):
    __tablename__ = "aitrap_edges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_node_id = Column(String(36), ForeignKey("aitrap_nodes.id"), nullable=False, index=True)
    to_node_id = Column(String(36), ForeignKey("aitrap_nodes.id"), nullable=False, index=True)
    edge_type = Column(String(32), nullable=False)  # DEEPEN / BRANCH / CONVERGE / RECONSTRUCT
    weight = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AitrapEdge {self.from_node_id[:8]}->{self.to_node_id[:8]} {self.edge_type}>"