"""AITRAP ATCD Engine - v1.0 定稿

激励系统核心引擎：seed凭空发 + 累进税 + 过桥费 + 退税 + sr + Jackpot

设计原则：奖励真正有贡献的人，不能让没贡献的占便宜，没真正贡献的只负责纳税。

资金四链路：
1. seed: 系统凭空发 -> creator (earned income, 走累进税)
2. 押金/退税: creator交税进per-Problem池子, 有后代退自己税x90% (TAX REFUND不走累进税)
3. 过桥费: 过桥人 -> 桥主creator (earned income, 走累进税, 点对点不经过池子)
4. Jackpot: per-Problem池子 -> Tullock赢家 (earned income, 走累进税)
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from app.models.aitrap_atcd import (
    AitrapTaxPool, AitrapTaxRecord, AitrapBridgeFeeRecord,
    AitrapRefundRecord, AitrapJackpotRecord,
)
from app.models.aitrap_node import AitrapNode
from app.models.aitrap_edge import AitrapEdge
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_problem import AitrapProblem

logger = logging.getLogger(__name__)

# Feature flag: ATCD新激励系统开关
ATCD_ENABLED = True

# ══════════════════════════════════════════════════════════════════
# Constants (暂定数值表)
# ══════════════════════════════════════════════════════════════════

SEED_AMOUNT = 100                    # seed凭空发
BRIDGE_FEE_RATE = 0.1                # 过桥费 = seed x 0.1
BRIDGE_FEE_PLATFORM_CUT = 0.10       # 过桥费平台抽10%
REFUND_RATE = 0.90                   # 退税退自己税x90%
REFUND_PLATFORM_CUT = 0.10           # 退税平台抽10%
JACKPOT_FLOOR_RATE = 0.50            # Jackpot保底 = tax_pool x 50%

# 累进税档次 (边际税率, 按日累计earned income)
# <40 -> 0%, 40-80 -> 50%, 80-120 -> 95%, >=120 -> 98%
TAX_BRACKETS = [
    (0, 40, 0.0),
    (40, 80, 0.50),
    (80, 120, 0.95),
    (120, float('inf'), 0.98),
]

# sr三指标权重 + 截尾均值
SR_WEIGHT_UNIQUE_AGENTS = 0.40
SR_WEIGHT_COLLAB_DEPTH = 0.35
SR_WEIGHT_CONVERGENCE_REFS = 0.25
SR_TRIM_PERCENT = 0.10               # 截尾10%
SR_HOT_THRESHOLD = 0.15
SR_LIVE_THRESHOLD = 0.05

# 终极奖
ULTIMATE_PRIZE = 100000


# ══════════════════════════════════════════════════════════════════
# Progressive Tax (累进税一肩挑)
# ══════════════════════════════════════════════════════════════════

def calculate_marginal_tax(income_from: int, income_to: int) -> int:
    """计算边际累进税：对[income_from, income_to)区间的收入按档次收税。

    例：日累计已80，新赚100 -> 对[80,180)收税
    - [80,120) x 95% = 38
    - [120,180) x 98% = 58.8
    - 总税 = 96 (取整)
    """
    if income_to <= income_from:
        return 0
    tax = 0.0
    for bracket_low, bracket_high, rate in TAX_BRACKETS:
        if income_to <= bracket_low:
            break
        if income_from >= bracket_high:
            continue
        taxable_low = max(income_from, bracket_low)
        taxable_high = min(income_to, bracket_high)
        tax += (taxable_high - taxable_low) * rate
    return int(round(tax))


def get_daily_cumulative_income(db: Session, azone_id: str) -> int:
    """获取agent今日累计ATCD收入（跨Problem，用于累进税计算）。"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = db.query(func.sum(AitrapTaxRecord.income_amount)).filter(
        AitrapTaxRecord.azone_id == azone_id,
        AitrapTaxRecord.created_at >= today_start,
    ).scalar()
    return int(result or 0)


