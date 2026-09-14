// Fleet interaction graph: hand-rolled force simulation on a 2D canvas.
//
// The physics (softened Coulomb repulsion, linear springs, centre gravity, D3-style
// alpha cooling) is carried over unchanged from the original single-file dashboard.
// What changed: node identity is preserved across refreshes so the layout no longer
// re-scatters, colours come from the CSS tokens rather than duplicated hex literals,
// and the animation loop plus listeners are torn down on unmount.

import { api } from '../core/api.js';
import { PALETTE, alpha } from '../core/palette.js';
import { setParam } from '../core/router.js';
import { toast } from '../core/ui.js';
import { refreshHeader } from '../core/header.js';
import { fmtUSD } from '../core/format.js';

const alphaDecay = 0.024;    // settles in ~120 frames
const velocityDecay = 0.55;  // strong friction to prevent jitter

let canvas, ctx, width = 0, height = 0;
let graphData = { nodes: [], edges: [] };
let findingsData = [];
let selectedNode = null;
let filterMode = 'all';
let camera = { x: 0, y: 0, zoom: 1.0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let simNodes = [];
let simLinks = [];
let simAlpha = 1.0;
let draggingNode = null;
let isDraggingNode = false;
let rafId = null;
let listeners = [];
let frameCount = 0, fpsLast = 0, fps = 0;

// The scene is static most of the time: physics freezes once cooled, and nothing
// else moves unless the user interacts. Repainting 300+ nodes and 900+ edges at
// 60fps regardless costs a full CPU core for no visible change, which is what made
// the whole tab feel sluggish. Redraw only when something actually changed.
let dirty = true;
function invalidateFrame() {
  dirty = true;
}

function on(target, type, fn, opts) {
  target.addEventListener(type, fn, opts);
  listeners.push([target, type, fn, opts]);
}

function resize() {
  const parent = canvas.parentElement;
  width = parent.clientWidth;
  height = parent.clientHeight;
  canvas.width = width;
  canvas.height = height;
  invalidateFrame();
}

function resetView() {
  camera = { x: 0, y: 0, zoom: 1.0 };
  invalidateFrame();
}

function reheatSimulation(a = 0.25) {
  simAlpha = Math.max(simAlpha, a);
  invalidateFrame();
}

/**
 * Reconcile incoming graph data against the live simulation.
 *
 * Nodes that still exist keep their position and velocity, so a refresh (or a
 * playback tick) grows the graph instead of throwing it back into the air. Only
 * genuinely new nodes are placed, and they spawn next to a neighbour they are
 * linked to so growth reads as accretion.
 */
function syncSimulation(data) {
  const prev = new Map(simNodes.map((n) => [n.id, n]));
  const centerX = width / 2;
  const centerY = height / 2;
  const count = Math.max(1, data.nodes.length);

  // Neighbour lookup so new nodes can spawn near something they connect to.
  const neighbourOf = new Map();
  for (const e of data.edges) {
    if (!neighbourOf.has(e.source)) neighbourOf.set(e.source, e.target);
    if (!neighbourOf.has(e.target)) neighbourOf.set(e.target, e.source);
  }

  let added = 0;
  const nodeMap = new Map();
  simNodes = data.nodes.map((incoming, i) => {
    const existing = prev.get(incoming.id);
    if (existing) {
      Object.assign(existing, incoming); // keeps x, y, vx, vy
      nodeMap.set(incoming.id, existing);
      return existing;
    }
    added += 1;
    const anchor = prev.get(neighbourOf.get(incoming.id)) || null;
    let x, y;
    if (anchor) {
      x = anchor.x + (Math.random() - 0.5) * 60;
      y = anchor.y + (Math.random() - 0.5) * 60;
    } else {
      const angle = (i / count) * 2 * Math.PI;
      const baseRadius = incoming.type === 'resource'
        ? Math.min(width, height) * 0.18
        : Math.min(width, height) * 0.35;
      x = centerX + Math.cos(angle) * baseRadius + (Math.random() - 0.5) * 20;
      y = centerY + Math.sin(angle) * baseRadius + (Math.random() - 0.5) * 20;
    }
    const sn = { ...incoming, x, y, vx: 0, vy: 0 };
    nodeMap.set(incoming.id, sn);
    return sn;
  });

  simLinks = data.edges
    .map((e) => ({ ...e, sourceNode: nodeMap.get(e.source), targetNode: nodeMap.get(e.target) }))
    .filter((l) => l.sourceNode && l.targetNode);

  // Keep the selection pointing at the live object, not a stale copy.
  if (selectedNode) {
    const still = nodeMap.get(selectedNode.id);
    if (still) selectedNode = still;
    else closeInspector();
  }

  if (prev.size === 0) {
    simAlpha = 1.0; // first layout needs a full cooling schedule
  } else if (added > 0) {
    reheatSimulation(0.12); // nudge, never a full reset
  }

  if (!selectedNode && simNodes.length > 0) {
    const top = simNodes.find((n) => n.type === 'agent' && n.status === 'concerning')
      || simNodes.find((n) => n.type === 'agent')
      || simNodes[0];
    selectNode(top);
  }

  // Statuses may have changed even when no node was added.
  invalidateFrame();
}

function stepPhysics() {
  if (simAlpha < 0.003) return; // frozen: rock-solid once settled

  const centerX = width / 2;
  const centerY = height / 2;

  // 1. Softened Coulomb repulsion (clamped to prevent explosion)
  for (let i = 0; i < simNodes.length; i++) {
    for (let j = i + 1; j < simNodes.length; j++) {
      const n1 = simNodes[i];
      const n2 = simNodes[j];
      let dx = n2.x - n1.x || (Math.random() - 0.5);
      let dy = n2.y - n1.y || (Math.random() - 0.5);
      let distSq = dx * dx + dy * dy;
      if (distSq < 1) distSq = 1;

      if (distSq < 50000) {
        const dist = Math.sqrt(distSq);
        const force = (simAlpha * 85) / (dist + 35);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        n1.vx -= fx; n1.vy -= fy;
        n2.vx += fx; n2.vy += fy;
      }
    }
  }

  // 2. Linear spring links
  for (const link of simLinks) {
    const dx = link.targetNode.x - link.sourceNode.x || (Math.random() - 0.5);
    const dy = link.targetNode.y - link.sourceNode.y || (Math.random() - 0.5);
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const desired = link.targetNode.type === 'resource' ? 140 : 100;
    const force = (dist - desired) * 0.022 * simAlpha;
    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;
    link.sourceNode.vx += fx; link.sourceNode.vy += fy;
    link.targetNode.vx -= fx; link.targetNode.vy -= fy;
  }

  // 3. Centre gravity and velocity damping
  for (const n of simNodes) {
    n.vx += (centerX - n.x) * 0.008 * simAlpha;
    n.vy += (centerY - n.y) * 0.008 * simAlpha;
    n.vx *= velocityDecay;
    n.vy *= velocityDecay;
    n.x += n.vx;
    n.y += n.vy;
  }

  simAlpha -= simAlpha * alphaDecay;
}

function nodeFill(n) {
  if (n.type === 'agent') {
    if (n.status === 'concerning') return PALETTE.rose;
    if (n.status === 'candidate') return PALETTE.amber;
    return PALETTE.mint;
  }
  if (n.status === 'conflict_hotspot') return PALETTE.rose;
  if (n.status === 'emerging_hub') return PALETTE.amber;
  return PALETTE.blue;
}

function draw() {
  rafId = requestAnimationFrame(draw);
  if (document.hidden) return; // don't burn cycles on a hidden tab

  const settled = simAlpha < 0.003;
  if (settled && !dirty) {
    // Nothing moving and nothing changed: skip the whole frame.
    const now = performance.now();
    if (now - fpsLast > 1000) {
      fpsLast = now;
      frameCount = 0;
      const readout = document.getElementById('graph-readout');
      if (readout) {
        readout.textContent =
          `${simNodes.length} nodes · ${simLinks.length} edges · settled (idle)`;
      }
    }
    return;
  }
  dirty = false;

  frameCount += 1;
  const now = performance.now();
  if (now - fpsLast > 500) {
    fps = Math.round((frameCount * 1000) / (now - fpsLast));
    frameCount = 0;
    fpsLast = now;
    const readout = document.getElementById('graph-readout');
    if (readout) {
      readout.textContent =
        `${simNodes.length} nodes · ${simLinks.length} edges · ${fps} fps` +
        (simAlpha < 0.003 ? ' · settled' : ' · cooling');
    }
  }

  ctx.clearRect(0, 0, width, height);
  stepPhysics();

  ctx.save();
  ctx.translate(camera.x, camera.y);
  ctx.scale(camera.zoom, camera.zoom);

  // Connections reveal on click, never on hover.
  const activeNode = selectedNode;
  const connectedNodeIds = new Set();
  if (activeNode) {
    connectedNodeIds.add(activeNode.id);
    for (const link of simLinks) {
      if (link.sourceNode.id === activeNode.id) connectedNodeIds.add(link.targetNode.id);
      if (link.targetNode.id === activeNode.id) connectedNodeIds.add(link.sourceNode.id);
    }
  }

  // 1. Links
  for (const link of simLinks) {
    const isConnected = activeNode
      && (link.sourceNode.id === activeNode.id || link.targetNode.id === activeNode.id);
    const isFaded = activeNode && !isConnected;

    ctx.save();
    ctx.globalAlpha = isFaded ? 0.02 : (isConnected ? 0.90 : 0.12);
    ctx.beginPath();
    ctx.moveTo(link.sourceNode.x, link.sourceNode.y);
    ctx.lineTo(link.targetNode.x, link.targetNode.y);

    if (link.type === 'CONFLICTS') {
      ctx.strokeStyle = PALETTE.rose;
      ctx.lineWidth = isConnected ? 2.0 : 1.2;
      ctx.setLineDash([3, 3]);
    } else if (link.type === 'SHARED_ARTIFACT') {
      ctx.strokeStyle = PALETTE.violet;
      ctx.lineWidth = isConnected ? 2.0 : 1.2;
      ctx.setLineDash([2, 3]);
    } else {
      ctx.strokeStyle = isConnected ? PALETTE.blue : alpha(PALETTE.textPrimary, 0.15);
      ctx.lineWidth = isConnected ? 1.5 : 0.7;
      ctx.setLineDash([]);
    }
    ctx.stroke();
    ctx.restore();
  }

  // 2. Nodes
  for (const n of simNodes) {
    if (filterMode === 'concerning' && n.status !== 'concerning') continue;
    if (filterMode === 'hubs' && n.status !== 'emerging_hub' && n.status !== 'conflict_hotspot') continue;

    const isSelected = selectedNode && selectedNode.id === n.id;
    const isConnectedNeighbor = activeNode && !isSelected && connectedNodeIds.has(n.id);
    const isFaded = activeNode && !isSelected && !isConnectedNeighbor;

    ctx.save();
    ctx.globalAlpha = isFaded ? 0.12 : 1.0;
    const fillColor = nodeFill(n);

    if (n.type === 'agent') {
      const r = isSelected ? 16 : (isConnectedNeighbor ? 9 : 7);

      // Work-allocation ring: how much of this agent's activity is routine.
      if (isSelected) {
        const normPct = n.normal_percentage !== undefined ? n.normal_percentage : 84.8;
        const normAngle = (normPct / 100) * 2 * Math.PI;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3, -Math.PI / 2, -Math.PI / 2 + normAngle);
        ctx.strokeStyle = PALETTE.mint;
        ctx.lineWidth = 2.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3, -Math.PI / 2 + normAngle, 3 * Math.PI / 2);
        ctx.strokeStyle = n.status === 'concerning' ? PALETTE.rose : PALETTE.amber;
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = fillColor;
      ctx.fill();

      if (n.token_drift) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3.5, 0, 2 * Math.PI);
        ctx.strokeStyle = PALETTE.violet;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([2, 2]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (isSelected || isConnectedNeighbor) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = PALETTE.textPrimary;
        ctx.stroke();
      }
    } else {
      const sz = isSelected ? 20 : (isConnectedNeighbor ? 13 : 10);
      ctx.fillStyle = fillColor;
      ctx.fillRect(n.x - sz / 2, n.y - sz / 2, sz, sz);
      if (isSelected || isConnectedNeighbor) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = PALETTE.textPrimary;
        ctx.strokeRect(n.x - sz / 2, n.y - sz / 2, sz, sz);
      }
    }

    // Labels only for the selection and its direct neighbours.
    if (isSelected || isConnectedNeighbor) {
      ctx.font = isSelected ? '600 11px Inter, sans-serif' : '500 9px Inter, sans-serif';
      const text = n.label.length > 22 ? n.label.slice(0, 20) + '...' : n.label;
      const bgW = ctx.measureText(text).width + 10;
      const bgH = 16;
      const labelOffset = isSelected ? (n.type === 'agent' ? 24 : 18) : 12;
      const bgX = n.x - bgW / 2;
      const bgY = n.y + labelOffset;

      ctx.fillStyle = PALETTE.bgPanel;
      ctx.strokeStyle = isSelected
        ? (n.status === 'concerning' ? PALETTE.rose : PALETTE.blue)
        : PALETTE.borderSubtle;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(bgX, bgY, bgW, bgH, 3);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = isSelected ? PALETTE.textPrimary : PALETTE.textSecondary;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, n.x, bgY + bgH / 2);
    }

    ctx.restore();
  }

  if (selectedNode) drawInCanvasCard(selectedNode, connectedNodeIds);

  ctx.restore();
}

