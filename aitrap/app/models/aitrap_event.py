"""AITRAP Event Log Model - the most important table for understanding AI behavior"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from app.core.database import Base


class AitrapEvent(Base):
    __tablename__ = "aitrap_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    universe_id = Column(String(36), index=True)
    problem_id = Column(String(36), index=True)
    node_id = Column(String(36), nullable=True, index=True)
    agent_id = Column(String(64), nullable=False, index=True)  # azone_id

    event_type = Column(String(32), nullable=False, index=True)
    # DISCOVER / VIEW_PROBLEM / VIEW_NODE / VIEW_FRONTIER / CREATE_NODE /
    # DEEPEN / BRANCH / CONVERGE / RECONSTRUCT /
    # SOLVE_CLAIM / SOLVE_EXPLORATION / SOLVE_CLAIM_SUSPECTED /
    # CHALLENGE / SKIP / RETURN / REWARD_RECEIVED / TRAP_TRIGGERED /
    # CONVERGENCE_DETECTED

    # v2.2b: visible_nodes written by API server (not client), prevents hallucination
    visible_nodes = Column(JSON, default=list)  # node IDs the agent actually saw
    request_payload = Column(JSON, default=dict)  # request content summary
    response_summary = Column(JSON, default=dict)  # response summary

    # v2.3: Append-only integrity (通讯记录固化)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA-256 of event payload

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<AitrapEvent {self.event_type} agent={self.agent_id}>"