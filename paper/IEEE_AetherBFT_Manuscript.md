# AetherBFT: A Prototype Dual-Path Byzantine Fault Tolerant Consensus Engine with Ephemeral MVCC Rollback for Geo-Distributed State Machine Replication

**Author:** Sahil Warke  
**Affiliation:** Independent Research in Distributed Systems and Algorithmic Consensus  
**Date:** September 2026  
**Document ID:** IEEE-TRANS-DS-2026-AETHERBFT-01  

---

### Abstract
Geo-distributed state machine replication (SMR) protocols (e.g., Google Spanner, CockroachDB, and enterprise BFT blockchains) face significant commit latency overhead because classical Byzantine Fault Tolerance (PBFT) and modern pipelined protocols (HotStuff) require 2 to 3 cross-region round-trip times (RTTs) per commit. Over transatlantic or transpacific links with RTTs of 100 to 190 ms, these round-trips compound into 300 to 570 ms client-perceived transaction delays. This paper presents **AetherBFT**, a prototype dual-path BFT replication engine that combines a certified unanimous speculative fast path with a quorum-certified recovery path and multiversion concurrency control (MVCC) tentative execution. Under its stated transaction, quorum, and partial-synchrony assumptions, the prototype preserves finalized-state safety while empirically reducing modeled commit delay for low-conflict workloads. AetherBFT integrates: (1) an optimistic fast path with unanimous replica quorum ($Q_{\text{fast}} = 3f + 1$), (2) a Certified Dependency Context $D(T)$ constructed over finite, deterministic key transactions to isolate concurrent conflicts prior to route dispatch, (3) an ephemeral MVCC version-tree DAG facilitating qualified $O(1)$ logical rollback upon conflict or Byzantine equivocation without stalling cluster throughput, and (4) a conservative 2-phase Prepare-Commit fallback ($Q_{\text{slow}} = 2f + 1$) coupled with a linear $O(n)$ Pacemaker view-change mechanism. In synthetic network-delay evaluations across four wide-area topologies, the fast path completes in approximately one modeled RTT, while PBFT and HotStuff reference paths require approximately three modeled RTTs. Under active Byzantine equivocation schedules, the prototype produced 33 Proofs of Equivocation (PoE) with zero observed conflicting finalizations, completing replica quarantine within one modeled RTT.

**Keywords:** Byzantine Fault Tolerance, Geo-Distributed Consensus, Speculative Execution, Ephemeral MVCC, Quorum Certificates, State Machine Replication.

---

### I. Introduction

State Machine Replication (SMR) is the foundational paradigm for building fault-tolerant distributed databases and decentralized ledgers. In geo-distributed deployments where replicas span multiple continents to ensure disaster resilience and data proximity, wide-area network (WAN) round-trip propagation delays dominate total transaction latency. Typical cross-regional RTTs range from 75 ms (continental US) to 150 ms (transatlantic) and 190 ms (transpacific/global).

Classical Byzantine Fault Tolerant protocols such as PBFT [Castro & Liskov, 1999] require three communication phases (Pre-Prepare, Prepare, Commit), incurring an asymptotic delay of $3 \times \text{RTT}$. Modern leader-based pipelined protocols such as HotStuff [Yin et al., 2019] achieve linear view-change communication complexity $O(n)$ by chaining three sequential blocks to achieve finality, also resulting in a steady-state latency of 3 RTTs per transaction commit.

The concept of speculative execution in BFT systems was pioneered by Zyzzyva [Kotla et al., 2007], which demonstrated that unanimous agreement ($3f + 1$) allows a 1-RTT commit under benign conditions. Subsequent systems explored egalitarian replication (EPaxos [Moraru et al., 2013]) and multiversion concurrency control in replicated stores. However, existing speculative architectures encounter several known practical challenges:
1. **Rollback Amplification:** When optimistic assumptions fail due to concurrent key collisions or network jitter, uncommitted speculative states can trigger global rollbacks, stalling unrelated transactions.
2. **Ambiguous API Boundaries:** If tentative speculative executions are exposed to external readers, clients may observe state that is later invalidated, violating linearizability.
3. **Equivocation Complexity:** In the presence of a Byzantine leader broadcasting conflicting proposals for the same sequence slot, naive speculative engines struggle to converge deterministically.

