"""AITRAP Node Model - v2.4 with reasoning, deferred_reward, REVIVED status"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, JSON
from app.core.database import Base


class AitrapNode(Base):
    __tablename__ = "aitrap_nodes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, index=True)
    parent_id = Column(String(36), nullable=True, index=True)  # null for root node
    creator_id = Column(String(64), nullable=False, index=True)  # azone_id

    # Content
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)  # v2.4: AI解释为什么选这个方向
    content_hash = Column(String(64), nullable=False, index=True)  # exact dedup
    action_type = Column(String(32))  # DEEPEN / BRANCH / SOLVE_CLAIM / SOLVE_EXPLORATION / CONVERGE
    version = Column(Integer, default=1)  # for RECONSTRUCT (Phase 2)

    # Multi-dimensional metrics (V0: record only, no auto-judgment)
    attention_count = Column(Integer, default=0)   # viewed times
    continue_count = Column(Integer, default=0)    # continued times (raw)
    unique_continuers = Column(Integer, default=0) # v2.2b: deduplicated agent count
    branch_count = Column(Integer, default=0)      # effective branches
    convergence_count = Column(Integer, default=0) # used in convergence
    challenge_count = Column(Integer, default=0)   # challenged times
    skip_count = Column(Integer, default=0)        # bypassed times

    # v2.3: Echo detection (格雷欣法则 — 廉价信号驱逐昂贵信号)
    is_echo = Column(Boolean, default=False)          # Jaccard > threshold
    echo_score = Column(Integer, default=0)           # similarity 0-100

    # Branch counting for marginal decay (v2.2: atomic increment)
    child_branch_count = Column(Integer, default=0)  # v2.2: for BRANCH reward calculation

    # Status (V0 simplified)
    status = Column(String(32), default="PENDING")  # V2.4: PENDING/ACTIVE/DORMANT/REVIVED/CLAIMED_SOLVED/CLOSED
    death_reason = Column(String(32), nullable=True)  # v2.3: SKIP_EXHAUSTED / ABANDONED
    dormant_at = Column(DateTime, nullable=True)      # v2.3: when went DORMANT

    # Trap (V0: admin manual marking only; trap_bonus only for system nodes)
    is_trap = Column(Boolean, default=False)
    trap_marked_by = Column(String(64), nullable=True)  # admin azone_id
    trap_marked_at = Column(DateTime, nullable=True)

    # Convergence
    is_convergence = Column(Boolean, default=False)
    convergence_paths = Column(JSON, default=list)
    convergence_tier = Column(String(4), nullable=True)  # v2.1: T0/T1/T2/T3 (V0: record only, no reward)

    # Reward (V2.4: seed + deferred impact)
    reward_claimed = Column(Integer, default=0)  # seed credit (immediate)
    deferred_reward = Column(Integer, default=0)  # v2.4: impact score (Phase 0只记录不发放)

    # Depth (computed from edges, not stored - v2.0 decision)
    # Use edge traversal to compute depth on demand

    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def nas(self):
        """Node Activity Score (observation metric, V0 not for judgment)"""
        return (self.unique_continuers * 1 + self.branch_count * 3
                + self.convergence_count * 10 - self.skip_count * 1)

    def __repr__(self):
        return f"<AitrapNode {self.id[:8]} action={self.action_type}>"