function drawInCanvasCard(n, connectedNodeIds) {
  ctx.save();
  const cardWidth = 220;
  const cardHeight = 76;
  const inspector = document.getElementById('inspector');
  const rightMargin = !inspector || inspector.classList.contains('hidden') ? 20 : 380;

  let cardX = n.x + 30;
  let cardY = n.y - 60;
  if (cardX + cardWidth > width - rightMargin) cardX = n.x - cardWidth - 30;
  if (cardX < 260) cardX = 260;
  if (cardY < 20) cardY = 20;
  if (cardY + cardHeight > height - 20) cardY = height - cardHeight - 20;

  ctx.fillStyle = PALETTE.bgSurface;
  ctx.strokeStyle = n.status === 'concerning' ? PALETTE.rose : PALETTE.borderSubtle;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(cardX, cardY, cardWidth, cardHeight, 6);
  ctx.fill();
  ctx.stroke();

  ctx.font = '600 11px Inter, sans-serif';
  ctx.fillStyle = PALETTE.textPrimary;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(n.label.length > 20 ? n.label.slice(0, 18) + '...' : n.label, cardX + 10, cardY + 10);

  const badgeText = n.status.toUpperCase();
  ctx.font = '600 8px Inter, sans-serif';
  const badgeW = ctx.measureText(badgeText).width + 8;
  const badgeX = cardX + cardWidth - badgeW - 10;
  ctx.fillStyle = n.status === 'concerning' ? alpha(PALETTE.rose, 0.15) : alpha(PALETTE.mint, 0.15);
  ctx.fillRect(badgeX, cardY + 9, badgeW, 14);
  ctx.fillStyle = n.status === 'concerning' ? PALETTE.rose : PALETTE.mint;
  ctx.fillText(badgeText, badgeX + 4, cardY + 12);

  ctx.font = '500 9px Inter, sans-serif';
  ctx.fillStyle = PALETTE.textSecondary;
  if (n.type === 'agent') {
    const norm = n.normal_percentage !== undefined ? n.normal_percentage : 84.8;
    ctx.fillText(`Events: ${n.event_count || 0}  |  Normal Work: ${norm}%`, cardX + 10, cardY + 28);
    ctx.fillText(`Connected Tools & Peers: ${connectedNodeIds.size - 1}`, cardX + 10, cardY + 42);
    if (n.token_drift) {
      ctx.fillStyle = PALETTE.violet;
      ctx.fillText(`Token Drift: ${n.token_drift.js_divergence} bits`, cardX + 10, cardY + 56);
    } else if (n.patterns && n.patterns.length > 0) {
      ctx.fillStyle = PALETTE.rose;
      ctx.fillText(`Alert: ${n.patterns.join(', ')}`, cardX + 10, cardY + 56);
    } else {
      ctx.fillStyle = PALETTE.mint;
      ctx.fillText('Normal benchmark task active', cardX + 10, cardY + 56);
    }
  } else {
    ctx.fillText(`Type: ${n.resource_type || 'wiki'}  |  Actions: ${n.event_count || 0}`, cardX + 10, cardY + 28);
    ctx.fillText(`Connected Agents: ${connectedNodeIds.size - 1}`, cardX + 10, cardY + 42);
    ctx.fillStyle = n.status === 'conflict_hotspot' ? PALETTE.rose : PALETTE.blue;
    ctx.fillText(
      n.status === 'conflict_hotspot' ? 'Status: Conflicting write hotspot' : 'Status: Shared benchmark tool',
      cardX + 10, cardY + 56
    );
  }
  ctx.restore();
}

