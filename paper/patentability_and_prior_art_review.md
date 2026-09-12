# Patentability Analysis and Formal Patent Claims: AetherBFT Dual-Path Consensus Engine

**Filing Entity:** Sahil Warke  
**Date:** September 2026  
**Classification:** IPC G06F 9/46, G06F 11/14, H04L 9/32, H04L 67/1095  
**Title:** System and Method for Dual-Path Speculative Byzantine Fault Tolerant Consensus with Ephemeral Version Tree Invalidation in Geo-Distributed Replicated State Machines  

---

### I. Executive Summary and Inventive Step

This patentability specification defines the algorithmic mechanisms, mathematical invariants, and architecture of **AetherBFT**, a dual-path Byzantine Fault Tolerant (BFT) consensus engine. AetherBFT provides a structured, verifiable approach to reducing geo-distributed consensus latency by combining 1-RTT optimistic speculative execution for non-conflicting proposals with an ephemeral version-tree DAG for qualified $O(1)$ logical rollback, backed by a 2-phase Prepare-Commit recovery path and linear $O(n)$ Pacemaker view change.

#### Core Architectural Features
1. **Certified Dependency Context (CDC) Dispatcher:** A pre-dispatch conflict analyzer inspecting finite deterministic read/write sets ($T = \langle \text{tx\_id}, \text{client\_id}, R(T), W(T), \text{payload} \rangle$) against active in-flight transactions to isolate collisions prior to fast-path routing.
2. **Ephemeral MVCC Version-Tree DAG:** A tree-structured state representation executing tentative mutations in isolated branch frames, enabling qualified $O(1)$ logical rollback via pointer redirection without stalling cluster throughput.
3. **Strict Non-Linearizable Speculative Barrier:** A formal dual-view interface where tentative uncommitted mutations are strictly partitioned from linearizable reads, protecting external ACID query consistency.
4. **Autonomous Proof-of-Equivocation (PoE) Quarantine:** A cryptographic control-plane mechanism detecting dual-signature conflicts for identical sequence slots and isolating malicious peers within one modeled RTT without requiring economic token slashing.

---

### II. Prior Art Analysis and Non-Obviousness Distinctions

#### A. Comparison with Zyzzyva (US Patent 8,244,904 / Kotla et al., 2007)
* **Zyzzyva Approach:** Pioneered speculative execution where replicas respond directly to clients, committing in 1 RTT if all $3f+1$ agree. However, recovery from uncommitted states is client-driven and frequently triggers cluster-wide pauses and cascading rollbacks.
* **AetherBFT Distinction & Non-Obviousness:** AetherBFT maintains server-side Quorum Certificate assembly, eliminating client-driven recovery complexity. Speculative state is branch-isolated within ephemeral MVCC version trees, allowing localized $O(1)$ pointer redirection rollback without cascading across independent transactions.

#### B. Comparison with Egalitarian Paxos (EPaxos, Moraru et al., 2013)
* **EPaxos Approach:** Decentralized dependency ordering where any replica can propose, but dependency conflicts require complex graph cycle resolution and topological sorting off the critical path. EPaxos only handles Crash Fault Tolerance (CFT).
* **AetherBFT Distinction & Non-Obviousness:** AetherBFT operates under Byzantine Fault Tolerance ($f < n/3$) while avoiding complex graph cycle sorting through primary-sequenced Certified Dependency Contexts and formal quorum thresholds ($3f+1$ fast vs $2f+1$ slow).

#### C. Comparison with HotStuff (US Patent 11,237,927 / Yin et al., 2019)
* **HotStuff Approach:** Uses a 3-phase pipelined leader-driven consensus chain achieving linear view change complexity $O(n)$, but requires 3 RTTs for every transaction commit in steady state.
* **AetherBFT Distinction & Non-Obviousness:** AetherBFT introduces an optimistic dual-path engine that reduces modeled non-conflicting commit latency from 3 RTTs to 1 RTT, while adopting HotStuff's linear $O(n)$ Pacemaker view-change resilience for slow-path fallbacks.

#### D. Comparison with Google Spanner (Corbett et al., 2013)
* **Spanner Approach:** Relies on hardware GPS/atomic clocks (TrueTime) with artificial wait buffers ($\epsilon \approx 7$ ms) to guarantee external consistency, operating under 2-Phase Locking and Multi-Paxos (CFT).
* **AetherBFT Distinction & Non-Obviousness:** AetherBFT operates without specialized hardware atomic clocks, functions under Byzantine threat models, and achieves 1-RTT commits via cryptographic Quorum Certificates rather than physical wait-time buffers.

---

### III. Formal Patent Claims (12 Claims)

#### Independent Claims

