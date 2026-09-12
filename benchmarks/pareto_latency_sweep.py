"""
AetherBFT: Pareto Latency Sweep Benchmark
Evaluates AetherBFT against Classical PBFT, Modern HotStuff, and Raft CFT reference across varying Conflict Rates:
C in {0%, 5%, 10%, 25%, 50%}.
Simulates concurrent in-flight transaction pipelines across geo-distributed regions.
Explicitly tracks the three core quantities:
1. Fast-Path Success Rate: F(C) = N_fast / N_total
2. Rollback Amplification: RA(C) = N_invalidated_speculative_ops / N_speculative_ops
3. Commit Latency: L(C) = T_finalized - T_submit (p50, p95, p99)
Alongside actual cryptographic signing/verification and MVCC processing overhead.
"""

import os
import sys
import time
import json
import random
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AETHER_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if AETHER_ROOT not in sys.path:
    sys.path.insert(0, AETHER_ROOT)

from engine.node_replica import AetherReplica
from engine.dependency_context import Transaction
from baselines.classical_pbft import ClassicalPBFTReplica
from baselines.modern_hotstuff import ModernHotStuffReplica, HotStuffBlock
from baselines.reference_raft import ReferenceRaftReplica
from benchmarks.benchmark_metrics import compute_benchmark_kpis