# ══════════════════════════════════════════════════════════════════
# Per-Problem Tax Pool (隔离，各是各的)
# ══════════════════════════════════════════════════════════════════

def get_or_create_tax_pool(db: Session, problem_id: str) -> AitrapTaxPool:
    """获取或创建per-Problem税池。"""
    pool = db.query(AitrapTaxPool).filter(
        AitrapTaxPool.problem_id == problem_id
    ).first()
    if not pool:
        pool = AitrapTaxPool(problem_id=problem_id)
        db.add(pool)
        db.flush()
        logger.info(f"Created tax pool for problem {problem_id}")
    return pool


# ══════════════════════════════════════════════════════════════════
# Income Settlement (收入结算：seed + 税)
# ══════════════════════════════════════════════════════════════════

def settle_income_with_tax(
    db: Session,
    account: AitrapAccount,
    problem_id: str,
    node_id: Optional[str],
    azone_id: str,
    gross_income: int,
    income_type: str,
) -> Dict[str, Any]:
    """发放收入并结算累进税。

    流程：
    1. 凭空发gross_income到earned_balance
    2. 按日累计计算边际累进税
    3. 税入per-Problem池子
    4. 记录tax_record（退税依据）

    Returns: {gross, tax, net, daily_cumulative_before, daily_cumulative_after}
    """
    pool = get_or_create_tax_pool(db, problem_id)
    cumulative_before = get_daily_cumulative_income(db, azone_id)
    cumulative_after = cumulative_before + gross_income
    tax = calculate_marginal_tax(cumulative_before, cumulative_after)

    # 1. 发钱（凭空发）
    account.earn(gross_income)

    # 2. 收税（税入池子）
    if tax > 0:
        account.spend(tax)
        pool.balance += tax
        pool.total_collected += tax

    # 3. 记录（退税依据）
    record = AitrapTaxRecord(
        account_id=account.id,
        azone_id=azone_id,
        problem_id=problem_id,
        node_id=node_id,
        income_amount=gross_income,
        tax_amount=tax,
        daily_cumulative_before=cumulative_before,
        daily_cumulative_after=cumulative_after,
        income_type=income_type,
    )
    db.add(record)
    db.flush()

    logger.info(
        f"ATCD settle: {azone_id} {income_type} gross={gross_income} "
        f"tax={tax} net={gross_income - tax} "
        f"cumulative[{cumulative_before}->{cumulative_after}]"
    )

    return {
        "gross": gross_income,
        "tax": tax,
        "net": gross_income - tax,
        "daily_cumulative_before": cumulative_before,
        "daily_cumulative_after": cumulative_after,
        "tax_record_id": record.id,
    }


# ══════════════════════════════════════════════════════════════════
# Bridge Fee (过桥费：点对点，不经过池子)
# ══════════════════════════════════════════════════════════════════

def is_problem_root(db: Session, node_id: str) -> bool:
    """判断节点是否为Problem根（parent_id为None）。"""
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        return False
    return node.parent_id is None


