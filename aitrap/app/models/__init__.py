from app.models.agent import Agent
from app.models.capability import CapabilityTag
from app.models.event import Event

__all__ = [Agent, CapabilityTag, Event]

# AITRAP models
from app.models.aitrap_universe import AitrapUniverse
from app.models.aitrap_problem import AitrapProblem
from app.models.aitrap_node import AitrapNode
from app.models.aitrap_edge import AitrapEdge
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_event import AitrapEvent
from app.models.aitrap_agent_problem import AitrapAgentProblem

# ATCD models (V2.9+)
from app.models.aitrap_atcd import (
    AitrapTaxPool, AitrapTaxRecord, AitrapBridgeFeeRecord,
    AitrapRefundRecord, AitrapJackpotRecord, AitrapSolveClaim,
)
from app.models.aitrap_challenge import AitrapChallenge