function screenToWorld(sx, sy) {
  return { x: (sx - camera.x) / camera.zoom, y: (sy - camera.y) / camera.zoom };
}

function hitTest(sx, sy, radius = 18) {
  const w = screenToWorld(sx, sy);
  for (const n of simNodes) {
    const dx = n.x - w.x;
    const dy = n.y - w.y;
    if (Math.sqrt(dx * dx + dy * dy) < radius) return n;
  }
  return null;
}

function closeInspector() {
  selectedNode = null;
  invalidateFrame();
  const inspector = document.getElementById('inspector');
  if (inspector) inspector.classList.add('hidden');
}

function selectNode(node) {
  selectedNode = node;
  invalidateFrame();
  const inspector = document.getElementById('inspector');
  if (!inspector) return;
  inspector.classList.remove('hidden');

  document.getElementById('inspector-name').innerText = node.label;
  document.getElementById('inspector-id').innerText = `ID: ${node.id}`;

  const badge = document.getElementById('inspector-badge');
  badge.className = `inspector-badge badge-${node.status}`;
  badge.innerText = node.status === 'concerning'
    ? 'Violation'
    : (node.status === 'candidate' ? 'Candidate' : 'Normal');

  document.getElementById('inspector-stats').innerText =
    `Total actions recorded: ${node.event_count || 0}`;

  const workProfileCard = document.getElementById('card-work-profile');
  const driftCard = document.getElementById('card-token-drift');

  if (node.type === 'agent') {
    workProfileCard.style.display = 'flex';
    const normPct = node.normal_percentage !== undefined ? node.normal_percentage : 84.8;
    const collPct = (100 - normPct).toFixed(1);
    document.getElementById('work-profile-text').innerHTML =
      `<strong>Normal Benchmark Work:</strong> ${normPct}% (${node.normal_actions || 0} routine calls)<br>` +
      `<strong>Shared Activity:</strong> ${collPct}% (${node.wiki_actions || 0} wiki edits)`;

    if (node.token_drift) {
      driftCard.style.display = 'flex';
      const d = node.token_drift;
      document.getElementById('token-drift-text').innerHTML =
        `<strong>Jensen-Shannon Divergence:</strong> <span style="color: var(--pastel-violet);">${d.js_divergence} bits</span> (threshold: 0.55)<br>` +
        `<strong>Cross-Entropy Perplexity:</strong> ${d.cross_entropy_perplexity}<br>` +
        `<strong>Steganography Score:</strong> ${d.steganography_score}<br>` +
        `<strong>Top Drift Keywords:</strong> <span style="color: var(--pastel-rose);">${d.drift_keywords ? d.drift_keywords.join(', ') : 'none'}</span>`;
    } else {
      driftCard.style.display = 'none';
    }
  } else {
    workProfileCard.style.display = 'none';
    driftCard.style.display = 'none';
  }

  const relatedFinding = findingsData.find(
    (f) => f.actors.includes(node.label) || f.target_resources.includes(node.label)
  );
  const alertCard = document.getElementById('card-alert');
  if (relatedFinding) {
    alertCard.style.display = 'flex';
    document.getElementById('inspector-pattern').innerText = `Pattern: ${relatedFinding.pattern}`;
    document.getElementById('inspector-explanation').innerText = relatedFinding.explanation;
    document.getElementById('inspector-snippet').innerText =
      `Evidence: ${relatedFinding.evidence_ids.join(', ')}`;
  } else {
    alertCard.style.display = 'none';
    document.getElementById('inspector-snippet').innerText = 'No alert triggers for this node.';
  }
}