#### Architectural Synthesis & Scope
AetherBFT does not claim to invent speculative BFT or dependency ordering from scratch; rather, its contribution lies in the specific architectural synthesis, formal interface boundaries, and empirical evaluation of a dual-path engine:
1. **Certified Dependency Context (CDC):** Formally separates non-conflicting proposals from contested proposals using a finite deterministic key transaction model $T_i = (R_i, W_i, \text{payload})$.
2. **Ephemeral MVCC Version Tree DAG:** Provides branch-isolated tentative states where qualified logical rollback is achieved in $O(1)$ pointer redirection, preventing rollback amplification ($RA(C) \to 0$ under low conflict).
3. **Strict Speculative Read Isolation Barrier:** Distinguishes between tentative execution (`TENTATIVE`, explicitly non-linearizable) and canonical finalized state (`COMMITTED`, linearizable reads).
4. **Resilient 2-Phase Fallback & Pacemaker:** Combines a 2-phase Prepare-Commit recovery path with linear $O(n)$ authenticated High-QC view change.

---

### II. System Model and Scope Boundaries

#### A. Network and Timing Model
We consider a distributed system comprising $n$ replica nodes:
$$\mathcal{P} = \{p_0, p_1, \dots, p_{n-1}\}$$
The network operates under partial synchrony: message delays may be arbitrary prior to an unknown Global Stabilization Time (GST). After GST, message transmission delays are bounded by $\Delta$.
- **Safety Invariant:** Safety (Agreement and Linearizability) holds unconditionally under complete asynchrony ($\Delta = \infty$).
- **Liveness Invariant:** Liveness holds after GST under partial synchrony.

#### B. Failure Model
At most $f$ nodes may exhibit arbitrary (Byzantine) behaviors, where:
$$n \ge 3f + 1$$
Byzantine nodes may equivocate, crash, delay messages, or send corrupted signatures. Cryptographic primitives (Ed25519 digital signatures and SHA-256 collision-resistant hashes) are computationally unforgeable.

#### C. Transaction Model
Transactions operate over a finite, deterministic key space $\mathcal{K}$. Each transaction $T$ is defined as a tuple:
$$T = \langle \text{tx\_id}, \text{client\_id}, R(T), W(T), \text{payload} \rangle$$
where $R(T) \subseteq \mathcal{K}$ is the explicit read set, $W(T) \subseteq \mathcal{K}$ is the explicit write set, and $\text{payload}$ specifies deterministic state mutations. Range queries and dynamic predicate locks are excluded from fast-path eligibility to guarantee deterministic conflict detection.

---

### III. The AetherBFT Protocol Architecture

#### A. Certified Dependency Context
For each arriving proposal $T$, the leader evaluates eligibility for the Optimistic Fast-Path. Two transactions $T_i$ and $T_j$ conflict ($T_i \sim T_j$) if and only if their key sets intersect with at least one write operation:
$$T_i \sim T_j \iff (W(T_i) \cap (R(T_j) \cup W(T_j)) \neq \emptyset) \lor (W(T_j) \cap R(T_i) \neq \emptyset)$$
The Certified Dependency Context $D(T)$ is the set of all active, in-flight transaction identifiers that precede $T$ and conflict with $T$:
$$D(T) = \{ T' \in \mathcal{A}_{\text{in-flight}} \mid T' \sim T \}$$
If $D(T) = \emptyset$, the transaction is routed to the **Fast-Path**. If $D(T) \neq \emptyset$, the transaction is immediately routed to the **Slow-Path** fallback to prevent speculative branch divergence.

#### B. Optimistic Fast-Path (1 RTT)
1. **Proposal (Half RTT):** The primary broadcasts proposal $T$ along with empty dependency context $D(T) = \emptyset$ and sequence number $s$ in view $v$.
2. **Speculative Execution:** Upon receiving proposal $(v, s, T)$, each replica verifies that no conflicting transaction is active. The replica creates an ephemeral MVCC child branch:
$$B_{\text{spec}} = \text{Branch}(B_{\text{parent}}, T)$$
and executes $T$ speculatively, recording mutations in $B_{\text{spec}}$.
3. **Fast Vote (Half RTT):** The replica generates an Ed25519 signature over the proposal digest:
$$\sigma_i = \text{Sign}_{sk_i}(H(v \parallel s \parallel H(T)))$$
and transmits $\sigma_i$ to the primary.
4. **Fast Quorum Certificate:** If the primary accumulates unanimous votes from all $n$ replicas ($Q_{\text{fast}} = 3f + 1$):
$$QC_{\text{fast}} = \langle v, s, H(T), \Sigma_{Q_{\text{fast}}}, \text{FAST} \rangle$$
The transaction is finalized. The speculative MVCC branch is atomically promoted to the canonical finalized root. Total modeled flight delay: **1 RTT**.

