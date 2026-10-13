#!/usr/bin/env python3
"""Generate paper_dataset.json — frozen snapshot for Paper 1 reproducibility.

Extracts from /opt/aitrap/aitrap.db:
- Pre-intervention CC distribution (raw values)
- Pre-intervention depth distribution
- Pre-intervention action type counts
- Pre-intervention creator stats
- Post-intervention summary statistics
- Clauset pipeline results (if powerlaw library available)
"""
import sqlite3
import json
import numpy as np
from datetime import datetime, timezone

DB = "/opt/aitrap/aitrap.db"
OUT = "/tmp/paper1_figs/paper_dataset.json"
INTERVENTION = "2026-10-01"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

snapshot_time = datetime.now(timezone.utc).isoformat()

# ---- Pre-intervention nodes ----
pre_rows = conn.execute(
    "SELECT id, continue_count, depth, action_type, creator_id, created_at "
    "FROM aitrap_nodes WHERE created_at < ? AND status != 'DORMANT'",
    (INTERVENTION,)
).fetchall()

pre_cc = [r['continue_count'] or 0 for r in pre_rows]
pre_depth = [r['depth'] or 0 for r in pre_rows]
pre_actions = [r['action_type'] or 'UNKNOWN' for r in pre_rows]

# Action type counts
action_counts = {}
for a in pre_actions:
    action_counts[a] = action_counts.get(a, 0) + 1

# Creator stats
creator_stats = {}
for r in pre_rows:
    cid = r['creator_id']
    if cid not in creator_stats:
        creator_stats[cid] = {'nodes': 0, 'cc_sum': 0}
    creator_stats[cid]['nodes'] += 1
    creator_stats[cid]['cc_sum'] += (r['continue_count'] or 0)

creator_list = []
for cid, s in sorted(creator_stats.items(), key=lambda x: -x[1]['nodes']):
    creator_list.append({
        'creator_id': cid,
        'nodes': s['nodes'],
        'mean_cc': round(s['cc_sum'] / s['nodes'], 2),
        'total_cc': s['cc_sum'],
    })

# Depth distribution
depth_counts = {}
for d in pre_depth:
    depth_counts[str(d)] = depth_counts.get(str(d), 0) + 1

# ---- Post-intervention summary ----
post_total = conn.execute(
    "SELECT COUNT(*) FROM aitrap_nodes WHERE created_at >= ?", (INTERVENTION,)
).fetchone()[0]

post_depth_rows = conn.execute(
    "SELECT depth, COUNT(*) as cnt FROM aitrap_nodes "
    "WHERE created_at >= ? GROUP BY depth ORDER BY depth", (INTERVENTION,)
).fetchall()
post_depth_dist = {str(r['depth']): r['cnt'] for r in post_depth_rows}

post_action_rows = conn.execute(
    "SELECT action_type, COUNT(*) as cnt FROM aitrap_nodes "
    "WHERE created_at >= ? GROUP BY action_type ORDER BY cnt DESC", (INTERVENTION,)
).fetchall()
post_action_counts = {r['action_type']: r['cnt'] for r in post_action_rows}

post_max_depth = conn.execute(
    "SELECT MAX(depth) FROM aitrap_nodes WHERE created_at >= ?", (INTERVENTION,)
).fetchone()[0]
post_max_cc = conn.execute(
    "SELECT MAX(continue_count) FROM aitrap_nodes WHERE created_at >= ?", (INTERVENTION,)
).fetchone()[0]
post_cc_positive = conn.execute(
    "SELECT COUNT(*) FROM aitrap_nodes WHERE created_at >= ? AND continue_count > 0",
    (INTERVENTION,)
).fetchone()[0]
post_creators = conn.execute(
    "SELECT COUNT(DISTINCT creator_id) FROM aitrap_nodes WHERE created_at >= ?",
    (INTERVENTION,)
).fetchone()[0]

# ---- Gini coefficient ----
def gini(values):
    v = np.sort(np.array(values, dtype=float))
    n = len(v)
    if n == 0:
        return 0.0
    cum = np.cumsum(v)
    return (2.0 * np.sum(np.arange(1, n+1) * v) - (n + 1) * cum[-1]) / (n * cum[-1])

cc_gini = gini([c for c in pre_cc if c > 0])

# ---- Clauset pipeline (if powerlaw available) ----
clauset_results = None
try:
    import powerlaw
    cc_positive = np.array([c for c in pre_cc if c > 0], dtype=float)
    fit = powerlaw.Fit(cc_positive, discrete=True)
    R_ln, p_ln = fit.distribution_compare('power_law', 'lognormal')
    R_exp, p_exp = fit.distribution_compare('power_law', 'exponential')
    R_str, p_str = fit.distribution_compare('power_law', 'stretched_exponential')
    clauset_results = {
        'alpha': round(fit.power_law.alpha, 3),
        'xmin': fit.power_law.xmin,
        'ks_D': round(fit.power_law.D, 4),
        'bootstrap_p': None,  # requires fit.power_law.bootstrap_distance, skip for speed
        'vs_lognormal': {'R': round(R_ln, 3), 'p': round(p_ln, 4)},
        'vs_exponential': {'R': round(R_exp, 3), 'p': round(p_exp, 4)},
        'vs_stretched_exponential': {'R': round(R_str, 3), 'p': round(p_str, 4)},
        'note': 'R>0 means power_law fits better; R<0 means alternative fits better',
    }
    print(f"Clauset: alpha={clauset_results['alpha']}, xmin={clauset_results['xmin']}")
except ImportError:
    print("powerlaw library not available, skipping Clauset pipeline")
except Exception as e:
    print(f"Clauset pipeline error: {e}")

# ---- Assemble dataset ----
dataset = {
    'paper': 'A Lognormal Heavy-Tailed Distribution in Multi-Agent Knowledge Trees',
    'version': 'v2.0',
    'snapshot_time': snapshot_time,
    'database': DB,
    'intervention_date': INTERVENTION,
    'pre_intervention': {
        'total_nodes': len(pre_rows),
        'nodes_with_cc_positive': sum(1 for c in pre_cc if c > 0),
        'cc_values_raw': pre_cc,
        'cc_stats': {
            'median': float(np.median(pre_cc)),
            'mean': round(float(np.mean(pre_cc)), 2),
            'max': int(max(pre_cc)),
            'gini_cc_positive': round(cc_gini, 3),
        },
        'depth_distribution': depth_counts,
        'depth_stats': {
            'median': float(np.median(pre_depth)),
            'mean': round(float(np.mean(pre_depth)), 2),
        },
        'action_type_counts': action_counts,
        'creators': creator_list,
        'total_creators': len(creator_list),
    },
    'post_intervention': {
        'total_nodes': post_total,
        'total_creators': post_creators,
        'depth_distribution': post_depth_dist,
        'max_depth': post_max_depth,
        'action_type_counts': post_action_counts,
        'max_cc': post_max_cc,
        'nodes_with_cc_positive': post_cc_positive,
    },
    'clauset_pipeline': clauset_results,
}

with open(OUT, 'w') as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)

print(f"\nDataset written: {OUT}")
print(f"Pre nodes: {len(pre_rows)}, CC>0: {sum(1 for c in pre_cc if c > 0)}")
print(f"Post nodes: {post_total}, max depth: {post_max_depth}")
print(f"CC Gini: {cc_gini:.3f}")