"""
AetherBFT: Geo-Distributed Network Simulation Benchmark
Simulates real-world wide-area latency profiles across 4 multi-region topologies:
1. LAN (Datacenter): RTT = 2 ms
2. WAN-Regional (US-East <-> US-West): RTT = 75 ms
3. WAN-Transatlantic (US-East <-> EU-Central): RTT = 150 ms
4. WAN-Global (US-East <-> AP-South): RTT = 190 ms

Compares:
- AetherBFT Fast-Path (1 RTT)
- AetherBFT Fallback (2 RTT)
- Classical PBFT (3 RTT)
- Modern HotStuff (3 RTT)
- Reference Raft (1 RTT CFT baseline)
"""

import os
import sys
import json
import random
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_geo_simulation():
    print("=== Starting AetherBFT Geo-Distributed Network Simulation ===")
    random.seed(42)
    np.random.seed(42)

    topologies = [
        {"name": "LAN-Datacenter", "base_rtt_ms": 2.0, "jitter_sigma": 0.2},
        {"name": "WAN-Regional (US-East / US-West)", "base_rtt_ms": 75.0, "jitter_sigma": 2.5},
        {"name": "WAN-Transatlantic (US-East / EU-Central)", "base_rtt_ms": 150.0, "jitter_sigma": 4.0},
        {"name": "WAN-Global (US-East / AP-South)", "base_rtt_ms": 190.0, "jitter_sigma": 6.5}
    ]

    n_samples = 200
    results = {
        "metadata": {
            "samples_per_topology": n_samples,
            "topologies": [t["name"] for t in topologies]
        },
        "profiles": []
    }

    for topo in topologies:
        t_name = topo["name"]
        rtt = topo["base_rtt_ms"]
        jitter = topo["jitter_sigma"]
        print(f"\n--- Topology: {t_name} (Base RTT = {rtt} ms) ---")

        # Simulate round-trip times with Gaussian noise and tail delay
        def sample_rtt(multiplier):
            samples = []
            for _ in range(n_samples):
                # 95% normal jitter, 5% network tail spikes
                val = (multiplier * rtt) + random.gauss(0, jitter * multiplier)
                if random.random() < 0.05:
                    val += random.uniform(5.0, 20.0)
                samples.append(max(0.5, val))
            return samples

        aether_fast = sample_rtt(1.0)
        aether_slow = sample_rtt(2.0)
        pbft = sample_rtt(3.0)
        hotstuff = sample_rtt(3.0)
        raft = sample_rtt(1.0)

        topo_summary = {
            "topology": t_name,
            "base_rtt_ms": rtt,
            "aether_fast_p50": round(float(np.percentile(aether_fast, 50)), 2),
            "aether_fast_p95": round(float(np.percentile(aether_fast, 95)), 2),
            "aether_fast_p99": round(float(np.percentile(aether_fast, 99)), 2),
            "aether_slow_p50": round(float(np.percentile(aether_slow, 50)), 2),
            "aether_slow_p95": round(float(np.percentile(aether_slow, 95)), 2),
            "pbft_p50": round(float(np.percentile(pbft, 50)), 2),
            "pbft_p95": round(float(np.percentile(pbft, 95)), 2),
            "hotstuff_p50": round(float(np.percentile(hotstuff, 50)), 2),
            "hotstuff_p95": round(float(np.percentile(hotstuff, 95)), 2),
            "raft_p50": round(float(np.percentile(raft, 50)), 2),
            "raft_p95": round(float(np.percentile(raft, 95)), 2),
            "aether_speedup_vs_pbft": round(float(np.percentile(pbft, 50)) / float(np.percentile(aether_fast, 50)), 2),
            "aether_speedup_vs_hotstuff": round(float(np.percentile(hotstuff, 50)) / float(np.percentile(aether_fast, 50)), 2)
        }

        print(f"  AetherBFT Fast (1 RTT): p50 = {topo_summary['aether_fast_p50']} ms, p95 = {topo_summary['aether_fast_p95']} ms")
        print(f"  AetherBFT Slow (2 RTT): p50 = {topo_summary['aether_slow_p50']} ms")
        print(f"  Classical PBFT (3 RTT): p50 = {topo_summary['pbft_p50']} ms (Speedup: {topo_summary['aether_speedup_vs_pbft']}x)")
        print(f"  Modern HotStuff(3 RTT): p50 = {topo_summary['hotstuff_p50']} ms (Speedup: {topo_summary['aether_speedup_vs_hotstuff']}x)")
        print(f"  Raft CFT Ceiling (1 RTT): p50 = {topo_summary['raft_p50']} ms")

        results["profiles"].append(topo_summary)

    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "geo_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved Geo-Distributed Benchmark Results to: {out_path}")
    return results


if __name__ == "__main__":
    run_geo_simulation()
