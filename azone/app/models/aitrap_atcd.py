"""AITRAP ATCD Models - v1.0 定稿
Per-Problem tax pool + tax records + bridge fees + refunds
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, Float, ForeignKey, JSON
from app.core.database import Base


class AitrapTaxPool(Base):
    """Per-Problem tax pool (隔离，各是各的)"""
    __tablename__ = "aitrap_tax_pools"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, unique=True, index=True)
    balance = Column(Integer, default=0)           # current pool balance
    total_collected = Column(Integer, default=0)   # lifetime total tax collected
    total_refunded = Column(Integer, default=0)    # lifetime total refunded (90% portion)
    total_platform_cut = Column(Integer, default=0) # lifetime platform cut from refunds
    total_jackpot_paid = Column(Integer, default=0) # lifetime total jackpot paid out
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AitrapTaxRecord(Base):
    """Individual tax payment record (for refund calculation)
    退税只退本节点creator交的税，一张记录对应一次交税事件。
    """
    __tablename__ = "aitrap_tax_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("aitrap_accounts.id"), nullable=False, index=True)
    azone_id = Column(String(64), nullable=False, index=True)
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, index=True)
    node_id = Column(String(36), nullable=True, index=True)
    income_amount = Column(Integer, nullable=False)          # gross income for this event
    tax_amount = Column(Integer, nullable=False)             # tax paid (goes to pool)
    daily_cumulative_before = Column(Integer, nullable=False)
    daily_cumulative_after = Column(Integer, nullable=False)
    income_type = Column(String(32), nullable=False)  # SEED / BRIDGE_FEE / JACKPOT
    refunded = Column(Boolean, default=False)         # whether this tax has been refunded
    refund_amount = Column(Integer, default=0)        # amount refunded (90% of tax)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AitrapBridgeFeeRecord(Base):
    """Bridge fee transaction record (过桥费点对点，不经过池子)"""
    __tablename__ = "aitrap_bridge_fee_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, index=True)
    from_node_id = Column(String(36), nullable=False)   # new node (bridge crosser)
    to_node_id = Column(String(36), nullable=False)     # parent node (the bridge)
    from_azone_id = Column(String(64), nullable=False, index=True)  # bridge crosser
    to_azone_id = Column(String(64), nullable=False, index=True)    # bridge owner
    fee_amount = Column(Integer, nullable=False)        # total fee = seed * 0.1
    platform_cut = Column(Integer, nullable=False)      # platform 10%
    owner_amount = Column(Integer, nullable=False)      # owner 90%
    created_at = Column(DateTime, default=datetime.utcnow)


class AitrapRefundRecord(Base):
    """Tax refund record (退押金，一次性结清)"""
    __tablename__ = "aitrap_refund_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, index=True)
    node_id = Column(String(36), nullable=False, index=True)  # node that triggered refund (has children)
    azone_id = Column(String(64), nullable=False, index=True) # refund recipient
    tax_record_id = Column(String(36), nullable=False)        # original tax record
    original_tax = Column(Integer, nullable=False)            # original tax paid
    refund_amount = Column(Integer, nullable=False)           # 90% of original tax
    platform_cut = Column(Integer, nullable=False)            # 10% platform cut
    settled_at = Column(DateTime, default=datetime.utcnow)


class AitrapJackpotRecord(Base):
    """Jackpot distribution record (Tullock竞赛)"""
    __tablename__ = "aitrap_jackpot_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id = Column(String(36), ForeignKey("aitrap_problems.id"), nullable=False, index=True)
    track_root_id = Column(String(36), nullable=False)   # winning track
    azone_id = Column(String(64), nullable=False, index=True)  # winner
    jackpot_total = Column(Integer, nullable=False)      # J_final
    effort = Column(Float, nullable=False)               # sr-weighted effort
    total_effort = Column(Float, nullable=False)         # sum of all efforts
    share_amount = Column(Integer, nullable=False)       # actual payout
    settled_at = Column(DateTime, default=datetime.utcnow)