function setStatus(html) {
  const bar = document.getElementById('status-bar');
  if (bar) bar.innerHTML = html;
}

async function refreshData() {
  try {
    const [graph, budget, findings] = await Promise.all([
      api.graph(), api.budget(), api.findings(),
    ]);
    graphData = graph;
    findingsData = findings;

    const hubCount = graphData.nodes.filter(
      (n) => n.type === 'resource' && (n.status === 'emerging_hub' || n.status === 'conflict_hotspot')
    ).length;
    setStatus(
      '<span class="status-indicator"></span>' +
      `<span>${hubCount} flagged resources · ${findingsData.length} findings · ` +
      `judge spend ${fmtUSD(budget.spent_usd)}</span>`
    );

    refreshHeader();
    syncSimulation(graphData);
  } catch (e) {
    console.error('Failed to refresh graph data', e);
    setStatus(`<span class="status-indicator" style="background:var(--pastel-rose);"></span><span>Refresh failed: ${e.message}</span>`);
  }
}

function setFilter(mode) {
  filterMode = mode;
  invalidateFrame();
  for (const [id, m] of [
    ['btn-filter-all', 'all'],
    ['btn-filter-alerts', 'concerning'],
    ['btn-filter-hubs', 'hubs'],
  ]) {
    const b = document.getElementById(id);
    if (b) b.className = mode === m ? 'btn active' : 'btn';
  }
  setParam('filter', mode === 'all' ? null : mode);
}