##### Claim 1 (System Claim: Dual-Path Consensus System)
A prototype distributed computing system for Byzantine fault tolerant consensus across $n$ replica nodes with $f < n/3$ fault tolerance, comprising:
- A network interface communicatively coupling the $n$ replica nodes over an asynchronous wide-area network;
- One or more processors and memory storing instructions that, when executed, configure at least one processor as a consensus replica comprising:
  - A Certified Dependency Context manager configured to inspect read sets and write sets of incoming transactions against active in-flight transactions to determine fast-path eligibility;
  - A dual-path consensus router configured to route eligible non-conflicting transactions to an optimistic fast path requiring unanimous fast quorum certificates ($Q_{\text{fast}} = 3f + 1$) and to route conflicting transactions to a two-phase fallback consensus path requiring slow quorum certificates ($Q_{\text{slow}} = 2f + 1$);
  - An ephemeral multiversion concurrency control (MVCC) version-tree engine configured to execute fast-path transactions tentatively on isolated speculative branches and perform qualified logical rollback of equivocated or conflicting branches via $O(1)$ pointer redirection; and
  - A cryptographic verification engine configured to assemble digital signatures into quorum certificates and detect Byzantine equivocation.

##### Claim 2 (Method Claim: Dual-Path Consensus Process)
A computer-implemented method for achieving dual-path consensus across a plurality of geo-distributed replica nodes, comprising:
1. Receiving, by a primary replica node, a client transaction $T$ specifying a finite read set $R(T)$ and a write set $W(T)$;
2. Computing, by the primary replica, a Certified Dependency Context $D(T)$ indicating whether any active in-flight transaction conflicts with $T$;
3. If $D(T) = \emptyset$:
   - Broadcasting a proposal for $T$ along an optimistic fast path;
   - Executing, by each replica, transaction $T$ speculatively within an isolated ephemeral MVCC branch tagged with a tentative status;
   - Collecting Ed25519 digital signatures from all $n$ replicas to form a unanimous Fast Quorum Certificate in approximately one network round-trip time; and
   - Promoting the speculative branch to a canonical finalized state tree;
4. If $D(T) \neq \emptyset$ or upon failure to collect unanimous votes within a timeout threshold:
   - Rolling back the ephemeral speculative branch via $O(1)$ pointer redirection; and
   - Executing a two-phase Prepare-Commit consensus sequence collecting at least $2f+1$ votes to achieve finality in approximately two network round-trip times.

##### Claim 3 (Non-Transitory Computer-Readable Medium Claim)
A non-transitory computer-readable storage medium comprising instructions that, when executed by one or more processors, cause the processors to perform the dual-path consensus method of Claim 2.

#### Dependent Claims

##### Claim 4 (Certified Dependency Context Collision Filter)
The system of Claim 1, wherein two transactions $T_a$ and $T_b$ are determined to conflict if and only if:
$$(W(T_a) \cap (R(T_b) \cup W(T_b)) \neq \emptyset) \lor (W(T_b) \cap R(T_a) \neq \emptyset)$$
and wherein transactions exhibiting empty dependency contexts are guaranteed disjoint state space access.

##### Claim 5 (Speculative Non-Linearizability Barrier)
The system of Claim 1, further comprising a dual-view read application programming interface (API) wherein:
- A finalized read endpoint queries exclusively the canonical finalized state tree and returns strictly linearizable data; and
- A speculative read endpoint queries an active ephemeral branch and returns uncommitted tentative data tagged with an explicit non-linearizable status flag.

##### Claim 6 (Qualified O(1) Logical Rollback)
The method of Claim 2, wherein rolling back an ephemeral speculative branch comprises resetting an active branch head pointer to a parent frame without synchronous memory deallocation, and deferring physical memory reclamation to an asynchronous garbage collector.

##### Claim 7 (Proof of Equivocation Generation)
The system of Claim 1, wherein upon observing two valid digital signatures from an identical node identifier for distinct transaction digests at the same view and sequence slot:
$$\sigma_1 = \text{Sign}_{sk}(v, s, H(T_1)), \quad \sigma_2 = \text{Sign}_{sk}(v, s, H(T_2)), \quad H(T_1) \neq H(T_2)$$
the replica compiles a cryptographic Proof of Equivocation (PoE) and broadcasts the PoE to peer replicas.

##### Claim 8 (Peer Quarantine Control Reaction)
The method of Claim 2, further comprising isolating an offending replica node identified in a valid Proof of Equivocation by adding the node identifier to a persistent quarantine registry within one modeled round-trip time, wherein subsequent votes and proposals from the quarantined node are dropped without requiring economic token slashing.

##### Claim 9 (Pacemaker Linear View Change)
The system of Claim 1, wherein upon expiration of a timeout without achieving quorum finality, replicas broadcast view-change messages containing their highest certified Quorum Certificate ($\text{High-QC}$), achieving new leader synchronization with $O(n)$ message complexity.

##### Claim 10 (Simulated Network Delay Optimization)
The system of Claim 1, wherein simulated network propagation delay between replicas ranges between 2 ms and 190 ms, and the 1-RTT fast path reduces modeled protocol delay by approximately two round-trip times relative to conservative 3-phase consensus.

##### Claim 11 (Finite Deterministic Transaction Scope)
The method of Claim 2, wherein incoming transactions containing dynamic range scans or predicate locks are restricted from the fast path and routed directly to two-phase consensus to ensure deterministic conflict detection.

##### Claim 12 (Quorum Intersection Safety Invariant)
The system of Claim 1, wherein the intersection between any unanimous fast quorum of size $3f+1$ and any slow quorum of size $2f+1$ in a cluster of size $3f+1$ comprises at least $f+1$ honest replica nodes, mathematically precluding concurrent conflicting finality under complete network asynchrony.
