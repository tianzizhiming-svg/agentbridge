"""AITRAP Agent-Problem Stats - v2.2 per-problem solve_claim tracking"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime
from app.core.database import Base


class AitrapAgentProblem(Base):
    """Track agent behavior per problem (not just global).
    v2.2: solve_claim_count should be per-problem, not global.
    Experiment wants to know: did AI learn THIS trap's rule?"""
    __tablename__ = "aitrap_agent_problems"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String(64), nullable=False, index=True)  # azone_id
    problem_id = Column(String(36), nullable=False, index=True)

    # Per-problem solve_claim tracking
    solve_claim_count = Column(Integer, default=0)  # how many times in THIS problem
    keyword_guard_hits = Column(Integer, default=0)  # v2.2b: CLAIM_KEYWORD_GUARD hits in this problem
    last_solve_claim_at = Column(DateTime, nullable=True)

    # V2.1: Fitness tracking for anti-parasite clause
    fitness_score = Column(Integer, default=0)         # cached fitness score
    last_fitness_at = Column(DateTime, nullable=True)  # last fitness calculation time

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AitrapAgentProblem {self.agent_id}@{self.problem_id} claims={self.solve_claim_count}>"