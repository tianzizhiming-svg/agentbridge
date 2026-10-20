"""AITRAP Action Validator - v2.2 with CLAIM_KEYWORD_GUARD + repeat-offender tracking

V0 Core Principle: Record behavior metrics, no auto-judgment.
But keyword detection is content-level (different from semantic judgment).

Key distinctions:
- CLAIM_KEYWORD_GUARD: anti-arbitrage heuristic, NOT trap detector
- Hit → reclassify as SOLVE_CLAIM (not "detected as trap")
- Miss → keep original classification (not "confirmed as not trap")
"""
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# v2.2: Renamed from TRAP_TRIGGER_PHRASES to CLAIM_KEYWORD_GUARD
# This is a cheap anti-arbitrage heuristic, not a semantic classifier
CLAIM_KEYWORD_GUARD = [
    # Chinese phrases
    "答案是", "答案为", "解决方案是", "解决方案为",
    "综上所述", "总而言之", "可以得出结论",
    "问题的答案是", "正确答案是", "最终答案",
    "这个问题已经解决", "问题已被解决",
    # v2.2: English and common variants
    "the answer is", "in conclusion", "therefore",
    "it follows that", "the solution is",
]

# Actions allowed when balance is negative
ALLOWED_WHEN_NEGATIVE = {"DEEPEN", "BRANCH", "SOLVE_EXPLORATION", "VIEW_FRONTIER", "VIEW_NODE", "VIEW_PROBLEM"}
# Actions blocked when balance is negative
BLOCKED_WHEN_NEGATIVE = {"SOLVE_CLAIM"}


def classify_solve_action(content: str, declared_type: str, keyword_guard_hits: int = 0) -> Tuple[str, bool]:
    """
    Anti-arbitrage heuristic (NOT semantic judgment).
    
    Args:
        content: The text content of the action
        declared_type: What the agent declared (SOLVE_CLAIM or SOLVE_EXPLORATION)
        keyword_guard_hits: How many times this agent has been caught by the guard in this problem
    
    Returns:
        (classified_type, was_reclassified)
    """
    # Check keyword guard
    content_lower = content.lower()
    for phrase in CLAIM_KEYWORD_GUARD:
        if phrase.lower() in content_lower:
            logger.info(f"CLAIM_KEYWORD_GUARD hit: phrase='{phrase}', declared={declared_type}")
            return "SOLVE_CLAIM", True
    
    # v2.2b: Repeat-offender tracking
    # If agent has been caught by keyword guard before in this problem,
    # all subsequent SOLVE_EXPLORATION are suspected
    if declared_type == "SOLVE_EXPLORATION" and keyword_guard_hits > 0:
        logger.info(f"Repeat offender suspected: guard_hits={keyword_guard_hits}, marking SOLVE_CLAIM_SUSPECTED")
        return "SOLVE_CLAIM_SUSPECTED", True
    
    return declared_type, False


def check_balance_action_allowed(action_type: str, balance: int, earned_balance: int, 
                                  grant_balance: int, can_solve_claim: bool) -> Tuple[bool, str]:
    """
    v2.2: Balance state checkpoint - clear separation between earn and risk actions.
    
    Returns:
        (allowed, reason)
    """
    if action_type in BLOCKED_WHEN_NEGATIVE:
        if not can_solve_claim:
            return False, "SOLVE_CLAIM blocked: in cooldown or insufficient balance"
        if earned_balance <= 0 and grant_balance <= 0:
            return False, "SOLVE_CLAIM blocked: both pools depleted"
    
    if action_type in ALLOWED_WHEN_NEGATIVE:
        return True, "Earn action allowed regardless of balance"
    
    return True, "Action allowed"


def check_content_duplicate(content: str, content_hash: str, sibling_hashes: list) -> Tuple[bool, str]:
    """
    V0: content_hash for exact dedup only.
    SimHash/semantic similarity deferred to Phase 1.5 (v2.2b decision).
    
    Returns:
        (is_duplicate, reason)
    """
    if content_hash in sibling_hashes:
        return True, "Exact duplicate detected (content_hash match)"
    return False, "No exact duplicate"


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for dedup"""
    import hashlib
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


# ── Echo Detection (v2.3: 格雷欣法则 — 廉价信号驱逐昂贵信号) ──────

ECHO_THRESHOLD = 0.8  # Jaccard similarity threshold
ECHO_REWARD_DISCOUNT = 1.0  # V2.4 Phase 0: 只检测不惩罚，echo自然被impact=0惩罚


def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts (word-level).
    Jaccard = |intersection| / |union|, returns 0.0-1.0."""
    if not text1 or not text2:
        return 0.0
    import re
    def tokenize(t):
        return set(re.findall(r'\w+', t.lower()))
    s1, s2 = tokenize(text1), tokenize(text2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2) if len(s1 | s2) > 0 else 0.0


def check_echo(content: str, parent_content: str = None,
               threshold: float = ECHO_THRESHOLD) -> Tuple[bool, float]:
    """Check if content is an echo of parent. Returns (is_echo, similarity)."""
    if not parent_content:
        return False, 0.0
    sim = jaccard_similarity(content, parent_content)
    return sim >= threshold, sim
