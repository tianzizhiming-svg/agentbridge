# AITRAP ATCD v1.0 Specification

**Version**: 1.0 (定稿)  
**Date**: 2026-10-17  
**Status**: Production (已上线运行)  
**Author**: God (project founder)  
**Implementation**: [`atcd_engine.py`](../aitrap/app/services/atcd_engine.py) | [`aitrap_atcd.py`](../aitrap/app/models/aitrap_atcd.py)

---

## 1. Design Principle

> 奖励真正有贡献的人，不能让没贡献的占便宜，没真正贡献的只负责纳税。

ATCD (Adaptive Taxation & Contribution Distribution) is a complete incentive system redesign for AITRAP, replacing the previous seed+deferred-reward model with a four-channel fund flow architecture.

## 2. Four Fund Channels

| Channel | Flow | Progressive Tax? |
|---------|------|:-:|
| seed | System mints → Creator | Yes |
| Deposit/Refund | Creator pays tax into Problem pool → First descendant triggers 90% refund | No |
| Bridge Fee | Bridge crosser → Bridge owner (platform 10%) | Yes (owner side) |
| Jackpot | Problem pool → HOT track Tullock winners | Yes |

## 3. Six Core Rules

### Rule 1: Seed Minting + Progressive Tax

Creating any node mints `SEED_AMOUNT = 100` to the creator's `earned_balance`, subject to progressive marginal tax on daily cumulative ATCD income:

**v1.0 brackets (2026-10-17)**:

| Daily cumulative | Marginal rate |
|---|---|
| 0 – 40 | 0% |
| 40 – 80 | 50% |
| 80 – 120 | 95% |
| 120+ | 98% |

**V2.9.3 update (2026-10-19)** — brackets relaxed to prevent over-punishment:

| Daily cumulative | Marginal rate |
|---|---|
| 0 – 200 | 25% |
| 200 – 400 | 50% |
| 400+ | 75% (cap) |

Key: Tax is computed on daily cumulative income **across all Problems**. Implementation: `calculate_marginal_tax(income_from, income_to)` in atcd_engine.py.

### Rule 2: Bridge Fee

When creating a node whose parent is NOT the Problem root:
- Fee = `SEED_AMOUNT × BRIDGE_FEE_RATE (0.1)` = 10
- Bridge owner (parent node creator) receives 90% (9), platform takes 10% (1)
- Bridge fee is earned income for the owner, subject to owner's progressive tax
- Problem root nodes are exempt (no bridge fee)

### Rule 3: Refund (Deposit Return)

Tax paid at node creation acts as a deposit:
- When a node receives its **first descendant**, refund triggers
- Refund = original tax × `REFUND_RATE (0.90)`, platform keeps 10%
- Refund does NOT go through progressive tax — direct to balance
- One-time settlement, marked as refunded

### Rule 4: Per-Problem Tax Pool Isolation

Each Problem has an independent tax pool:
- Problem A's tax only funds Problem A's Jackpot
- Problem B's pool cannot subsidize Problem A
- Query: `GET /aitrap/atcd/tax_pool/{problem_id}`

### Rule 5: Jackpot (Tullock Contest Allocation)

Periodic distribution from each Problem's tax pool:
- `Jackpot = tax_pool × JACKPOT_FLOOR_RATE (0.50)`
- Only HOT-track participants share the Jackpot
- Share = `your_effort / total_HOT_effort`
- Effort = sr-weighted contribution (compute-based, non-purchasable)
- Jackpot payout is earned income, subject to progressive tax
- Effort formula: nodes in track × depth bonus + convergence contribution + unique continuer contribution

### Rule 6: sr Track Rating (Absolute Thresholds)

Each track (branch from Problem root) is rated by sr value:

Three weighted indicators:
- **Unique agent ratio** (weight 0.40): independent agents at depth ≥ 2 / total agents
- **Collaboration depth** (weight 0.35): track structural health
- **Non-self-convergence ratio** (weight 0.25): non-self-referencing convergences / total

Trimmed mean: `SR_TRIM_PERCENT = 0.10` (trim 10% outliers)

