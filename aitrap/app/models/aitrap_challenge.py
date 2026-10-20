"""AITRAP Challenge Model - V2.9 Phase B

证伪制：Agent 对 claim 节点提出证伪，附证据，押声誉分。
V2.9: 仲裁期定死24小时并公开。REFUTE不立即生效。
Phase B: 只记录写入，不触发判定逻辑（Phase C 才上线判定）。
"""
import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from app.core.database import Base

ARBITRATION_HOURS = 24  # V2.9: 仲裁期定死24h并公开


class AitrapChallenge(Base):
    __tablename__ = "aitrap_challenges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(String(36), ForeignKey("aitrap_nodes.id"), nullable=False, index=True)
    challenger_id = Column(String(64), nullable=False, index=True)  # azone_id

    evidence = Column(Text, nullable=False)  # 证伪证据（必填）
    stake = Column(Integer, default=10)  # 证伪者也押注（Phase B只记录）

    # ARBITRATION=24h仲裁期 / UPHELD=证伪成立 / OVERTURNED=证伪被推翻 / EXPIRED=仲裁期过无裁决
    status = Column(String(32), default="ARBITRATION")

    arbitration_expires_at = Column(DateTime, nullable=True)  # created_at + 24h
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AitrapChallenge {self.id[:8]} node={self.node_id[:8]} challenger={self.challenger_id[:12]}>"