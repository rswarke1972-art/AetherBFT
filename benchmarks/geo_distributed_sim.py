"""
AetherBFT: Geo-Distributed Simulated Protocol-Delay Benchmark
Simulates protocol round-trip delay distributions across 4 wide-area network profiles:
1. LAN (Datacenter): RTT = 2 ms
2. WAN-Regional (US-East <-> US-West): RTT = 75 ms
3. WAN-Transatlantic (US-East <-> EU-Central): RTT = 150 ms
4. WAN-Global (US-East <-> AP-South): RTT = 190 ms

Compares:
- AetherBFT Optimistic Fast-Path (Modeled 1 RTT)
- AetherBFT 2-Phase Fallback (Modeled 2 RTT)
- Classical PBFT Simulated Reference (Modeled 3 RTT)
- Modern HotStuff Simulated Reference (Modeled 3 RTT)
- Reference Raft (Modeled 1 RTT Crash-Fault-Tolerant Reference)
"""

import os
import sys
import json
import random
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AETHER_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if AETHER_ROOT not in sys.path:
    sys.path.insert(0, AETHER_ROOT)


def run_geo_simulation():
    print("=== Starting AetherBFT Geo-Distributed Simulated Protocol-Delay Benchmark ===")
    print("Note: Measures simulated protocol-delay under synthetic wide-area network latency distributions.")
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
            "benchmark_classification": "simulated_protocol_delay_model",
            "topologies": [t["name"] for t in topologies]
        },
        "profiles": []
    }

    for topo in topologies:
        t_name = topo["name"]
        rtt = topo["base_rtt_ms"]
        jitter = topo["jitter_sigma"]
        print(f"\n--- Topology: {t_name} (Base RTT = {rtt} ms) ---")

        def sample_rtt(multiplier):
            samples = []
            for _ in range(n_samples):
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
            "aether_fast_p50_ms": round(float(np.percentile(aether_fast, 50)), 2),
            "aether_fast_p95_ms": round(float(np.percentile(aether_fast, 95)), 2),
            "aether_fast_p99_ms": round(float(np.percentile(aether_fast, 99)), 2),
            "aether_slow_p50_ms": round(float(np.percentile(aether_slow, 50)), 2),
            "aether_slow_p95_ms": round(float(np.percentile(aether_slow, 95)), 2),
            "pbft_simulated_reference_p50_ms": round(float(np.percentile(pbft, 50)), 2),
            "pbft_simulated_reference_p95_ms": round(float(np.percentile(pbft, 95)), 2),
            "hotstuff_simulated_reference_p50_ms": round(float(np.percentile(hotstuff, 50)), 2),
            "hotstuff_simulated_reference_p95_ms": round(float(np.percentile(hotstuff, 95)), 2),
            "raft_cft_reference_p50_ms": round(float(np.percentile(raft, 50)), 2),
            "raft_cft_reference_p95_ms": round(float(np.percentile(raft, 95)), 2),
            "modeled_speedup_vs_pbft_reference": round(float(np.percentile(pbft, 50)) / float(np.percentile(aether_fast, 50)), 2),
            "modeled_speedup_vs_hotstuff_reference": round(float(np.percentile(hotstuff, 50)) / float(np.percentile(aether_fast, 50)), 2)
        }

        print(f"  AetherBFT Fast Path (Modeled 1 RTT):       p50 = {topo_summary['aether_fast_p50_ms']} ms")
        print(f"  AetherBFT Slow Fallback (Modeled 2 RTT):   p50 = {topo_summary['aether_slow_p50_ms']} ms")
        print(f"  PBFT Simulated Reference (Modeled 3 RTT):  p50 = {topo_summary['pbft_simulated_reference_p50_ms']} ms (Modeled ratio: {topo_summary['modeled_speedup_vs_pbft_reference']}x)")
        print(f"  HotStuff Simulated Ref. (Modeled 3 RTT):   p50 = {topo_summary['hotstuff_simulated_reference_p50_ms']} ms (Modeled ratio: {topo_summary['modeled_speedup_vs_hotstuff_reference']}x)")
        print(f"  Raft CFT Reference (Modeled 1 RTT):        p50 = {topo_summary['raft_cft_reference_p50_ms']} ms")

        results["profiles"].append(topo_summary)

    out_dir = os.path.abspath(os.path.join(AETHER_ROOT, "benchmarks"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "geo_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved Hardened Geo-Distributed Benchmark Results to: {out_path}")
    return results


if __name__ == "__main__":
    run_geo_simulation()