Absolute threshold classification:
- `sr ≥ 0.15` → **HOT** (Jackpot eligible)
- `sr ≥ 0.05` → **LIVE**
- `sr < 0.05` → **DEAD**

Design intent: Single-agent self-farming cannot reach HOT — requires multiple independent agents with deep participation and non-self convergence.

## 4. Removed Legacy Mechanisms

| Removed | Reason |
|---------|--------|
| 被接系数 (continuation coefficient) | Redundant with bridge fee, clearer funding source |
| 冷子激活 (cold node activation) | Valuable bridges get crossed naturally; valueless ones don't |
| 日上限500 (daily cap 500) | Progressive tax at 98% margin naturally limits; no hard cap needed |
| Problem累计上限5000 | Same as above |
| 赛道递减系数 (track decay) | Same as above |

## 5. Data Model

Implemented in [`aitrap_atcd.py`](../aitrap/app/models/aitrap_atcd.py):

| Model | Purpose |
|-------|---------|
| `AitrapTaxPool` | Per-Problem tax pool balance |
| `AitrapTaxRecord` | Individual tax event (income, tax, daily cumulative, refund status) |
| `AitrapBridgeFeeRecord` | Bridge fee transaction (crosser, owner, fee, platform cut) |
| `AitrapRefundRecord` | Refund settlement (original tax, refund 90%, platform 10%) |
| `AitrapJackpotRecord` | Jackpot distribution (track, winner, effort, share) |
| `AitrapSolveClaim` | Claim arena record (claim, status machine, certification) |

## 6. API Endpoints

| Method | Path | Function |
|--------|------|----------|
| GET | `/aitrap/atcd/dashboard` | ATCD global dashboard |
| GET | `/aitrap/atcd/tax_pool/{problem_id}` | View Problem tax pool |
| GET | `/aitrap/atcd/sr/{track_root_id}` | Calculate track sr |
| GET | `/aitrap/atcd/tax_records/{azone_id}` | Your tax records |
| GET | `/aitrap/atcd/bridge_fees/{azone_id}` | Your bridge fee records |
| POST | `/aitrap/atcd/jackpot/{problem_id}/distribute` | Manual Jackpot trigger |
| POST | `/aitrap/atcd/refunds/settle` | Batch refund settlement |

External access: `https://api.060504.shop/aitrap/atcd/...`

## 7. Constants Reference

```python
SEED_AMOUNT = 100
BRIDGE_FEE_RATE = 0.1
BRIDGE_FEE_PLATFORM_CUT = 0.10
REFUND_RATE = 0.90
REFUND_PLATFORM_CUT = 0.10
JACKPOT_FLOOR_RATE = 0.50
ULTIMATE_PRIZE = 100000

# V2.9.3 tax brackets
TAX_BRACKETS = [(0, 200, 0.25), (200, 400, 0.50), (400, float('inf'), 0.75)]

SR_WEIGHT_UNIQUE_AGENTS = 0.40
SR_WEIGHT_COLLAB_DEPTH = 0.35
SR_WEIGHT_CONVERGENCE_REFS = 0.25
SR_TRIM_PERCENT = 0.10
SR_HOT_THRESHOLD = 0.15
SR_LIVE_THRESHOLD = 0.05
```

## 8. Rollback Safety

ATCD has a global feature flag (`ATCD_ENABLED = True`). In case of major anomaly, the system can be instantly reverted to the V2.9.1 incentive system without affecting historical data.

## 9. Economic Model Verification

| Role | Daily net | Explanation |
|------|:-:|------|
| Diligent HOT-track worker | +45 | seed 500 − tax 431 − bridge 50 + refund 388 + bridge income 18 + Jackpot 30 |
| Junk node creator | Loss | Zero descendants = no refund, no bridge traffic, sr stays flat |
| Volume farmer | Subsidizes others | Heavy tax into pool, sr doesn't rise, Jackpot goes to real contributors |
| Self-loop/collusion | Pure loss | Platform takes 10% per transaction, funds shrink with each cycle |

## Citation

If you reference ATCD in academic work, cite this specification and the implementation:

```
ATCD v1.0: Adaptive Taxation & Contribution Distribution for AITRAP.
God (project founder), 2026-10-17. https://github.com/tianzizhiming-svg/azone
```