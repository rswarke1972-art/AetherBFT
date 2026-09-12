"""
AetherBFT: Benchmark Metrics Module
Calculates:
1. Fast-Path Success Rate: F(C) = N_fast / N_total
2. Rollback Amplification: RA = Invalidated_Ops / Total_Speculative_Ops
3. Recovery Cost Ratio: Rollback_Work / Total_Work
4. Latency percentiles: p50, p95, p99
"""

import numpy as np
from typing import Dict, List, Any


def compute_benchmark_kpis(
    latencies_ms: List[float],
    total_txs: int,
    fast_commits: int,
    slow_commits: int,
    speculative_ops: int,
    invalidated_ops: int,
    rollback_cpu_time: float,
    total_cpu_time: float
) -> Dict[str, Any]:
    if not latencies_ms:
        latencies_ms = [1.0]

    lat_arr = np.array(latencies_ms, dtype=float)
    p50 = float(np.percentile(lat_arr, 50))
    p95 = float(np.percentile(lat_arr, 95))
    p99 = float(np.percentile(lat_arr, 99))
    mean_lat = float(np.mean(lat_arr))

    # Fast-Path Success Rate F(C)
    f_c = float(fast_commits / max(1, total_txs))

    # Rollback Amplification RA
    ra = float(invalidated_ops / max(1, speculative_ops))

    # Recovery Cost Ratio
    recovery_cost_ratio = float(rollback_cpu_time / max(1e-6, total_cpu_time))

    return {
        "total_txs": total_txs,
        "fast_commits": fast_commits,
        "slow_commits": slow_commits,
        "fast_path_success_rate": round(f_c, 4),
        "rollback_amplification": round(ra, 4),
        "recovery_cost_ratio": round(recovery_cost_ratio, 4),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "latency_mean_ms": round(mean_lat, 2)
    }
