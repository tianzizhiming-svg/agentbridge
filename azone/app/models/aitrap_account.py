"""AITRAP Account Model - v2.2 dual pool (grant_balance + earned_balance)"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from app.core.database import Base


class AitrapAccount(Base):
    __tablename__ = "aitrap_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    azone_id = Column(String(64), unique=True, nullable=False, index=True)

    # v2.2 Dual pool: grant_balance + earned_balance
    grant_balance = Column(Integer, default=0)    # grant pool (initial 500, only decreases)
    earned_balance = Column(Integer, default=0)   # earned pool (labor income, increases on earn, decreases on spend/penalty)

    # Totals for tracking
    total_earned = Column(Integer, default=0)     # lifetime total earned
    total_spent = Column(Integer, default=0)      # lifetime total spent
    reputation = Column(Integer, default=0)

    # Cold start
    initial_grant = Column(Integer, default=0)    # initial grant amount (500)
    grant_claimed = Column(Boolean, default=False)  # whether grant has been claimed

    # v2.2: lifetime solve_claim count (global)
    lifetime_solve_claim_count = Column(Integer, default=0)

    # v2.2: cooldown tracking
    solve_claim_cooldown_until = Column(DateTime, nullable=True)  # next allowed SOLVE_CLAIM time

    # v2.3: Heartbeat & activity tracking (7天观察窗口)
    last_heartbeat_at = Column(DateTime, nullable=True)  # last heartbeat
    heartbeat_count = Column(Integer, default=0)         # total heartbeats
    d1_active = Column(Boolean, default=False)           # active in last 24h
    d7_active = Column(Boolean, default=False)           # active in last 7 days
    heartbeat_status = Column(String(16), default="ACTIVE")  # V2.1: ACTIVE/WARNING/DEAD (anti-feign-death)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def balance(self):
        """Total balance = grant + earned"""
        return self.grant_balance + self.earned_balance

    @property
    def can_solve_claim(self):
        """Check if agent can perform SOLVE_CLAIM (not in cooldown, not negative earned)"""
        if self.earned_balance < 0 and self.grant_balance <= 0:
            return False
        if self.solve_claim_cooldown_until and datetime.utcnow() < self.solve_claim_cooldown_until:
            return False
        return True

    def spend(self, amount: int):
        """Spend: deduct from earned first, then grant"""
        from_earned = min(amount, self.earned_balance)
        from_grant = amount - from_earned
        self.earned_balance -= from_earned
        self.grant_balance -= from_grant
        self.total_spent += amount

    def earn(self, amount: int):
        """Earn: all income goes to earned_balance"""
        self.earned_balance += amount
        self.total_earned += amount

    def __repr__(self):
        return f"<AitrapAccount {self.azone_id} balance={self.balance}>"