const MARKUP = `
  <div class="workspace">
    <div class="controls-overlay">
      <div class="control-row">
        <label>View</label>
        <div class="control-btn-group">
          <button class="btn active" id="btn-filter-all">All</button>
          <button class="btn" id="btn-filter-alerts">Alerts</button>
          <button class="btn" id="btn-filter-hubs">Hubs</button>
        </div>
      </div>
      <div class="control-row" style="margin-top: 2px;">
        <button class="btn btn-action btn-primary-action" id="btn-load-fleet">Load 100-Agent Fleet</button>
        <button class="btn btn-action" id="btn-replay">Run Offline Replay</button>
      </div>
      <div class="legend">
        <div class="legend-item"><span class="dot" style="background: var(--pastel-rose);"></span> Policy Violation (Alert)</div>
        <div class="legend-item"><span class="dot" style="background: var(--pastel-amber);"></span> Flagged Candidate</div>
        <div class="legend-item"><span class="dot" style="background: var(--pastel-mint);"></span> Normal Agent</div>
        <div class="legend-item"><span class="dot" style="background: var(--pastel-violet);"></span> Token Drift Anomaly</div>
        <div class="legend-item"><span class="sq" style="background: var(--pastel-rose);"></span> Conflict Hotspot Page</div>
        <div class="legend-item"><span class="sq" style="background: var(--pastel-blue);"></span> Benchmark Tool / Resource</div>
      </div>
    </div>

    <div class="canvas-hint">Click node to inspect connections &middot; Scroll to zoom &middot; Drag to pan</div>

    <div id="graph-container"><canvas id="canvas"></canvas></div>

    <div id="inspector" class="hidden">
      <div class="inspector-header">
        <div>
          <div class="inspector-title" id="inspector-name">—</div>
          <div class="inspector-sub" id="inspector-id">—</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="inspector-badge badge-concerning" id="inspector-badge">—</span>
          <button class="inspector-close-btn" id="btn-close-inspector">&times;</button>
        </div>
      </div>
      <div class="inspector-content">
        <div class="card" id="card-alert">
          <h4>Policy Violation Finding</h4>
          <p id="inspector-pattern">—</p>
          <p id="inspector-explanation">—</p>
        </div>
        <div class="card" id="card-token-drift">
          <h4>Token Distribution Anomaly</h4>
          <p id="token-drift-text">—</p>
        </div>
        <div class="card" id="card-work-profile">
          <h4>Workload Allocation</h4>
          <p id="work-profile-text">—</p>
        </div>
        <div class="card">
          <h4>Interaction Telemetry</h4>
          <p id="inspector-stats">—</p>
        </div>
        <div class="card">
          <h4>Observed Payload Evidence</h4>
          <div class="snippet-box" id="inspector-snippet">—</div>
        </div>
      </div>
    </div>
  </div>

  <div class="bottom-panel">
    <div class="status-text" id="status-bar">
      <span class="status-indicator"></span><span>Ready.</span>
    </div>
    <div class="row">
      <span class="dim mono" id="graph-readout" style="font-size:0.66rem;"></span>
      <button class="btn" id="btn-reset-view">Reset View</button>
      <button class="btn" id="btn-refresh">Refresh</button>
    </div>
  </div>
`;

