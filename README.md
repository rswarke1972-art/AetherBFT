# AetherBFT: Dual-Path Byzantine Fault Tolerant Consensus Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests: 15/15 Passed](https://img.shields.io/badge/tests-15%2F15%20passed-brightgreen.svg)](tests/)
[![Paper: IEEE Format](https://img.shields.io/badge/paper-IEEE%20Format-purple.svg)](paper/IEEE_AetherBFT_Manuscript.md)
[![Live Demo](https://img.shields.io/badge/demo-60%20FPS%20Canvas-cyan.svg)](https://rswarke1972-art.github.io/AetherBFT/)

> **Algorithm 07 in the Flagship Algorithmic Research Portfolio**  
> *Geo-Distributed Replicated Databases &bull; Speculative Dual-Path BFT Consensus &bull; Ephemeral MVCC Rollback*

---

## ⚡ Overview

Geo-distributed replicated state machines (e.g., Google Spanner, multi-region CockroachDB, enterprise blockchains) suffer severe latency penalties because classical PBFT and modern pipelined protocols (HotStuff) require **2 to 3 round-trip times (RTTs)** per commit. Across cross-continental links with round-trips of 100 to 190 ms, commit latencies compound into 300 to 570 ms delays.

**AetherBFT** introduces a dual-path consensus engine that delivers:
1. **Optimistic Fast-Path (1 RTT):** Unanimous fast quorum ($Q_{\text{fast}} = 3f + 1$) for non-conflicting proposals.
2. **Certified Dependency Context (CDC):** Formal conflict detection across finite deterministic key transactions.
3. **Ephemeral MVCC Version-Tree DAG:** Qualified $O(1)$ logical rollback via pointer redirection without cluster throughput freezes.
4. **Resilient 2-Phase Fallback (2 RTT):** Conservative Prepare-Commit ($Q_{\text{slow}} = 2f + 1$) with linear $O(n)$ Pacemaker view change.

---

## 📊 Benchmark Results

### 1. Pareto Latency Sweep across Conflict Rates ($C \in [0\%, 50\%]$)
*Evaluated across $n=4$ nodes ($f=1$), 100 ms base RTT, 120 transactions per run:*

| Conflict Rate $C$ | Fast Success $F(C)$ | Rollback Amp. $RA$ | AetherBFT $p_{50}$ | Classical PBFT (3 RTT) | Modern HotStuff (3 RTT) | Raft CFT Ceiling | Speedup vs PBFT |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0% (Disjoint)** | **100.0%** | 0.000 | **100.2 ms** | 300.4 ms | 299.7 ms | 100.0 ms | **3.00x** |
| **5% Contention** | **99.2%** | 0.008 | **99.7 ms** | 299.7 ms | 300.2 ms | 99.7 ms | **3.00x** |
| **10% Contention** | **95.0%** | 0.050 | **100.4 ms** | 300.0 ms | 299.5 ms | 99.7 ms | **2.99x** |
| **25% Contention** | **75.0%** | 0.250 | **101.1 ms** | 300.3 ms | 300.6 ms | 99.6 ms | **2.97x** |
| **50% (High)** | **55.0%** | 0.450 | **102.3 ms** | 299.9 ms | 300.3 ms | 100.5 ms | **2.93x** |

### 2. Multi-Region Topologies Benchmark

| Topology Profile | Base RTT | Aether Fast (1 RTT) | Aether Slow (2 RTT) | PBFT (3 RTT) | HotStuff (3 RTT) | Net Speedup |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **LAN Datacenter** | 2.0 ms | **2.02 ms** | 4.00 ms | 6.09 ms | 6.01 ms | **3.01x** |
| **WAN-Regional (US-East/West)** | 75.0 ms | **75.18 ms** | 151.18 ms | 225.91 ms | 224.98 ms | **3.00x** |
| **WAN-Transatlantic (US/EU)** | 150.0 ms | **150.78 ms** | 299.86 ms | 450.60 ms | 450.23 ms | **2.99x** |
| **WAN-Global (US/AP-South)** | 190.0 ms | **188.55 ms** | 381.39 ms | 569.31 ms | 570.84 ms | **3.02x** |

---

## 🔒 Theoretical Invariants

1. **Unconditional Safety under Asynchrony:**  
   The intersection of any unanimous fast quorum ($3f + 1$) and any slow quorum ($2f + 1$) in a cluster of $3f + 1$ contains at least $f + 1$ honest nodes, preventing double commits under arbitrary message delays.
2. **Liveness after GST:**  
   Under partial synchrony, non-conflicting proposals commit in 1 RTT, and conflicting proposals finalize via 2-phase slow path in 2 RTTs under Pacemaker view-change bounds.
3. **Speculative Read Boundary:**  
   Speculative execution results returned during the 1-RTT flight window are explicitly tagged `TENTATIVE`. `read_linearizable()` queries strictly the canonical finalized state tree.
4. **Qualified $O(1)$ Logical Rollback:**  
   Branch invalidation resets the active head pointer to the parent frame in $O(1)$ time, deferring physical memory deallocation to background garbage collection.

---

## 🚀 Quickstart & Verification

```bash
# Clone the repository
git clone https://github.com/rswarke1972-art/AetherBFT.git
cd AetherBFT

# Run the 15-test unit suite
python -m unittest discover -s tests -p "test_*.py"

# Execute Pareto conflict sweep benchmark
python benchmarks/pareto_latency_sweep.py

# Execute Byzantine resilience benchmark
python benchmarks/byzantine_resilience.py

# Execute Geo-Distributed network simulation
python benchmarks/geo_distributed_sim.py
```

---

## 📂 Repository Structure

```
AetherBFT/
├── engine/
│   ├── crypto_verifier.py       # Ed25519 authentication, QCs, Proof of Equivocation
│   ├── dependency_context.py    # Certified Dependency Context & transaction model
│   ├── mvcc_version_tree.py     # Ephemeral MVCC version-tree DAG & O(1) rollback
│   ├── fast_path_router.py      # Unanimous (3f+1) & slow (2f+1) quorum accumulator
│   ├── slow_path_consensus.py   # 2-phase Prepare-Commit & Pacemaker view-change
│   └── node_replica.py          # Unified BFT replica coordinating engine modules
├── baselines/
│   ├── classical_pbft.py        # Classical 3-phase PBFT replica (3 RTTs)
│   ├── modern_hotstuff.py       # Modern pipelined HotStuff replica (3 RTTs)
│   └── reference_raft.py        # Crash-Fault-Tolerant reference ceiling (1 RTT)
├── benchmarks/
│   ├── benchmark_metrics.py     # F(C), RA, recovery ratio, latency percentiles
│   ├── pareto_latency_sweep.py  # Conflict rate sweep (C in [0%, 50%])
│   ├── byzantine_resilience.py  # Equivocation detection & quarantine benchmark
│   └── geo_distributed_sim.py   # Multi-region topology latency benchmark
├── dashboard/                   # 60 FPS HTML5 Canvas Interactive PWA Simulation
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── paper/
│   ├── IEEE_AetherBFT_Manuscript.md
│   └── patentability_and_prior_art_review.md
├── tests/
│   └── test_aether_bft.py       # 15 automated unit tests (100% pass)
├── LICENSE                      # MIT License
└── README.md
```

---

## 📜 License
MIT License. Copyright &copy; 2026 Sahil Warke.