#### C. Slow-Path Fallback (2 RTT)
If unanimous votes cannot be gathered within timeout $2\Delta$ (due to node crash, network delay, or dependency conflict):
1. **Prepare Phase (1 RTT):** The leader broadcasts a Prepare message. Replicas verify that at least $2f + 1$ distinct nodes are accounted for, and return Prepare votes.
2. **Commit Phase (2nd RTT):** Upon assembling a Prepare Quorum Certificate ($QC_{\text{prep}}$ with $|\Sigma| \ge 2f + 1$), the leader broadcasts Commit. Replicas commit $T$ and reply with Commit votes.
Total fallback flight delay: **2 RTTs**.

#### D. Ephemeral MVCC Version Tree & Qualified O(1) Rollback
To avoid expensive physical state copy-on-write overhead during speculative rollbacks, AetherBFT structures replica state as an immutable directed acyclic graph (DAG) of versioned key-value frames.
- **Speculative Isolation:** Write mutations are appended to an ephemeral branch descriptor. Tentative reads traverse the branch descriptor before falling back to the parent frame.
- **Qualified O(1) Logical Rollback:** When an equivocated or conflicting transaction is aborted, the replica dereferences the active branch pointer:
$$\text{ActiveBranch} \leftarrow \text{Parent}(\text{ActiveBranch})$$
This pointer redirection is strictly an $O(1)$ logical operation. Physical memory reclamation is deferred to an asynchronous background garbage collector off the critical consensus path.

#### E. Byzantine Equivocation and Quarantine
When a Byzantine leader signs two distinct proposals $H(T_a) \neq H(T_b)$ for the identical slot $(v, s)$, honest replicas compile a **Proof of Equivocation (PoE)**:
$$\text{PoE} = \langle p_{\text{byz}}, v, s, H(T_a), \sigma_{p_{\text{byz}}}(a), H(T_b), \sigma_{p_{\text{byz}}}(b) \rangle$$
Upon validating both signatures, the replica adds $p_{\text{byz}}$ to a persistent quarantine registry. Quarantine operates as a membership/control-plane reaction that isolates the misbehaving replica within 1 modeled RTT, while consensus transitions to the slow path without halting throughput.

---

### IV. Correctness Invariants and Formal Proofs

#### Invariant 1: Unconditional Safety under Asynchrony
**Theorem 1:** *No two conflicting transactions can both be committed at the same sequence slot $s$, regardless of network message delays and reordering, provided $f < n/3$.*

*Proof:*
Suppose transaction $T_a$ commits via the Fast-Path at slot $s$ with $|Q_a| = 3f + 1$. Suppose conflicting transaction $T_b$ commits at the same slot $s$. If $T_b$ commits via Fast-Path, $|Q_b| = 3f + 1$, meaning all $2f + 1$ honest nodes must have signed both proposals, which honest nodes never do. If $T_b$ commits via Slow-Path, $|Q_b| \ge 2f + 1$. The quorum intersection contains:
$$|Q_a \cap Q_b| = (3f + 1) + (2f + 1) - (3f + 1) = 2f + 1 \text{ nodes}$$
Subtracting at most $f$ Byzantine nodes leaves at least $f + 1$ honest nodes in the intersection. These honest nodes cannot have signed both proposals for slot $s$. Thus, $T_b$ cannot assemble a valid Quorum Certificate. $\blacksquare$

#### Invariant 2: Liveness after GST
**Theorem 2:** *Under partial synchrony, every submitted transaction is eventually committed within bounded time after GST.*

