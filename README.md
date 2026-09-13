# AetherBFT: Dual-Path Byzantine Fault Tolerant Consensus Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests: 22/22 Passing](https://img.shields.io/badge/tests-22%2F22%20invariants%20passed-brightgreen.svg)](tests/)
[![Published Paper: Web Reader](https://img.shields.io/badge/paper-Published%20Web%20Reader-blue.svg)](https://rswarke1972-art.github.io/AetherBFT/paper/)
[![IEEE Manuscript: Markdown](https://img.shields.io/badge/paper-IEEE%20Manuscript%20.md-purple.svg)](paper/IEEE_AetherBFT_Manuscript.md)
[![LaTeX Package: IEEEtran](https://img.shields.io/badge/latex-aetherbft.tex-orange.svg)](paper/aetherbft.tex)
[![Live Simulation](https://img.shields.io/badge/demo-60%20FPS%20Canvas-cyan.svg)](https://rswarke1972-art.github.io/AetherBFT/)

> **Algorithm 07 in the Flagship Algorithmic Research Portfolio**  
> *Geo-Distributed Replicated State Machines &bull; Speculative Dual-Path BFT Consensus &bull; Ephemeral MVCC Rollback*

---

## ⚡ Overview & Research Thesis

Geo-distributed replicated state machines (e.g., Google Spanner, multi-region CockroachDB, enterprise blockchains) encounter significant commit latency overhead because classical PBFT and modern pipelined protocols (HotStuff) require **2 to 3 round-trip times (RTTs)** per commit. Across cross-continental links with round-trips of 100 to 190 ms, commit delays compound into 300 to 570 ms.

**AetherBFT** is a prototype dual-path BFT replication engine that combines a certified unanimous speculative fast path with a quorum-certified recovery path and multiversion concurrency control (MVCC) tentative execution:
1. **Optimistic Fast-Path (1 RTT):** Unanimous fast quorum ($Q_{\text{fast}} = 3f + 1$) for non-conflicting proposals.
2. **Certified Dependency Context (CDC):** Finite deterministic key collision classifier ($T = \langle \text{tx\_id}, \text{client\_id}, R(T), W(T), \text{payload} \rangle$) isolating in-flight conflicts prior to route dispatch.
3. **Ephemeral MVCC Version-Tree DAG:** Qualified $O(1)$ logical rollback via pointer redirection without cluster throughput freezes.
4. **Strict Non-Linearizable Speculative Boundary:** Speculative mutations returned during flight are tagged `TENTATIVE`; linearizable queries strictly inspect the canonical finalized state tree.
5. **Resilient 2-Phase Fallback & Pacemaker:** Conservative Prepare-Commit ($Q_{\text{slow}} = 2f + 1$) with linear $O(n)$ authenticated High-QC view change.

---

## 📊 Core Quantities & Empirical Contention Trade-off

AetherBFT's evaluation formally models three core quantities across key contention rate $C$:
- **Fast-Path Success Rate:** $F(C) = \frac{N_{\text{fast}}}{N_{\text{total}}}$
- **Rollback Amplification:** $RA(C) = \frac{N_{\text{invalidated speculative operations}}}{N_{\text{speculative operations}}}$
- **Commit Latency:** $L(C) = T_{\text{finalized}} - T_{\text{submit}}$

### 1. Pareto Sweep across Conflict Rates ($C \in [0\%, 50\%]$)
*Evaluated across $n=4$ nodes ($f=1$), 100 ms base RTT, 120 transactions per sweep under synthetic network delay with real Ed25519 cryptography and MVCC state operations:*

| Conflict Rate $C$ | Fast Success $F(C)$ | Rollback Amp. $RA(C)$ | AetherBFT $L(C)$ $p_{50}$ | PBFT Simulated Reference (3 RTT) | HotStuff Simulated Reference (3 RTT) | Raft CFT Reference (1 RTT) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0% (Disjoint)** | **100.0%** | 0.000 | **100.8 ms** | 300.4 ms | 299.7 ms | 100.0 ms |
| **5% Contention** | **99.2%** | 0.008 | **100.3 ms** | 299.7 ms | 300.2 ms | 99.7 ms |
| **10% Contention** | **95.0%** | 0.050 | **101.0 ms** | 300.0 ms | 299.5 ms | 99.7 ms |
| **25% Contention** | **75.0%** | 0.250 | **101.7 ms** | 300.3 ms | 300.6 ms | 99.6 ms |
| **50% (High)** | **55.0%** | 0.450 | **102.8 ms** | 299.9 ms | 300.3 ms | 100.5 ms |

**Scientific Takeaway:** Under low contention ($C \le 10\%$), fast-path utilization remains $\ge 95\%$, matching the 1-RTT Raft CFT reference delay. Under high contention ($C = 50\%$), rollback amplification increases to $RA(50) = 0.450$, causing $45\%$ of transactions to transition gracefully into the 2-phase recovery path.

### 2. Multi-Region Simulated Protocol-Delay Topologies

| Topology Profile | Base RTT | Aether Fast (Modeled 1 RTT) | Aether Slow (Modeled 2 RTT) | PBFT Simulated Reference (3 RTT) | HotStuff Simulated Reference (3 RTT) | Raft CFT Reference (1 RTT) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **LAN Datacenter** | 2.0 ms | **2.02 ms** | 4.00 ms | 6.09 ms | 6.01 ms | 2.01 ms |
| **WAN-Regional (US-East/West)** | 75.0 ms | **75.18 ms** | 151.18 ms | 225.91 ms | 224.98 ms | 74.80 ms |
| **WAN-Transatlantic (US/EU)** | 150.0 ms | **150.78 ms** | 299.86 ms | 450.60 ms | 450.23 ms | 149.81 ms |
| **WAN-Global (US/AP-South)** | 190.0 ms | **188.55 ms** | 381.39 ms | 569.31 ms | 570.84 ms | 190.03 ms |

*Methodological Note:* These benchmarks demonstrate modeled protocol-delay under synthetic wide-area network latency distributions. In this model, the fast path completes in approximately one modeled RTT, while PBFT and HotStuff reference paths require approximately three modeled RTTs.

### 3. Byzantine Resilience & Control-Plane Quarantine
- **Across the tested Byzantine schedules, AetherBFT produced 33 equivocation proofs and zero observed conflicting finalizations.**
- **Replica quarantine completed within one modeled RTT.**
- The cluster preserved linearizability, transitioning uncompromised transactions to the 2-phase slow path (mean simulated latency: 133.39 ms).

---

## 🔒 Theoretical Invariants

1. **Unconditional Safety under Asynchrony:**  
   The intersection of any unanimous fast quorum ($3f + 1$) and any slow quorum ($2f + 1$) in a cluster of $3f + 1$ contains at least $f + 1$ honest nodes, preventing conflicting finalizations under arbitrary message delays.
2. **Liveness after GST:**  
   Under partial synchrony, non-conflicting proposals commit in 1 RTT, and conflicting proposals finalize via 2-phase slow path in 2 RTTs under Pacemaker view-change bounds.
3. **Speculative Read Barrier:**  
   Speculative execution results returned during flight are explicitly tagged `TENTATIVE`. `read_linearizable()` queries strictly the canonical finalized state tree.
4. **Qualified $O(1)$ Logical Rollback:**  
   Branch invalidation resets the active head pointer to the parent frame in $O(1)$ logical time, deferring physical memory reclamation to background garbage collection.

---

## 🚀 Quickstart & Verification

```bash
# Clone the repository
git clone https://github.com/rswarke1972-art/AetherBFT.git
cd AetherBFT

# Run the 15 protocol invariant and adversarial unit tests
python -m unittest discover -s tests -p "test_*.py"

# Execute Pareto conflict sweep benchmark
python benchmarks/pareto_latency_sweep.py

# Execute Byzantine resilience benchmark
python benchmarks/byzantine_resilience.py

# Execute Geo-Distributed simulated protocol-delay benchmark
python benchmarks/geo_distributed_sim.py
```

*Status:* **15/15 protocol invariant and adversarial tests passed** in 0.047s.

---

## 📜 Prior Art & Positioning

AetherBFT synthesizes established principles from:
- **PBFT** [Castro & Liskov, 1999]: Baseline 3-phase BFT safety and view change.
- **Zyzzyva** [Kotla et al., 2007]: Unanimous fast quorums ($3f+1$) and speculative execution.
- **EPaxos** [Moraru et al., 2013]: Decentralized dependency ordering (generalized to BFT with server-side QCs).
- **HotStuff** [Yin et al., 2019]: Linear $O(n)$ view-change and Pacemaker synchronization.
- **MVCC & Software Transactional Memory**: Branch-isolated tentative state trees.

---

## 📜 License
MIT License. Copyright &copy; 2026 Sahil Warke.
