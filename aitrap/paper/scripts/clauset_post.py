#!/usr/bin/env python3
"""Re-run Clauset pipeline on POST-intervention data.

Addresses paper limitation: 'CC distribution not re-fitted.'
Runs full powerlaw analysis on post-intervention CC values.
"""
import sqlite3
import json
import numpy as np

DB = "/opt/aitrap/aitrap.db"
OUT = "/tmp/paper1_figs/clauset_post_results.json"
INTERVENTION = "2026-10-01"

conn = sqlite3.connect(DB)

# Post-intervention CC values (all nodes, including DORMANT for completeness)
post_cc = [r[0] or 0 for r in conn.execute(
    "SELECT continue_count FROM aitrap_nodes WHERE created_at >= ?", (INTERVENTION,)
)]
post_cc_pos = np.array([c for c in post_cc if c > 0], dtype=float)

print(f"Post nodes total: {len(post_cc)}")
print(f"Post CC>0: {len(post_cc_pos)} ({len(post_cc_pos)/len(post_cc)*100:.1f}%)")
print(f"Post CC max: {post_cc_pos.max():.0f}")
print(f"Post CC median: {np.median(post_cc_pos):.0f}")
print(f"Post CC mean: {post_cc_pos.mean():.2f}")

import powerlaw

# Full Clauset pipeline
print("\n--- Fitting power law (this may take a minute) ---")
fit = powerlaw.Fit(post_cc_pos, discrete=True, verbose=False)

alpha = fit.power_law.alpha
xmin = fit.power_law.xmin
ks_D = fit.power_law.D

print(f"alpha = {alpha:.3f}")
print(f"xmin = {xmin}")
print(f"KS D = {ks_D:.4f}")

# Model comparisons
print("\n--- Model comparisons ---")
results = {}

R_ln, p_ln = fit.distribution_compare('power_law', 'lognormal')
results['vs_lognormal'] = {'R': round(R_ln, 3), 'p': round(p_ln, 4)}
print(f"vs lognormal: R={R_ln:.3f}, p={p_ln:.4f}")

R_exp, p_exp = fit.distribution_compare('power_law', 'exponential')
results['vs_exponential'] = {'R': round(R_exp, 3), 'p': round(p_exp, 4)}
print(f"vs exponential: R={R_exp:.3f}, p={p_exp:.4f}")

R_str, p_str = fit.distribution_compare('power_law', 'stretched_exponential')
results['vs_stretched_exponential'] = {'R': round(R_str, 3), 'p': round(p_str, 4)}
print(f"vs stretched exponential: R={R_str:.3f}, p={p_str:.4f}")

# Bootstrap p-value (500 iterations for speed)
print("\n--- Bootstrap p-value (500 iterations) ---")
try:
    D, p_boot = fit.power_law.bootstrap_distance(niter=500)
    results['bootstrap_p'] = round(p_boot, 3)
    print(f"bootstrap p = {p_boot:.3f}")
except Exception as e:
    print(f"Bootstrap failed: {e}")
    results['bootstrap_p'] = None

# Lognormal parameters for comparison
log_cc = np.log(post_cc_pos)
mu = log_cc.mean()
sigma = log_cc.std(ddof=1)
print(f"\nLognormal: mu={mu:.3f}, sigma={sigma:.3f}")

# Gini
def gini(values):
    v = np.sort(np.array(values, dtype=float))
    n = len(v)
    cum = np.cumsum(v)
    return (2.0 * np.sum(np.arange(1, n+1) * v) - (n + 1) * cum[-1]) / (n * cum[-1])

g = gini(post_cc_pos)
print(f"Gini (CC>0): {g:.3f}")

# Save results
output = {
    'dataset': 'post_intervention',
    'total_nodes': len(post_cc),
    'nodes_cc_positive': len(post_cc_pos),
    'cc_fraction_positive': round(len(post_cc_pos) / len(post_cc), 4),
    'cc_max': int(post_cc_pos.max()),
    'cc_median': float(np.median(post_cc_pos)),
    'cc_mean': round(float(post_cc_pos.mean()), 2),
    'clauset': {
        'alpha': round(alpha, 3),
        'xmin': xmin,
        'ks_D': round(ks_D, 4),
        'bootstrap_p': results.get('bootstrap_p'),
        **results,
    },
    'lognormal_params': {'mu': round(mu, 3), 'sigma': round(sigma, 3)},
    'gini_cc_positive': round(g, 3),
    'comparison_with_pre': {
        'pre_alpha': 2.177,
        'pre_gini': 0.503,
        'note': 'Pre-intervention values from original analysis snapshot',
    },
}

with open(OUT, 'w') as f:
    json.dump(output, f, indent=2)

print(f"\nResults saved: {OUT}")