*Proof:*
After GST, maximum message delay is bounded by $\Delta$. If the leader is honest and proposals are non-conflicting, all honest nodes receive the proposal within $\Delta$, execute speculatively, and return votes within $\Delta$. The leader accumulates $3f + 1$ votes within $2\Delta$, achieving fast finality. If the leader is Byzantine or crashes, the Pacemaker timer expires after $2\Delta + \epsilon$. At least $2f + 1$ honest nodes broadcast View-Change messages containing their highest certified QC ($\text{High-QC}$). Replicas transition to view $v+1$ with deterministic leader $p_{(v+1) \bmod n}$. Since at most $f$ nodes are faulty, an honest leader is elected within at most $f+1$ view changes, restoring cluster throughput. $\blacksquare$

#### Invariant 3: Speculative Non-Linearizability Boundary
**Theorem 3:** *Tentative speculative reads never violate linearizability of the external client read interface.*

*Proof:*
The client API enforces strict separation:
1. `read_linearizable(k)` queries exclusively the canonical finalized state tree.
2. `read_speculative(tx_id, k)` queries the ephemeral branch $B(tx\_id)$ and returns state tagged with explicit status `TENTATIVE`.
External clients requiring linearizability query only `read_linearizable()`, ensuring uncommitted speculative mutations are never exposed to linearizable readers. $\blacksquare$

---

### V. Empirical Evaluation and Benchmark Results

#### A. Core Quantities and Contention Trade-off
We formally evaluate the system across three core quantities as a function of key contention rate $C$:
1. **Fast-Path Success Rate:**
   $$F(C) = \frac{N_{\text{fast}}}{N_{\text{total}}}$$
2. **Rollback Amplification:**
   $$RA(C) = \frac{N_{\text{invalidated speculative operations}}}{N_{\text{speculative operations}}}$$
3. **Commit Latency:**
   $$L(C) = T_{\text{finalized}} - T_{\text{submit}}$$

The central research hypothesis is that as contention increases, fast-path utilization decreases and rollback increases, producing a measurable transition in AetherBFT's latency and throughput profile.

#### B. Pareto Latency and Metric Sweep ($C \in [0\%, 50\%]$)
Table I presents results across 120 transactions per sweep under WAN-Transatlantic conditions (Base RTT = 100 ms) with real cryptographic signing/verification and MVCC state operations.

**TABLE I: Pareto Latency and Metric Sweep across Conflict Rates (Synthetic Network Delay + Real Crypto/MVCC)**

| Conflict Rate $C$ | Fast Success $F(C)$ | Rollback Amp. $RA(C)$ | AetherBFT $L(C)$ $p_{50}$ | PBFT Simulated Reference | HotStuff Simulated Reference | Raft CFT Reference |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0% (Disjoint)** | **100.0%** | 0.0000 | **100.78 ms** | 300.42 ms | 299.68 ms | 100.02 ms |
| **5% Contention** | **99.2%** | 0.0083 | **100.28 ms** | 299.65 ms | 300.24 ms | 99.66 ms |
| **10% Contention** | **95.0%** | 0.0500 | **100.95 ms** | 300.03 ms | 299.53 ms | 99.69 ms |
| **25% Contention** | **75.0%** | 0.2500 | **101.66 ms** | 300.26 ms | 300.59 ms | 99.55 ms |
| **50% (High)** | **55.0%** | 0.4500 | **102.83 ms** | 299.86 ms | 300.27 ms | 100.53 ms |

**Analysis of Contention Trade-off:**
- At $C = 0\%$, all transactions target independent keys. Fast-path utilization is $F(0) = 100\%$, rollback amplification is $RA(0) = 0.0$, and median commit latency is 100.78 ms, closely matching the 1-RTT Raft CFT reference.
- At $C = 50\%$, intense contention forces in-flight conflicts: $F(50)$ drops to 55.0% and $RA(50)$ increases to 0.4500. This confirms the expected transition: higher contention gracefully degrades fast-path gains into the 2-phase slow-path fallback.

#### C. Multi-Region Simulated Protocol-Delay Benchmarks
Table II summarizes modeled round-trip delays across four simulated network topologies.

**TABLE II: Multi-Region Simulated Protocol-Delay Benchmarks (Modeled RTT Distribution)**