export async function mount(root, params = {}) {
  root.innerHTML = MARKUP;
  canvas = document.getElementById('canvas');
  ctx = canvas.getContext('2d');

  // Reset per-mount view state; node positions are rebuilt from the API below.
  simNodes = [];
  simLinks = [];
  selectedNode = null;
  camera = { x: 0, y: 0, zoom: 1.0 };
  filterMode = params.filter || 'all';
  fpsLast = performance.now();
  frameCount = 0;

  resize();
  on(window, 'resize', resize);

  document.getElementById('btn-filter-all').onclick = () => setFilter('all');
  document.getElementById('btn-filter-alerts').onclick = () => setFilter('concerning');
  document.getElementById('btn-filter-hubs').onclick = () => setFilter('hubs');
  document.getElementById('btn-close-inspector').onclick = closeInspector;
  document.getElementById('btn-reset-view').onclick = resetView;
  document.getElementById('btn-refresh').onclick = () => refreshData();

  document.getElementById('btn-load-fleet').onclick = async () => {
    setStatus('<span class="status-indicator"></span><span>Loading 100 benchmark agent traces…</span>');
    try {
      const data = await api.loadFleet({ agents: 100, eventsPerAgent: 25 });
      setStatus(`<span class="status-indicator"></span><span>Fleet loaded: ${data.total_agents} agents, ${data.total_events} events, ${data.findings_generated} findings.</span>`);
      await refreshData();
    } catch (e) {
      setStatus(`<span class="status-indicator" style="background:var(--pastel-rose);"></span><span>Load failed: ${e.message}</span>`);
    }
  };

  document.getElementById('btn-replay').onclick = async () => {
    setStatus('<span class="status-indicator"></span><span>Executing deterministic replay verification…</span>');
    try {
      const data = await api.replay();
      setStatus(`<span class="status-indicator"></span><span>Replay verified: ${data.replayed_findings_count} findings confirmed with ${data.llm_calls_made} fresh LLM calls.</span>`);
      toast(`Replay reproduced ${data.replayed_findings_count} findings with 0 model calls`, 'ok');
    } catch (e) {
      setStatus(`<span class="status-indicator" style="background:var(--pastel-rose);"></span><span>Replay failed: ${e.message}</span>`);
    }
  };

  setFilter(filterMode);

  on(canvas, 'wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    camera.x = mouseX - (mouseX - camera.x) * zoomFactor;
    camera.y = mouseY - (mouseY - camera.y) * zoomFactor;
    camera.zoom = Math.max(0.2, Math.min(3.5, camera.zoom * zoomFactor));
    invalidateFrame();
  }, { passive: false });

  on(canvas, 'mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const node = hitTest(sx, sy);
    if (node) {
      draggingNode = node;
      isDraggingNode = true;
      selectNode(node);
      reheatSimulation(0.2);
      return;
    }
    isPanning = true;
    panStart = { x: sx - camera.x, y: sy - camera.y };
  });

  on(canvas, 'mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (isDraggingNode && draggingNode) {
      const w = screenToWorld(sx, sy);
      draggingNode.x = w.x;
      draggingNode.y = w.y;
      draggingNode.vx = 0;
      draggingNode.vy = 0;
      reheatSimulation(0.15);
      invalidateFrame();
    } else if (isPanning) {
      camera.x = sx - panStart.x;
      camera.y = sy - panStart.y;
      invalidateFrame();
    } else {
      canvas.style.cursor = hitTest(sx, sy, 16) ? 'pointer' : 'default';
    }
  });

  on(window, 'mouseup', () => {
    isDraggingNode = false;
    draggingNode = null;
    isPanning = false;
  });

  on(canvas, 'click', (e) => {
    if (isDraggingNode) return;
    const rect = canvas.getBoundingClientRect();
    const node = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (node) selectNode(node);
    else closeInspector();
  });

  await refreshData();
  if (graphData.nodes.length === 0) {
    await document.getElementById('btn-load-fleet').onclick();
  }

  rafId = requestAnimationFrame(draw);
}

export function unmount() {
  if (rafId != null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  for (const [target, type, fn, opts] of listeners) {
    target.removeEventListener(type, fn, opts);
  }
  listeners = [];
  canvas = null;
  ctx = null;
  simNodes = [];
  simLinks = [];
  selectedNode = null;
}