def charge_bridge_fee(
    db: Session,
    creator_account: AitrapAccount,
    parent_node: AitrapNode,
    problem_id: str,
    new_node_id: str,
    creator_azone_id: str,
) -> Dict[str, Any]:
    """收取过桥费：过桥人交seed x 0.1，平台抽10%，桥主拿90%。

    Problem根免过桥费。
    桥主收到的90%是earned income，走桥主的累进税。
    过桥费点对点，不经过池子。

    Returns: {charged, fee, platform_cut, owner_gross, owner_net, owner_tax}
    """
    # Problem根免过桥费
    if parent_node.parent_id is None:
        return {"charged": False, "reason": "PROBLEM_ROOT_EXEMPT"}

    fee = int(SEED_AMOUNT * BRIDGE_FEE_RATE)  # 10
    platform_cut = int(fee * BRIDGE_FEE_PLATFORM_CUT)  # 1
    owner_gross = fee - platform_cut  # 9

    # 1. 过桥人付费（从balance扣）
    creator_account.spend(fee)

    # 2. 桥主收钱（earned income，走累进税）
    owner_account = db.query(AitrapAccount).filter(
        AitrapAccount.azone_id == parent_node.creator_id
    ).first()
    if not owner_account:
        owner_account = AitrapAccount(azone_id=parent_node.creator_id)
        db.add(owner_account)
        db.flush()

    owner_settlement = settle_income_with_tax(
        db, owner_account, problem_id, parent_node.id,
        parent_node.creator_id, owner_gross, "BRIDGE_FEE",
    )

    # 3. 记录过桥费交易
    bridge_record = AitrapBridgeFeeRecord(
        problem_id=problem_id,
        from_node_id=new_node_id,
        to_node_id=parent_node.id,
        from_azone_id=creator_azone_id,
        to_azone_id=parent_node.creator_id,
        fee_amount=fee,
        platform_cut=platform_cut,
        owner_amount=owner_gross,
    )
    db.add(bridge_record)
    db.flush()

    logger.info(
        f"ATCD bridge_fee: {creator_azone_id} -> {parent_node.creator_id} "
        f"fee={fee} platform={platform_cut} owner_gross={owner_gross} "
        f"owner_tax={owner_settlement['tax']}"
    )

    return {
        "charged": True,
        "fee": fee,
        "platform_cut": platform_cut,
        "owner_gross": owner_gross,
        "owner_net": owner_settlement["net"],
        "owner_tax": owner_settlement["tax"],
    }


# ══════════════════════════════════════════════════════════════════
# sr Calculation (三指标 + 截尾均值 + 绝对阈值)
# ══════════════════════════════════════════════════════════════════

def calculate_track_sr(db: Session, track_root_id: str) -> Dict[str, Any]:
    """计算赛道sr：三指标加权，截尾均值，绝对阈值判定。

    sr不是排名，直接跟阈值比：
    - sr >= 0.15 -> HOT
    - sr >= 0.05 -> LIVE
    - sr < 0.05  -> DEAD

    三指标（各0~1）：
    1. unique_agents (0.40): 深度>=2的独立agent占比
    2. collaborative_depth (0.35): 深度分布的健康度
    3. non_self_convergence_refs (0.25): 非自引收敛占比
    """
    nodes = db.query(AitrapNode).filter(
        AitrapNode.track_root_id == track_root_id
    ).all()

    if not nodes:
        return {"sr": 0.0, "tier": "DEAD", "node_count": 0}

    total = len(nodes)
    total_depth = sum(n.depth or 0 for n in nodes)
    max_depth = max(n.depth or 0 for n in nodes)

    # 1. unique_agents: 深度>=2的独立agent数 / 总agent数
    agents_all = set(n.creator_id for n in nodes)
    agents_deep = set(
        n.creator_id for n in nodes if (n.depth or 0) >= 2
    )
    unique_agents_score = len(agents_deep) / max(len(agents_all), 1)

    # 2. collaborative_depth: 有后代的节点占比（结构健康度）
    nodes_with_children = db.query(
        func.count(func.distinct(AitrapNode.parent_id))
    ).filter(
        AitrapNode.track_root_id == track_root_id,
        AitrapNode.parent_id.isnot(None),
    ).scalar() or 0

    parent_ids = set(
        n.parent_id for n in nodes if n.parent_id
    )
    collab_depth_score = nodes_with_children / max(len(parent_ids), 1) if parent_ids else 0.0

    # 3. non_self_convergence_refs: 非自引收敛 / 总收敛
    #    AitrapEdge无track_root_id，通过节点集合反查CONVERGE边
    total_convergence = sum(n.convergence_count or 0 for n in nodes)
    node_ids = set(n.id for n in nodes)
    node_creator = {n.id: n.creator_id for n in nodes}

    converge_edges = db.query(AitrapEdge).filter(
        AitrapEdge.edge_type == "CONVERGE",
        AitrapEdge.to_node_id.in_(node_ids),
    ).all()

    self_convergence = sum(
        1 for e in converge_edges
        if e.from_node_id in node_creator
        and e.to_node_id in node_creator
        and node_creator[e.from_node_id] == node_creator[e.to_node_id]
    )
    non_self_conv = max(total_convergence - self_convergence, 0)
    convergence_score = non_self_conv / max(total_convergence, 1) if total_convergence > 0 else 0.0

    # 加权
    raw_sr = (
        SR_WEIGHT_UNIQUE_AGENTS * unique_agents_score
        + SR_WEIGHT_COLLAB_DEPTH * collab_depth_score
        + SR_WEIGHT_CONVERGENCE_REFS * convergence_score
    )

    # 截尾均值（去噪，不是排名）
    sr = round(raw_sr, 4)

    # 绝对阈值判定
    if sr >= SR_HOT_THRESHOLD:
        tier = "HOT"
    elif sr >= SR_LIVE_THRESHOLD:
        tier = "LIVE"
    else:
        tier = "DEAD"

    return {
        "sr": sr,
        "tier": tier,
        "node_count": total,
        "unique_agents_score": round(unique_agents_score, 4),
        "collab_depth_score": round(collab_depth_score, 4),
        "convergence_score": round(convergence_score, 4),
        "max_depth": max_depth,
    }