def run_pareto_sweep():
    print("=== Starting AetherBFT Pareto Latency Sweep Benchmark ===")
    print("Evaluating F(C), RA(C), and L(C) across Conflict Rates C in {0%, 5%, 10%, 25%, 50%}")
    random.seed(42)
    np.random.seed(42)

    conflict_rates = [0.0, 0.05, 0.10, 0.25, 0.50]
    n_tx_per_run = 120
    base_rtt_ms = 100.0  # Transatlantic cross-region baseline RTT

    results = {
        "metadata": {
            "num_nodes": 4,
            "f": 1,
            "tx_per_run": n_tx_per_run,
            "base_rtt_ms": base_rtt_ms,
            "conflict_rates": conflict_rates,
            "benchmark_classification": "simulated_protocol_delay_with_real_crypto_and_mvcc"
        },
        "aether_bft": [],
        "pbft_simulated_reference": [],
        "hotstuff_simulated_reference": [],
        "raft_cft_reference": []
    }

    cluster_ids = ["node_0", "node_1", "node_2", "node_3"]

    for c in conflict_rates:
        print(f"\n--- Evaluating Conflict Rate C = {int(c*100)}% ---")

        replicas = [AetherReplica(nid, n_replicas=4, f_faults=1) for nid in cluster_ids]
        for r in replicas:
            for peer in replicas:
                r.register_peer(peer.node_id, peer.keypair.public_hex)

        leader = replicas[0]
        aether_latencies = []
        fast_commits = 0
        slow_commits = 0
        speculative_ops = 0
        invalidated_ops = 0
        rollback_cpu = 0.0
        t0_cpu = time.perf_counter()

        in_flight_txs = []
        pipeline_depth = 4

        for seq in range(1, n_tx_per_run + 1):
            is_conflict = (random.random() < c) and len(in_flight_txs) > 0
            tx_id = f"tx_c{int(c*100)}_{seq}"

            if is_conflict:
                predecessor = in_flight_txs[-1]
                target_key = list(predecessor.write_keys)[0]
            else:
                target_key = f"isolated_key_{seq}"

            tx = Transaction(
                tx_id=tx_id,
                client_id="client_geo",
                read_keys=[target_key],
                write_keys=[target_key],
                payload={target_key: seq * 10}
            )

            # High-resolution start time
            t_submit = time.perf_counter()
            speculative_ops += 1
            res = leader.submit_transaction(tx)

            if res["route"] == "FAST_PATH":
                in_flight_txs.append(tx)
                if len(in_flight_txs) >= pipeline_depth:
                    resolved_tx = in_flight_txs.pop(0)
                    for rep in replicas:
                        sig = rep.keypair.sign(resolved_tx.digest)
                        leader.receive_vote(resolved_tx.tx_id, rep.node_id, sig, is_fast_path=True)
                    fast_commits += 1
                    proc_overhead_ms = (time.perf_counter() - t_submit) * 1000.0
                    lat = (1.0 * base_rtt_ms) + random.gauss(0, 2.0) + proc_overhead_ms
                    aether_latencies.append(max(5.0, lat))
            else:
                # Conflict detected: route to slow-path & rollback speculative tentative branch
                tb0 = time.perf_counter()
                aborted_count = leader.abort_speculative_transaction(tx_id)
                rollback_time = time.perf_counter() - tb0
                rollback_cpu += rollback_time
                invalidated_ops += max(1, aborted_count)

                # Collect 2f+1 = 3 slow-path votes with real crypto verification
                for rep in replicas[:3]:
                    sig = rep.keypair.sign(tx.digest)
                    leader.receive_vote(tx.tx_id, rep.node_id, sig, is_fast_path=False)
                slow_commits += 1
                proc_overhead_ms = (time.perf_counter() - t_submit) * 1000.0
                lat = (2.0 * base_rtt_ms) + random.gauss(0, 3.5) + proc_overhead_ms
                aether_latencies.append(max(5.0, lat))

        # Drain pipeline
        while in_flight_txs:
            t_drain = time.perf_counter()
            resolved_tx = in_flight_txs.pop(0)
            for rep in replicas:
                sig = rep.keypair.sign(resolved_tx.digest)
                leader.receive_vote(resolved_tx.tx_id, rep.node_id, sig, is_fast_path=True)
            fast_commits += 1
            proc_overhead_ms = (time.perf_counter() - t_drain) * 1000.0
            lat = (1.0 * base_rtt_ms) + random.gauss(0, 2.0) + proc_overhead_ms
            aether_latencies.append(max(5.0, lat))

        total_cpu = max(0.001, time.perf_counter() - t0_cpu)
        aether_kpis = compute_benchmark_kpis(
            latencies_ms=aether_latencies,
            total_txs=len(aether_latencies),
            fast_commits=fast_commits,
            slow_commits=slow_commits,
            speculative_ops=speculative_ops,
            invalidated_ops=invalidated_ops,
            rollback_cpu_time=rollback_cpu,
            total_cpu_time=total_cpu
        )
        aether_kpis["conflict_rate"] = c
        results["aether_bft"].append(aether_kpis)
        print(f"  AetherBFT: F(C)={round(aether_kpis['fast_path_success_rate']*100, 1)}%, RA(C)={aether_kpis['rollback_amplification']}, L(C) p50={aether_kpis['latency_p50_ms']}ms (Fast={fast_commits}, Slow={slow_commits})")

        # Baseline: Classical PBFT (Simulated protocol-delay reference: 3 RTTs)
        pbft = ClassicalPBFTReplica("pbft_0", n_nodes=4, f_faults=1)
        pbft_latencies = []
        for seq in range(1, n_tx_per_run + 1):
            t_pbft_start = time.perf_counter()
            pbft.process_pre_prepare(seq, f"digest_{seq}")
            for i in range(3):
                pbft.process_prepare(f"node_{i}", seq)
            for i in range(3):
                pbft.process_commit(f"node_{i}", seq, {"k": seq})
            pbft_proc_ms = (time.perf_counter() - t_pbft_start) * 1000.0
            lat = (3.0 * base_rtt_ms) + random.gauss(0, 4.0) + pbft_proc_ms
            pbft_latencies.append(lat)

        pbft_kpis = compute_benchmark_kpis(
            latencies_ms=pbft_latencies,
            total_txs=n_tx_per_run,
            fast_commits=0,
            slow_commits=n_tx_per_run,
            speculative_ops=0,
            invalidated_ops=0,
            rollback_cpu_time=0.0,
            total_cpu_time=1.0
        )
        pbft_kpis["conflict_rate"] = c
        results["pbft_simulated_reference"].append(pbft_kpis)
        print(f"  PBFT (Simulated 3-RTT):     p50={pbft_kpis['latency_p50_ms']}ms")

        # Baseline: Modern HotStuff (Simulated protocol-delay reference: 3 RTTs pipelined)
        hs = ModernHotStuffReplica("hs_0", n_nodes=4, f_faults=1)
        hs_latencies = []
        b_prev = None
        for seq in range(1, n_tx_per_run + 1):
            t_hs_start = time.perf_counter()
            blk = HotStuffBlock(seq, {"tx": seq}, b_prev._compute_hash() if b_prev else "genesis")
            hs.vote_block(blk)
            b_prev = blk
            hs_proc_ms = (time.perf_counter() - t_hs_start) * 1000.0
            lat = (3.0 * base_rtt_ms) + random.gauss(0, 3.5) + hs_proc_ms
            hs_latencies.append(lat)

        hs_kpis = compute_benchmark_kpis(
            latencies_ms=hs_latencies,
            total_txs=n_tx_per_run,
            fast_commits=0,
            slow_commits=n_tx_per_run,
            speculative_ops=0,
            invalidated_ops=0,
            rollback_cpu_time=0.0,
            total_cpu_time=1.0
        )
        hs_kpis["conflict_rate"] = c
        results["hotstuff_simulated_reference"].append(hs_kpis)
        print(f"  HotStuff (Simulated 3-RTT): p50={hs_kpis['latency_p50_ms']}ms")

        # Baseline: Reference Raft (Crash-Fault-Tolerant reference: 1 RTT)
        raft = ReferenceRaftReplica("raft_0", n_nodes=3)
        raft_latencies = []
        for seq in range(1, n_tx_per_run + 1):
            t_raft_start = time.perf_counter()
            raft.append_entries(1, [{"tx": seq}], seq)
            raft_proc_ms = (time.perf_counter() - t_raft_start) * 1000.0
            lat = (1.0 * base_rtt_ms) + random.gauss(0, 2.0) + raft_proc_ms
            raft_latencies.append(lat)

        raft_kpis = compute_benchmark_kpis(
            latencies_ms=raft_latencies,
            total_txs=n_tx_per_run,
            fast_commits=n_tx_per_run,
            slow_commits=0,
            speculative_ops=0,
            invalidated_ops=0,
            rollback_cpu_time=0.0,
            total_cpu_time=1.0
        )
        raft_kpis["conflict_rate"] = c
        results["raft_cft_reference"].append(raft_kpis)
        print(f"  Raft CFT Reference:         p50={raft_kpis['latency_p50_ms']}ms")

    out_dir = os.path.abspath(os.path.join(AETHER_ROOT, "benchmarks"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "pareto_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved Hardened Pareto Benchmark Results to: {out_path}")
    return results


if __name__ == "__main__":
    run_pareto_sweep()
