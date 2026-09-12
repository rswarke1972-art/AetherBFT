/**
 * AetherBFT: 60 FPS Interactive Simulation Engine
 * Visualizes Dual-Path Consensus, Ephemeral MVCC Version Trees,
 * Byzantine Equivocation Quarantine, and Dynamic Geo-Latency Topologies.
 */

(function() {
  'use strict';

  // --- Configuration & State ---
  const state = {
    conflictRate: 0.10,
    topology: 'wan-transatlantic',
    baseRttMs: 150,
    isByzantineActive: false,
    isStreaming: false,
    streamTimer: null,

    // Metrics counters
    totalProposed: 0,
    fastCommits: 0,
    slowCommits: 0,
    invalidatedOps: 0,
    speculativeOps: 0,
    byzQuarantines: 0,

    // Sliding window of recent commits for HUD
    recentTransactions: [],

    // Nodes in the cluster
    nodes: [
      { id: 'node_0', name: 'US-East (Virginia)', role: 'LEADER', x: 230, y: 145, color: '#06b6d4', status: 'HONEST', qVotes: 0 },
      { id: 'node_1', name: 'US-West (Oregon)', role: 'REPLICA', x: 135, y: 130, color: '#10b981', status: 'HONEST', qVotes: 0 },
      { id: 'node_2', name: 'EU-Central (Frankfurt)', role: 'REPLICA', x: 510, y: 120, color: '#10b981', status: 'HONEST', qVotes: 0 },
      { id: 'node_3', name: 'AP-South (Singapore)', role: 'REPLICA', x: 720, y: 250, color: '#10b981', status: 'HONEST', qVotes: 0 }
    ],

    // Active in-flight packet animations
    packets: [],

    // Particle ripples for QC formation
    ripples: [],

    // MVCC DAG visualizer state
    dagNodes: [
      { id: 'root_0', seq: 0, x: 60, y: 90, type: 'FINALIZED', label: 'Genesis' }
    ],
    dagEdges: []
  };

  // Topologies config
  const TOPOLOGIES = {
    'lan': { name: 'LAN Datacenter', rtt: 2, speedMultiplier: 2.5 },
    'wan-regional': { name: 'WAN-Regional (US-East / West)', rtt: 75, speedMultiplier: 1.5 },
    'wan-transatlantic': { name: 'WAN-Transatlantic (US / EU)', rtt: 150, speedMultiplier: 1.0 },
    'wan-global': { name: 'WAN-Global (US / AP-South)', rtt: 190, speedMultiplier: 0.85 }
  };

  // DOM Elements
  const geoCanvas = document.getElementById('geoCanvas');
  const geoCtx = geoCanvas.getContext('2d');
  const dagCanvas = document.getElementById('dagCanvas');
  const dagCtx = dagCanvas.getContext('2d');

  const sliderConflict = document.getElementById('slider-conflict');
  const valConflict = document.getElementById('val-conflict');
  const selectTopology = document.getElementById('select-topology');
  const toggleByzantine = document.getElementById('toggle-byzantine');
  const btnInjectTx = document.getElementById('btn-inject-tx');
  const btnConflictTx = document.getElementById('btn-conflict-tx');
  const btnToggleTraffic = document.getElementById('btn-toggle-traffic');
  const btnReset = document.getElementById('btn-reset');
  const btnClearLog = document.getElementById('btn-clear-log');

  const hudStatus = document.getElementById('hud-status');
  const hudFps = document.getElementById('hud-fps');
  const routeIndicator = document.getElementById('route-indicator');
  const statFc = document.getElementById('stat-fc');
  const statLatency = document.getElementById('stat-latency');
  const statRa = document.getElementById('stat-ra');
  const statCommits = document.getElementById('stat-commits');
  const odoFast = document.getElementById('odo-fast');
  const odoSlow = document.getElementById('odo-slow');
  const odoByz = document.getElementById('odo-byz');
  const eventLog = document.getElementById('event-log');

  // Benchmark tabs
  const tabButtons = document.querySelectorAll('.bench-tab');
  const tabPanes = document.querySelectorAll('.tab-pane');

  // FPS tracking
  let lastFrameTime = performance.now();
  let frameCount = 0;
  let fpsTimer = 0;

  // --- Logging Helper ---
  function logEvent(text, type = 'sys') {
    const d = new Date();
    const ts = d.toTimeString().split(' ')[0] + '.' + String(d.getMilliseconds()).padStart(3, '0');
    const el = document.createElement('div');
    el.className = `log-entry log-${type}`;
    el.textContent = `[${ts}] ${text}`;
    eventLog.appendChild(el);
    eventLog.scrollTop = eventLog.scrollHeight;
  }

  // --- Canvas Coordinate Scaling ---
  function initCanvasDPI(canvas, ctx, width, height) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(dpr, dpr);
  }

  initCanvasDPI(geoCanvas, geoCtx, 900, 420);
  initCanvasDPI(dagCanvas, dagCtx, 900, 180);

  // --- Event Listeners ---
  sliderConflict.addEventListener('input', (e) => {
    state.conflictRate = parseInt(e.target.value) / 100;
    valConflict.textContent = `${e.target.value}%`;
    logEvent(`Dependency conflict rate reconfigured to C = ${e.target.value}%`, 'sys');
  });

  selectTopology.addEventListener('change', (e) => {
    const val = e.target.value;
    state.topology = val;
    state.baseRttMs = TOPOLOGIES[val].rtt;
    logEvent(`Topology profile changed to ${TOPOLOGIES[val].name} (Base RTT = ${state.baseRttMs} ms)`, 'sys');
    updateHUD();
  });

  toggleByzantine.addEventListener('change', (e) => {
    state.isByzantineActive = e.target.checked;
    const node1 = state.nodes[1];
    if (state.isByzantineActive) {
      node1.status = 'BYZANTINE';
      node1.color = '#ef4444';
      logEvent(`ADVERSARY INJECTED: Node 1 (US-West) programmed to equivocate proposals.`, 'byz');
    } else {
      node1.status = 'HONEST';
      node1.color = '#10b981';
      logEvent(`Node 1 (US-West) restored to certified honest state.`, 'sys');
    }
  });

  btnInjectTx.addEventListener('click', () => {
    proposeTransaction(false);
  });

  btnConflictTx.addEventListener('click', () => {
    proposeTransaction(true);
  });

  btnToggleTraffic.addEventListener('click', () => {
    state.isStreaming = !state.isStreaming;
    if (state.isStreaming) {
      btnToggleTraffic.textContent = '⏹ Stop Traffic';
      btnToggleTraffic.classList.add('btn-warning');
      state.streamTimer = setInterval(() => {
        const isConflict = Math.random() < state.conflictRate;
        proposeTransaction(isConflict);
      }, 400);
      logEvent('Streaming synthetic geo-distributed traffic at ~2.5 tx/sec.', 'fast');
    } else {
      btnToggleTraffic.textContent = '▶ Stream Traffic (10 tx/s)';
      btnToggleTraffic.classList.remove('btn-warning');
      clearInterval(state.streamTimer);
      state.streamTimer = null;
      logEvent('Traffic stream halted.', 'sys');
    }
  });

  btnReset.addEventListener('click', () => {
    state.totalProposed = 0;
    state.fastCommits = 0;
    state.slowCommits = 0;
    state.invalidatedOps = 0;
    state.speculativeOps = 0;
    state.byzQuarantines = 0;
    state.recentTransactions = [];
    state.packets = [];
    state.ripples = [];
    state.dagNodes = [{ id: 'root_0', seq: 0, x: 60, y: 90, type: 'FINALIZED', label: 'Genesis' }];
    state.dagEdges = [];
    logEvent('System state and telemetry metrics reset.', 'sys');
    updateHUD();
  });

  btnClearLog.addEventListener('click', () => {
    eventLog.innerHTML = '';
    logEvent('Event stream cleared.', 'sys');
  });

  // Tab switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.getAttribute('data-tab');
      document.getElementById(`pane-${target}`).classList.add('active');
    });
  });

  // --- Consensus Transaction Execution ---
  function proposeTransaction(forceConflict) {
    state.totalProposed++;
    state.speculativeOps++;
    const seq = state.totalProposed;
    const txId = `tx_${seq}`;
    const key = forceConflict ? 'shared_vault' : `acc_${seq}`;

    const isConflict = forceConflict || (Math.random() < state.conflictRate && seq > 1);
    const isByzAttack = state.isByzantineActive && (seq % 2 === 0);

    // Leader proposes
    const leader = state.nodes[0];

    if (!isConflict && !isByzAttack) {
      // 1. FAST PATH (1 RTT)
      routeIndicator.textContent = 'OPTIMISTIC FAST PATH (1 RTT)';
      routeIndicator.className = 'route-fast';
      logEvent(`[${txId}] Proposing on disjoint key ${key}. Initiating Fast-Path (Q_fast=4).`, 'fast');

      // Add tentative DAG node
      const parentDag = state.dagNodes[state.dagNodes.length - 1];
      const dagX = Math.min(840, 60 + seq * 45);
      const dagY = 90;
      const tentativeNode = { id: `tent_${seq}`, seq, x: dagX, y: dagY, type: 'TENTATIVE', label: txId };
      state.dagNodes.push(tentativeNode);
      state.dagEdges.push({ from: parentDag.id, to: tentativeNode.id, type: 'SPECULATIVE' });

      // Packets from Leader to Replicas
      state.nodes.slice(1).forEach((target, i) => {
        sendPacket(leader, target, '#10b981', 'PROPOSE_FAST', () => {
          // Replica votes back to Leader
          sendPacket(target, leader, '#10b981', 'VOTE_FAST', () => {
            if (i === 0) {
              // Unanimous fast quorum reached!
              state.fastCommits++;
              state.recentTransactions.push({ fast: true, rtt: state.baseRttMs });
              tentativeNode.type = 'FINALIZED';
              addRipple(leader.x, leader.y, '#10b981');
              logEvent(`[${txId}] Quorum Certificate formed (4/4 votes). Fast commit finalized in 1 RTT (${state.baseRttMs} ms)!`, 'qc');
              updateHUD();
            }
          });
        });
      });
    } else if (isByzAttack) {
      // 2. BYZANTINE EQUIVOCATION ATTACK
      routeIndicator.textContent = 'BYZANTINE EQUIVOCATION DETECTED (QUARANTINED)';
      routeIndicator.className = 'route-byz';
      logEvent(`[${txId}] Node 1 (US-West) attempted conflicting signature equivocation!`, 'byz');

      const byzNode = state.nodes[1];
      sendPacket(leader, byzNode, '#ef4444', 'PROPOSE_SPLIT', () => {
        sendPacket(byzNode, leader, '#ef4444', 'EQUIVOCATION_EVIDENCE', () => {
          // Honest leader validates Proof of Equivocation (PoE)
          state.byzQuarantines++;
          addRipple(byzNode.x, byzNode.y, '#ef4444');
          logEvent(`[SECURITY AUDIT] Proof of Equivocation verified for Node 1. Quarantined from consensus!`, 'byz');

          // Fallback to slow path
          fallbackToSlowPath(txId, seq, true);
        });
      });
    } else {
      // 3. SLOW PATH FALLBACK (2 RTT)
      routeIndicator.textContent = 'SLOW PATH FALLBACK (2 RTT) &bull; MVCC ROLLBACK';
      routeIndicator.className = 'route-slow';
      state.invalidatedOps++;
      logEvent(`[${txId}] Dependency collision on ${key}! Branch rolled back in O(1). Switching to Slow-Path.`, 'slow');

      // Add rolled back speculative DAG branch
      const parentDag = state.dagNodes[state.dagNodes.length - 1];
      const dagX = Math.min(840, 60 + seq * 45);
      const abortedNode = { id: `abort_${seq}`, seq, x: dagX, y: 40, type: 'ABORTED', label: `${txId} (Aborted)` };
      state.dagNodes.push(abortedNode);
      state.dagEdges.push({ from: parentDag.id, to: abortedNode.id, type: 'ABORTED' });

      fallbackToSlowPath(txId, seq, false);
    }
  }

  function fallbackToSlowPath(txId, seq, isByz) {
    const leader = state.nodes[0];
    const honestReplicas = state.nodes.slice(2); // Nodes 2 and 3

    // Phase 1: Prepare (1 RTT)
    honestReplicas.forEach(target => {
      sendPacket(leader, target, '#f59e0b', 'PREPARE', () => {
        sendPacket(target, leader, '#f59e0b', 'PREPARE_VOTE', () => {
          // Phase 2: Commit (2nd RTT)
          sendPacket(leader, target, '#06b6d4', 'COMMIT', () => {
            sendPacket(target, leader, '#06b6d4', 'COMMIT_ACK', () => {
              state.slowCommits++;
              const slowRtt = state.baseRttMs * 2;
              state.recentTransactions.push({ fast: false, rtt: slowRtt });

              // Canonical finalized DAG node on main spine
              const parentDag = state.dagNodes[state.dagNodes.length - 2] || state.dagNodes[0];
              const dagX = Math.min(840, 60 + seq * 45);
              const committedNode = { id: `slow_${seq}`, seq, x: dagX, y: 90, type: 'FINALIZED', label: txId };
              state.dagNodes.push(committedNode);
              state.dagEdges.push({ from: parentDag.id, to: committedNode.id, type: 'FINALIZED' });

              addRipple(leader.x, leader.y, '#f59e0b');
              logEvent(`[${txId}] Slow-Path 2-Phase Commit QC assembled (Q_slow=3). Finalized in 2 RTTs (${slowRtt} ms).`, 'qc');
              updateHUD();
            });
          });
        });
      });
    });
  }

  function sendPacket(fromNode, toNode, color, type, onComplete) {
    const speedMult = TOPOLOGIES[state.topology].speedMultiplier;
    state.packets.push({
      fromX: fromNode.x,
      fromY: fromNode.y,
      toX: toNode.x,
      toY: toNode.y,
      x: fromNode.x,
      y: fromNode.y,
      color,
      progress: 0,
      speed: 0.02 * speedMult,
      type,
      onComplete
    });
  }

  function addRipple(x, y, color) {
    state.ripples.push({ x, y, radius: 10, maxRadius: 50, alpha: 1.0, color });
  }

  // --- Telemetry HUD Calculation ---
  function updateHUD() {
    const total = state.fastCommits + state.slowCommits;
    statCommits.textContent = total;
    odoFast.textContent = state.fastCommits;
    odoSlow.textContent = state.slowCommits;
    odoByz.textContent = state.byzQuarantines;

    // F(C) rate
    const fc = total > 0 ? (state.fastCommits / total) * 100 : 100;
    statFc.textContent = `${fc.toFixed(1)}%`;

    // RA Rollback Amplification
    const ra = state.speculativeOps > 0 ? (state.invalidatedOps / state.speculativeOps) : 0;
    statRa.textContent = ra.toFixed(3);

    // p50 latency estimate
    if (state.recentTransactions.length > 0) {
      const recent = state.recentTransactions.slice(-20);
      const sum = recent.reduce((acc, t) => acc + t.rtt, 0);
      const mean = sum / recent.length;
      statLatency.textContent = `${Math.round(mean)} ms`;
    } else {
      statLatency.textContent = `${state.baseRttMs} ms`;
    }
  }

  // --- Animation Loop ---
  function animate(now) {
    // FPS counter
    frameCount++;
    if (now - fpsTimer >= 1000) {
      const fps = (frameCount * 1000) / (now - fpsTimer);
      hudFps.textContent = `${fps.toFixed(1)} FPS`;
      frameCount = 0;
      fpsTimer = now;
    }

    renderGeoNetwork();
    renderMVCCDAG();

    requestAnimationFrame(animate);
  }

  // --- Render Geo Network ---
  function renderGeoNetwork() {
    geoCtx.clearRect(0, 0, 900, 420);

    // 1. Draw World Map stylized background lines
    drawMapGrid(geoCtx);

    // 2. Draw Network Interconnects (Edges)
    const leader = state.nodes[0];
    state.nodes.slice(1).forEach(target => {
      geoCtx.beginPath();
      geoCtx.moveTo(leader.x, leader.y);
      geoCtx.lineTo(target.x, target.y);
      geoCtx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
      geoCtx.lineWidth = 1.5;
      geoCtx.setLineDash([4, 4]);
      geoCtx.stroke();
      geoCtx.setLineDash([]);
    });

    // 3. Update & Draw Packets
    for (let i = state.packets.length - 1; i >= 0; i--) {
      const p = state.packets[i];
      p.progress += p.speed;
      p.x = p.fromX + (p.toX - p.fromX) * p.progress;
      p.y = p.fromY + (p.toY - p.fromY) * p.progress;

      // Glow trail
      geoCtx.beginPath();
      geoCtx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      geoCtx.fillStyle = p.color;
      geoCtx.shadowColor = p.color;
      geoCtx.shadowBlur = 12;
      geoCtx.fill();
      geoCtx.shadowBlur = 0;

      if (p.progress >= 1.0) {
        state.packets.splice(i, 1);
        if (p.onComplete) p.onComplete();
      }
    }

    // 4. Update & Draw Ripples
    for (let i = state.ripples.length - 1; i >= 0; i--) {
      const r = state.ripples[i];
      r.radius += 1.5;
      r.alpha -= 0.025;

      geoCtx.beginPath();
      geoCtx.arc(r.x, r.y, r.radius, 0, Math.PI * 2);
      geoCtx.strokeStyle = r.color;
      geoCtx.globalAlpha = Math.max(0, r.alpha);
      geoCtx.lineWidth = 2;
      geoCtx.stroke();
      geoCtx.globalAlpha = 1.0;

      if (r.alpha <= 0) {
        state.ripples.splice(i, 1);
      }
    }

    // 5. Draw Regional Replica Nodes
    state.nodes.forEach(node => {
      const isQuarantined = node.status === 'BYZANTINE';

      // Node aura
      const grad = geoCtx.createRadialGradient(node.x, node.y, 4, node.x, node.y, 22);
      grad.addColorStop(0, node.color);
      grad.addColorStop(1, 'transparent');
      geoCtx.beginPath();
      geoCtx.arc(node.x, node.y, 22, 0, Math.PI * 2);
      geoCtx.fillStyle = grad;
      geoCtx.fill();

      // Node core
      geoCtx.beginPath();
      geoCtx.arc(node.x, node.y, 10, 0, Math.PI * 2);
      geoCtx.fillStyle = '#060913';
      geoCtx.fill();
      geoCtx.strokeStyle = node.color;
      geoCtx.lineWidth = 3;
      geoCtx.stroke();

      // Label & Role Tag
      geoCtx.fillStyle = '#f8fafc';
      geoCtx.font = '600 12px Plus Jakarta Sans';
      geoCtx.fillText(node.name, node.x - 40, node.y - 18);

      geoCtx.fillStyle = isQuarantined ? '#ef4444' : (node.role === 'LEADER' ? '#06b6d4' : '#94a3b8');
      geoCtx.font = '700 10px JetBrains Mono';
      const roleText = isQuarantined ? '[QUARANTINED]' : `[${node.role}]`;
      geoCtx.fillText(roleText, node.x - 30, node.y + 24);
    });
  }

  function drawMapGrid(ctx) {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
    ctx.lineWidth = 1;
    for (let x = 0; x < 900; x += 50) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, 420);
      ctx.stroke();
    }
    for (let y = 0; y < 420; y += 50) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(900, y);
      ctx.stroke();
    }
  }

  // --- Render MVCC Version Tree DAG ---
  function renderMVCCDAG() {
    dagCtx.clearRect(0, 0, 900, 180);

    // Draw connecting edges
    state.dagEdges.forEach(edge => {
      const fromNode = state.dagNodes.find(n => n.id === edge.from);
      const toNode = state.dagNodes.find(n => n.id === edge.to);
      if (fromNode && toNode) {
        dagCtx.beginPath();
        dagCtx.moveTo(fromNode.x, fromNode.y);
        dagCtx.lineTo(toNode.x, toNode.y);
        if (edge.type === 'ABORTED') {
          dagCtx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
          dagCtx.setLineDash([3, 3]);
        } else if (edge.type === 'SPECULATIVE') {
          dagCtx.strokeStyle = 'rgba(168, 85, 247, 0.5)';
          dagCtx.setLineDash([4, 4]);
        } else {
          dagCtx.strokeStyle = 'rgba(6, 182, 212, 0.7)';
          dagCtx.setLineDash([]);
        }
        dagCtx.lineWidth = 2;
        dagCtx.stroke();
        dagCtx.setLineDash([]);
      }
    });

    // Draw DAG nodes
    state.dagNodes.slice(-16).forEach(n => {
      dagCtx.beginPath();
      dagCtx.arc(n.x, n.y, 8, 0, Math.PI * 2);

      if (n.type === 'FINALIZED') {
        dagCtx.fillStyle = '#06b6d4';
        dagCtx.shadowColor = '#06b6d4';
        dagCtx.shadowBlur = 8;
      } else if (n.type === 'TENTATIVE') {
        dagCtx.fillStyle = '#a855f7';
        dagCtx.shadowColor = '#a855f7';
        dagCtx.shadowBlur = 6;
      } else {
        dagCtx.fillStyle = '#ef4444';
        dagCtx.shadowColor = '#ef4444';
        dagCtx.shadowBlur = 4;
      }
      dagCtx.fill();
      dagCtx.shadowBlur = 0;

      // Label
      dagCtx.fillStyle = '#94a3b8';
      dagCtx.font = '10px JetBrains Mono';
      dagCtx.fillText(n.label, n.x - 18, n.y + 18);
    });
  }

  // Start loop
  requestAnimationFrame(animate);
  logEvent('AetherBFT 60 FPS Visual Simulation Engine operational.', 'sys');

})();