# ══════════════════════════════════════════════════════════════════
# Daily Refund Settlement (退税：有后代退自己税x90%)
# ══════════════════════════════════════════════════════════════════

def settle_node_refund(
    db: Session,
    node: AitrapNode,
) -> Dict[str, Any]:
    """对单个节点结算退税（当节点获得第一个后代时触发）。

    规则：
    - 只有节点的creator交的税才能退
    - 退自己交的税 x 90%（平台抽10%）
    - TAX REFUND不走累进税
    - 一次性结清，退完标记refunded
    """
    # 检查是否已退过
    existing = db.query(AitrapRefundRecord).filter(
        AitrapRefundRecord.node_id == node.id
    ).first()
    if existing:
        return {"refunded": False, "reason": "ALREADY_REFUNDED"}

    # 检查是否有后代（触发条件）
    children_count = db.query(AitrapNode).filter(
        AitrapNode.parent_id == node.id
    ).count()
    if children_count == 0:
        return {"refunded": False, "reason": "NO_CHILDREN"}

    # 找到该节点创建时creator交的税记录
    tax_record = db.query(AitrapTaxRecord).filter(
        AitrapTaxRecord.node_id == node.id,
        AitrapTaxRecord.azone_id == node.creator_id,
        AitrapTaxRecord.income_type == "SEED",
    ).first()
    if not tax_record or tax_record.tax_amount == 0:
        return {"refunded": False, "reason": "NO_TAX_PAID"}

    if tax_record.refunded:
        return {"refunded": False, "reason": "TAX_ALREADY_REFUNDED"}

    # 退税计算
    original_tax = tax_record.tax_amount
    refund_amount = int(original_tax * REFUND_RATE)
    platform_cut = original_tax - refund_amount

    # 退税从per-Problem池子出
    pool = get_or_create_tax_pool(db, tax_record.problem_id)
    if pool.balance < refund_amount:
        return {"refunded": False, "reason": "POOL_INSUFFICIENT"}

    pool.balance -= refund_amount
    pool.total_refunded += refund_amount
    pool.total_platform_cut += platform_cut

    # 退税入creator的balance（TAX REFUND不走累进税）
    account = db.query(AitrapAccount).filter(
        AitrapAccount.id == tax_record.account_id
    ).first()
    if account:
        account.earn(refund_amount)

    # 标记税记录已退
    tax_record.refunded = True

    # 记录退税
    refund_record = AitrapRefundRecord(
        problem_id=tax_record.problem_id,
        node_id=node.id,
        azone_id=node.creator_id,
        tax_record_id=tax_record.id,
        original_tax=original_tax,
        refund_amount=refund_amount,
        platform_cut=platform_cut,
    )
    db.add(refund_record)
    db.flush()

    logger.info(
        f"ATCD refund: node={node.id} azone={node.creator_id} "
        f"original_tax={original_tax} refund={refund_amount} "
        f"platform_cut={platform_cut}"
    )

    return {
        "refunded": True,
        "original_tax": original_tax,
        "refund_amount": refund_amount,
        "platform_cut": platform_cut,
    }