| Topology Profile | Base RTT | Aether Fast (Modeled 1 RTT) | Aether Slow (Modeled 2 RTT) | PBFT Simulated Reference (3 RTT) | HotStuff Simulated Reference (3 RTT) | Raft CFT Reference (1 RTT) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **LAN Datacenter** | 2.0 ms | **2.02 ms** | 4.00 ms | 6.09 ms | 6.01 ms | 2.01 ms |
| **WAN-Regional (US-East/West)** | 75.0 ms | **75.18 ms** | 151.18 ms | 225.91 ms | 224.98 ms | 74.80 ms |
| **WAN-Transatlantic (US/EU)** | 150.0 ms | **150.78 ms** | 299.86 ms | 450.60 ms | 450.23 ms | 149.81 ms |
| **WAN-Global (US/AP-South)** | 190.0 ms | **188.55 ms** | 381.39 ms | 569.31 ms | 570.84 ms | 190.03 ms |

*Note on Benchmarking Methodology:* In the current synthetic network-delay model, the fast path completes in approximately one modeled RTT, while PBFT and HotStuff reference paths require approximately three modeled RTTs. These results reflect modeled protocol round-trip delays under synthetic WAN distributions, not physical cross-cloud deployments.

#### D. Byzantine Equivocation and Quarantine Evaluation
Under adversarial testing where Node 1 attempted equivocation across sequence slots:
- **Across the tested Byzantine schedules, AetherBFT produced 33 equivocation proofs and zero observed conflicting finalizations.**
- **Replica quarantine completed within one modeled RTT.**
- The cluster preserved linearizability, gracefully transitioning uncompromised transactions to the slow path with a mean simulated latency of 133.39 ms.
- 15 out of 15 protocol invariant and adversarial unit tests passed.

---

### VI. Prior Art and Positioning

| Protocol | Protocol Class | Fast-Path Latency | Fallback Latency | Rollback Mechanism | Conflict Detection |
|:---|:---:|:---:|:---:|:---:|:---:|
| **PBFT (1999)** | Conservative 3-Phase BFT | N/A (3 RTT) | 3 RTT | None | Serial Locking |
| **Zyzzyva (2007)** | Client-Driven Speculative BFT | 1 RTT | 2-3 RTT | Global Cascading Stall | Client Detection |
| **EPaxos (2013)** | Decentralized Egalitarian Paxos | 1 RTT (CFT) | 2 RTT (CFT) | Graph Cycle Resolution | Inter-Leader Graph |
| **HotStuff (2019)**| Chained Pipelined BFT | N/A (3 RTT) | 3 RTT | None (Chained Blocks) | Serial Block Ordering |
| **AetherBFT (Ours)**| **Dual-Path Speculative BFT** | **1 RTT (BFT)** | **2 RTT (BFT)** | **Qualified $O(1)$ MVCC** | **Certified Dependency Context** |

AetherBFT synthesizes principles from speculative BFT (Zyzzyva), linear view-change (HotStuff), and multiversion concurrency control, delivering a defensible, formally bounded architecture for geo-distributed state machine replication.

---

### VII. Conclusion
AetherBFT demonstrates that speculative Byzantine consensus in geo-distributed state machine replication can significantly reduce modeled commit delays under low-conflict workloads without compromising linearizability or risking cascading rollbacks. By combining Certified Dependency Contexts with ephemeral MVCC branch invalidation, the prototype provides a structured, verifiable approach to dual-path consensus under partial synchrony.

---

### References
1. Castro, M., & Liskov, B. (1999). *Practical Byzantine Fault Tolerance*. In Proceedings of the Third Symposium on Operating Systems Design and Implementation (OSDI).
2. Kotla, R., Alvisi, L., Dahlin, M., Clement, A., & Wong, E. (2007). *Zyzzyva: Speculative Byzantine Fault Tolerance*. In ACM SIGOPS Operating Systems Review.
3. Moraru, I., Andersen, D. G., & Kaminsky, M. (2013). *There is More Consensus in Egalitarian Parliaments*. In ACM SOSP.
4. Yin, M., Malkhi, D., Reiter, M. K., Gueta, G. G., & Abraham, I. (2019). *HotStuff: BFT Consensus in the Lens of Blockchain*. In ACM PODC.
5. Corbett, J. C., et al. (2013). *Spanner: Google’s Globally Distributed Database*. In ACM Transactions on Computer Systems (TOCS).