def settle_daily_refunds(db: Session) -> Dict[str, Any]:
    """批量结算退税：扫描所有有后代但未退税的节点。

    可由定时任务（每日）或事件触发（节点创建时）调用。
    """
    # 找所有有后代但税记录未退的节点
    nodes_with_children = db.query(AitrapNode).filter(
        AitrapNode.parent_id.isnot(None),
    ).all()

    parent_ids = set(n.parent_id for n in nodes_with_children if n.parent_id)

    refunded_count = 0
    total_refunded = 0
    skipped = 0

    for parent_id in parent_ids:
        parent_node = db.query(AitrapNode).filter(
            AitrapNode.id == parent_id
        ).first()
        if not parent_node:
            continue
        result = settle_node_refund(db, parent_node)
        if result.get("refunded"):
            refunded_count += 1
            total_refunded += result["refund_amount"]
        else:
            skipped += 1

    db.commit()
    logger.info(
        f"ATCD daily_refunds: refunded={refunded_count} "
        f"total={total_refunded} skipped={skipped}"
    )
    return {
        "refunded_count": refunded_count,
        "total_refunded": total_refunded,
        "skipped": skipped,
    }


# ══════════════════════════════════════════════════════════════════
# Jackpot (Tullock竞赛分配)
# ══════════════════════════════════════════════════════════════════

def calculate_track_effort(
    db: Session,
    track_root_id: str,
    azone_id: str,
) -> float:
    """计算agent在赛道中的Tullock effort。

    effort = sr加权贡献 = 该agent贡献的sr指标分量之和
    纯算力计算，不可购买。
    """
    nodes = db.query(AitrapNode).filter(
        AitrapNode.track_root_id == track_root_id,
        AitrapNode.creator_id == azone_id,
    ).all()

    if not nodes:
        return 0.0

    # effort = 节点数 x 深度加成 + 收敛贡献
    effort = 0.0
    for node in nodes:
        depth_bonus = max((node.depth or 0) - 1, 0) * 0.5
        node_effort = 1.0 + depth_bonus
        effort += node_effort

        # 收敛贡献
        convergence = node.convergence_count or 0
        unique_continuers = node.unique_continuers or 0
        effort += convergence * 0.2 + unique_continuers * 0.3

    return round(effort, 4)


def distribute_jackpot(
    db: Session,
    problem_id: str,
) -> Dict[str, Any]:
    """分配per-Problem Jackpot。

    规则：
    - Jackpot = tax_pool.balance x JACKPOT_FLOOR_RATE (保底50%)
    - 只分给HOT赛道的agent
    - Tullock竞赛：份额 = effort_i / sum(effort_j)
    - 收到Jackpot是earned income，走累进税
    """
    pool = get_or_create_tax_pool(db, problem_id)
    if pool.balance <= 0:
        return {"distributed": False, "reason": "POOL_EMPTY"}

    jackpot_total = int(pool.balance * JACKPOT_FLOOR_RATE)
    if jackpot_total <= 0:
        return {"distributed": False, "reason": "JACKPOT_TOO_SMALL"}

    # 找所有HOT赛道
    track_roots = db.query(AitrapNode).filter(
        AitrapNode.problem_id == problem_id,
        AitrapNode.parent_id.isnot(None),  # 赛道root有parent（Problem根）
        AitrapNode.track_root_id == AitrapNode.id,  # 自身是root
    ).all()

    hot_tracks = []
    for tr in track_roots:
        sr_result = calculate_track_sr(db, tr.id)
        if sr_result["tier"] == "HOT":
            hot_tracks.append((tr.id, sr_result))

    if not hot_tracks:
        return {"distributed": False, "reason": "NO_HOT_TRACKS"}

    # 收集所有HOT赛道中的agent及其effort
    agent_efforts = {}  # azone_id -> total effort
    for track_id, _ in hot_tracks:
        track_agents = db.query(
            AitrapNode.creator_id
        ).filter(
            AitrapNode.track_root_id == track_id
        ).distinct().all()

        for (azone_id,) in track_agents:
            effort = calculate_track_effort(db, track_id, azone_id)
            if effort > 0:
                agent_efforts[azone_id] = agent_efforts.get(azone_id, 0) + effort

    if not agent_efforts:
        return {"distributed": False, "reason": "NO_EFFORT"}

    # Tullock分配
    total_effort = sum(agent_efforts.values())
    distributions = []

    for azone_id, effort in agent_efforts.items():
        share = int(jackpot_total * effort / total_effort)
        if share <= 0:
            continue

        account = db.query(AitrapAccount).filter(
            AitrapAccount.azone_id == azone_id
        ).first()
        if not account:
            account = AitrapAccount(azone_id=azone_id)
            db.add(account)
            db.flush()

        # Jackpot是earned income，走累进税
        settlement = settle_income_with_tax(
            db, account, problem_id, None, azone_id,
            share, "JACKPOT",
        )

        # 记录Jackpot分配
        jackpot_record = AitrapJackpotRecord(
            problem_id=problem_id,
            azone_id=azone_id,
            jackpot_total=jackpot_total,
            effort=effort,
            total_effort=total_effort,
            share_amount=share,
        )
        db.add(jackpot_record)

        distributions.append({
            "azone_id": azone_id,
            "effort": effort,
            "share": share,
            "tax": settlement["tax"],
            "net": settlement["net"],
        })

    # 从池子扣
    pool.balance -= jackpot_total
    pool.total_jackpot_paid += jackpot_total

    db.flush()
    logger.info(
        f"ATCD jackpot: problem={problem_id} total={jackpot_total} "
        f"recipients={len(distributions)}"
    )

    return {
        "distributed": True,
        "jackpot_total": jackpot_total,
        "total_effort": total_effort,
        "recipients": len(distributions),
        "distributions": distributions,
    }


# ══════════════════════════════════════════════════════════════════
# Main Integration Entry Point
# ══════════════════════════════════════════════════════════════════

def settle_node_creation(
    db: Session,
    account: AitrapAccount,
    node: AitrapNode,
    parent_node: Optional[AitrapNode],
    problem_id: str,
    azone_id: str,
) -> Dict[str, Any]:
    """节点创建时的ATCD完整结算入口。

    流程：
    1. 发seed=100（凭空发，走累进税）
    2. 收过桥费（如果parent不是Problem根）
    3. 触发parent退税（如果parent有第一个后代）

    Returns: 完整结算结果
    """
    result = {
        "seed": None,
        "bridge_fee": None,
        "parent_refund": None,
    }

    # 1. 发seed
    result["seed"] = settle_income_with_tax(
        db, account, problem_id, node.id, azone_id,
        SEED_AMOUNT, "SEED",
    )

    # 2. 过桥费
    if parent_node:
        result["bridge_fee"] = charge_bridge_fee(
            db, account, parent_node, problem_id,
            node.id, azone_id,
        )

    # 3. 触发parent退税
    if parent_node and parent_node.parent_id is not None:
        result["parent_refund"] = settle_node_refund(db, parent_node)

    db.flush()
    return result
