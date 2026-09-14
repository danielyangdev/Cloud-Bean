// State playback: scrub the fleet's event stream and watch findings surface.
//
// Features an interactive animated mini-graph simulation canvas, timeline scrubber,
// event tape with node filtering, and surfaced findings rail.

import { load, snapshot } from '../core/store.js';
import { heatStrip } from '../charts/chart.js';
import { el, panel, emptyState } from '../core/ui.js';
import { fmtInt, fmtClock, fmtTsShort, humanise, truncate, stripPrefix, escapeHtml } from '../core/format.js';
import { PALETTE, alpha } from '../core/palette.js';

const BUCKETS = 140;
const TAPE_ROWS = 28;
const SPEEDS = [1, 4, 16, 64];

let root = null;
let strip = null;
let events = [];
let findings = [];
let cursor = 0;          // event ordinal
let playing = false;
let speedIdx = 1;
let timerId = null;

// Simulation canvas state
let simCanvas = null;
let simCtx = null;
let simWidth = 640;
let simHeight = 310;
let simNodes = [];
let simNodeMap = new Map();
let simRafId = null;
let simResizeObserver = null;
let hoveredNode = null;
let selectedFilterNode = null;

function isWiki(ev) {
  if (!ev) return false;
  return ev.sensor_source === 'wiki_archive' || String(ev.target || '').startsWith('wiki:');
}

function buildBuckets() {
  if (!events.length) return [];
  const size = Math.max(1, Math.ceil(events.length / BUCKETS));
  const out = [];
  for (let i = 0; i < events.length; i += size) {
    const slice = events.slice(i, i + size);
    out.push({
      total: slice.length,
      highlight: slice.filter(isWiki).length,
    });
  }
  return out;
}

function cursorTime() {
  if (!events.length) return null;
  const idx = Math.min(events.length - 1, Math.max(0, cursor));
  return events[idx].timestamp;
}

// -----------------------------------------------------------------------------
// Simulation Model & Layout
// -----------------------------------------------------------------------------

function initSimulationData() {
  const actorIds = [...new Set(events.map((e) => e.actor_id))].sort();

  // Calculate target frequencies across the event stream
  const targetCounts = new Map();
  for (const e of events) {
    if (e.target) {
      targetCounts.set(e.target, (targetCounts.get(e.target) || 0) + 1);
    }
  }

  const sortedTargets = [...targetCounts.entries()].sort((a, b) => b[1] - a[1]);
  const topTools = sortedTargets.filter(([t]) => String(t).startsWith('tool:')).slice(0, 14);
  const topWikis = sortedTargets.filter(([t]) => String(t).startsWith('wiki:')).slice(0, 10);

  simNodes = [];
  simNodeMap = new Map();

  // 1. Core Tools (upper inner arc)
  const nTools = topTools.length || 1;
  topTools.forEach(([tgt, count], i) => {
    const angle = -Math.PI * 0.85 + (i / Math.max(1, nTools - 1)) * (Math.PI * 0.70);
    const rx = 0.22;
    const ry = 0.19;
    const nx = 0.5 + rx * Math.cos(angle);
    const ny = 0.5 + ry * Math.sin(angle);

    const node = {
      id: tgt,
      label: stripPrefix(tgt),
      type: 'tool',
      nx, ny,
      x: 0, y: 0,
      r: 6,
      color: '#7dd3fc', // Glacier Blue
      count,
    };
    simNodes.push(node);
    simNodeMap.set(tgt, node);
  });

  // 2. Core Wiki Resources (lower inner arc)
  const nWikis = topWikis.length || 1;
  topWikis.forEach(([tgt, count], i) => {
    const angle = Math.PI * 0.15 + (i / Math.max(1, nWikis - 1)) * (Math.PI * 0.70);
    const rx = 0.22;
    const ry = 0.19;
    const nx = 0.5 + rx * Math.cos(angle);
    const ny = 0.5 + ry * Math.sin(angle);

    const isHub = tgt === 'wiki:WillkommenImWiki';
    const node = {
      id: tgt,
      label: stripPrefix(tgt),
      type: 'wiki',
      nx, ny,
      x: 0, y: 0,
      r: isHub ? 8 : 6,
      color: isHub ? '#fb7185' : '#c084fc', // Smoky Heather / Terracotta hub
      count,
    };
    simNodes.push(node);
    simNodeMap.set(tgt, node);
  });

  // Fallback map for occasional low-frequency targets
  const defaultWikiNode = simNodeMap.get('wiki:WillkommenImWiki') || simNodes[0];
  const defaultToolNode = simNodeMap.get('tool:python_repl') || simNodes[0];
  for (const [tgt] of sortedTargets) {
    if (!simNodeMap.has(tgt)) {
      simNodeMap.set(tgt, String(tgt).startsWith('wiki:') ? defaultWikiNode : defaultToolNode);
    }
  }

  // 3. Agents (outer perimeter ring)
  const nAgents = actorIds.length || 1;
  actorIds.forEach((aid, i) => {
    const angle = (i / nAgents) * 2 * Math.PI - Math.PI / 2;
    const rVar = 0.96 + 0.08 * Math.sin(i * 3.7);
    const rx = 0.44 * rVar;
    const ry = 0.38 * rVar;
    const nx = 0.5 + rx * Math.cos(angle);
    const ny = 0.5 + ry * Math.sin(angle);

    const node = {
      id: aid,
      label: aid,
      type: 'agent',
      nx, ny,
      x: 0, y: 0,
      r: 4.5,
      color: '#5eead4', // Lichen Sage default
    };
    simNodes.push(node);
    simNodeMap.set(aid, node);
  });

  updateNodeCoords(simWidth, simHeight);
}

function updateNodeCoords(w, h) {
  for (const n of simNodes) {
    n.x = Math.round(n.nx * w);
    n.y = Math.round(n.ny * h);
  }
}

function resizeSimulation() {
  if (!simCanvas || !simCanvas.parentElement) return;
  const parent = simCanvas.parentElement;
  const w = Math.floor(parent.clientWidth) || 640;
  const h = 310;
  const dpr = window.devicePixelRatio || 1;

  simCanvas.width = Math.round(w * dpr);
  simCanvas.height = Math.round(h * dpr);
  simCanvas.style.width = `${w}px`;
  simCanvas.style.height = `${h}px`;

  simWidth = w;
  simHeight = h;
  updateNodeCoords(w, h);
}

function drawSimulation() {
  if (!simCanvas || !simCtx) return;

  const dpr = window.devicePixelRatio || 1;
  const w = simWidth;
  const h = simHeight;

  simCtx.save();
  simCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // 1. Clear to dark volcanic charcoal
  simCtx.fillStyle = '#131418';
  simCtx.fillRect(0, 0, w, h);

  // 2. Cosmic guide rings
  simCtx.lineWidth = 1;
  simCtx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
  simCtx.beginPath();
  simCtx.ellipse(w * 0.5, h * 0.5, w * 0.22, h * 0.19, 0, 0, 2 * Math.PI);
  simCtx.stroke();

  simCtx.beginPath();
  simCtx.ellipse(w * 0.5, h * 0.5, w * 0.44, h * 0.38, 0, 0, 2 * Math.PI);
  simCtx.stroke();

  const nowTs = cursorTime();

  // Identify surfaced finding actors at nowTs
  const activeFindingActors = new Set();
  if (nowTs) {
    for (const f of findings) {
      if (f.first_evidence_time && f.first_evidence_time <= nowTs) {
        for (const act of (f.actors || [])) {
          activeFindingActors.add(act);
        }
      }
    }
  }

  // 3. Active Filaments for events in [cursor - 4 ... cursor]
  const recentWindow = [];
  const startWindow = Math.max(0, cursor - 4);
  for (let i = startWindow; i <= cursor; i++) {
    if (events[i]) recentWindow.push({ ev: events[i], idx: i });
  }

  const nowMs = performance.now();

  for (const { ev, idx } of recentWindow) {
    const actor = simNodeMap.get(ev.actor_id);
    const target = simNodeMap.get(ev.target);
    if (!actor || !target) continue;

    const recency = 1.0 - (cursor - idx) * 0.20;
    const isW = isWiki(ev);
    const baseColor = isW ? '#fb7185' : (ev.event_type === 'tool_call' ? '#7dd3fc' : '#f59e0b');

    // Glowing filament line
    simCtx.beginPath();
    simCtx.moveTo(actor.x, actor.y);
    simCtx.lineTo(target.x, target.y);
    simCtx.strokeStyle = isW
      ? `rgba(251, 113, 133, ${0.90 * recency})`
      : `rgba(125, 211, 252, ${0.85 * recency})`;
    simCtx.lineWidth = idx === cursor ? 2.5 : Math.max(1, 1.8 * recency);
    simCtx.lineCap = 'round';
    simCtx.stroke();

    // Traveling pulse particle
    const pulseOffset = ((nowMs / 650) + (idx * 0.25)) % 1;
    const px = actor.x + (target.x - actor.x) * pulseOffset;
    const py = actor.y + (target.y - actor.y) * pulseOffset;

    simCtx.beginPath();
    simCtx.arc(px, py, idx === cursor ? 3.5 : 2.5, 0, 2 * Math.PI);
    simCtx.fillStyle = baseColor;
    simCtx.fill();

    simCtx.beginPath();
    simCtx.arc(px, py, idx === cursor ? 7 : 5, 0, 2 * Math.PI);
    simCtx.fillStyle = isW ? 'rgba(251, 113, 133, 0.35)' : 'rgba(125, 211, 252, 0.28)';
    simCtx.fill();
  }

  // 4. Draw Nodes
  const currentEvent = events[cursor];
  const activeActorId = currentEvent ? currentEvent.actor_id : null;
  const activeTargetId = currentEvent ? currentEvent.target : null;

  for (const n of simNodes) {
    const isActor = n.type === 'agent';
    const isActive = (n.id === activeActorId || (n.id === activeTargetId && !isActor));
    const isSelected = (selectedFilterNode && selectedFilterNode.id === n.id);
    const isHovered = (hoveredNode && hoveredNode.id === n.id);
    const hasAlert = isActor && activeFindingActors.has(n.id);
    const isCurrentOffender = (n.id === activeActorId && hasAlert);

    if (isActor) {
      const fillColor = hasAlert ? '#fb7185' : '#5eead4';
      const r = isActive ? 7.5 : (isSelected ? 8 : 4.5);

      // Terracotta alert flare shockwave ONLY for active offending actor
      if (isCurrentOffender) {
        const flareT = (nowMs / 900) % 1;
        const ringR = r + 3 + flareT * 18;
        simCtx.beginPath();
        simCtx.arc(n.x, n.y, ringR, 0, 2 * Math.PI);
        simCtx.strokeStyle = `rgba(251, 113, 133, ${Math.max(0, 1 - flareT)})`;
        simCtx.lineWidth = 2.0;
        simCtx.stroke();
      }

      // Translucent outer cell membrane
      simCtx.beginPath();
      simCtx.arc(n.x, n.y, r + (isActive ? 3.5 : 2), 0, 2 * Math.PI);
      simCtx.fillStyle = hasAlert
        ? (isActive ? 'rgba(251, 113, 133, 0.40)' : 'rgba(251, 113, 133, 0.16)')
        : (isActive ? 'rgba(94, 234, 212, 0.35)' : 'rgba(94, 234, 212, 0.10)');
      simCtx.fill();

      // Nucleus
      simCtx.beginPath();
      simCtx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      simCtx.fillStyle = fillColor;
      simCtx.fill();

      // Selection or hover ring
      if (isSelected || isHovered) {
        simCtx.beginPath();
        simCtx.arc(n.x, n.y, r + 2.5, 0, 2 * Math.PI);
        simCtx.strokeStyle = '#f0f1f4';
        simCtx.lineWidth = 1.5;
        simCtx.stroke();
      }
    } else {
      // Resource: smooth river pebble
      const isWikiRes = n.type === 'wiki';
      const fillColor = isWikiRes
        ? (isActive ? '#fb7185' : '#c084fc')
        : (isActive ? '#38bdf8' : '#7dd3fc');
      const sz = isActive ? 16 : (isSelected ? 16 : 12);
      const pr = Math.floor(sz * 0.35);

      // Translucent outer pebble aura
      simCtx.beginPath();
      simCtx.roundRect(n.x - (sz + 4) / 2, n.y - (sz + 2) / 2, sz + 4, sz + 2, pr + 1);
      simCtx.fillStyle = isActive ? 'rgba(125, 211, 252, 0.32)' : 'rgba(125, 211, 252, 0.08)';
      simCtx.fill();

      // Pebble body
      simCtx.beginPath();
      simCtx.roundRect(n.x - sz / 2, n.y - (sz - 2) / 2, sz, sz - 2, pr);
      simCtx.fillStyle = fillColor;
      simCtx.fill();

      if (isSelected || isHovered) {
        simCtx.lineWidth = 1.5;
        simCtx.strokeStyle = '#f0f1f4';
        simCtx.stroke();
      }
    }
  }

  // 5. Active Telemetry Watermark
  if (currentEvent) {
    const op = currentEvent.operation || currentEvent.event_type;

    simCtx.font = '600 10px Inter, sans-serif';
    simCtx.fillStyle = '#6a6f7e';
    simCtx.textAlign = 'left';
    simCtx.textBaseline = 'top';
    simCtx.fillText('LIVE TELEMETRY', 14, 12);

    simCtx.font = '500 12px "JetBrains Mono", monospace';
    simCtx.fillStyle = '#f0f1f4';
    simCtx.fillText(`${currentEvent.actor_id} → ${stripPrefix(currentEvent.target)}`, 14, 26);

    simCtx.font = '400 10px "JetBrains Mono", monospace';
    simCtx.fillStyle = isWiki(currentEvent) ? '#fb7185' : '#7dd3fc';
    simCtx.fillText(`[${op}] ${fmtTsShort(currentEvent.timestamp)}`, 14, 42);
  }

  // 6. Floating Tooltip on Hover
  if (hoveredNode) {
    const hx = hoveredNode.x;
    const hy = hoveredNode.y - 18;
    const isAct = hoveredNode.type === 'agent';
    const tag = isAct ? 'Agent' : (hoveredNode.type === 'wiki' ? 'Wiki Page' : 'Tool API');
    const hasAlert = isAct && activeFindingActors.has(hoveredNode.id);

    simCtx.font = '600 10px "JetBrains Mono", monospace';
    const txt = `${hoveredNode.id} (${tag}${hasAlert ? ' · ALERT' : ''})`;
    const tw = simCtx.measureText(txt).width;
    const pad = 6;
    const bx = Math.max(10, Math.min(w - tw - pad * 2 - 10, hx - (tw + pad * 2) / 2));
    const by = Math.max(10, hy - 18);

    simCtx.fillStyle = 'rgba(26, 27, 33, 0.95)';
    simCtx.strokeStyle = hasAlert ? '#fb7185' : '#31333e';
    simCtx.lineWidth = 1;
    simCtx.beginPath();
    simCtx.roundRect(bx, by, tw + pad * 2, 20, 4);
    simCtx.fill();
    simCtx.stroke();

    simCtx.fillStyle = hasAlert ? '#fb7185' : '#f0f1f4';
    simCtx.textAlign = 'left';
    simCtx.textBaseline = 'middle';
    simCtx.fillText(txt, bx + pad, by + 10);
  }

  simCtx.restore();

  simRafId = requestAnimationFrame(drawSimulation);
}

function hitTest(mx, my) {
  for (const n of simNodes) {
    const dx = n.x - mx;
    const dy = n.y - my;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist <= 14) return n;
  }
  return null;
}

// -----------------------------------------------------------------------------
// Tape & Counters Rendering
// -----------------------------------------------------------------------------

function renderTape() {
  const host = root.querySelector('#tape');
  const banner = root.querySelector('#tape-filter-host');
  if (!host) return;

  if (selectedFilterNode) {
    if (banner) {
      banner.innerHTML = `<div class="tape-filter-badge">` +
        `<span>Filtered by: <strong>${escapeHtml(selectedFilterNode.id)}</strong></span>` +
        `<span class="tape-filter-clear" id="btn-clear-filter">Clear filter &times;</span>` +
        `</div>`;
      const clearBtn = banner.querySelector('#btn-clear-filter');
      if (clearBtn) {
        clearBtn.onclick = () => {
          selectedFilterNode = null;
          renderTape();
          renderCounters();
        };
      }
    }
  } else if (banner) {
    banner.innerHTML = '';
  }

  const baseEvents = selectedFilterNode
    ? events.filter((e) => e.actor_id === selectedFilterNode.id || e.target === selectedFilterNode.id)
    : events;

  if (!baseEvents.length) {
    host.innerHTML = '<div style="padding:16px; color:var(--text-tertiary); text-align:center;">No matching events for this node.</div>';
    return;
  }

  let effectiveCursor = cursor;
  if (selectedFilterNode) {
    const curTs = cursorTime();
    effectiveCursor = baseEvents.findIndex((e) => e.timestamp >= curTs);
    if (effectiveCursor < 0) effectiveCursor = baseEvents.length - 1;
  }

  const start = Math.max(0, effectiveCursor - TAPE_ROWS + 6);
  const slice = baseEvents.slice(start, start + TAPE_ROWS);

  host.innerHTML = slice.map((ev, i) => {
    const idx = start + i;
    const isCurrent = idx === effectiveCursor;
    const cls = `tape-row${isCurrent ? ' cursor' : ''}${isWiki(ev) ? ' wiki' : ''}`;
    const op = ev.operation || ev.event_type;
    return `<div class="${cls}">` +
      `<span class="tr-ts">${fmtTsShort(ev.timestamp)}</span>` +
      `<span class="tr-actor">${escapeHtml(truncate(ev.actor_id, 18))}</span>` +
      `<span>${escapeHtml(truncate(op, 20))}</span>` +
      `<span class="dim">${escapeHtml(truncate(stripPrefix(ev.target), 26))}</span>` +
      `</div>`;
  }).join('');
}

function renderCounters() {
  const seen = events.slice(0, cursor + 1);
  const wiki = seen.filter(isWiki).length;
  const actors = new Set(seen.map((e) => e.actor_id)).size;
  const resources = new Set(seen.map((e) => e.target).filter(Boolean)).size;

  const host = root.querySelector('#pb-counters');
  if (!host) return;
  host.innerHTML = '';

  const rows = [
    el('tr', {}, [el('td', { text: 'Events replayed' }), el('td', { class: 'strong mono', text: `${fmtInt(cursor + 1)} / ${fmtInt(events.length)}` })]),
    el('tr', {}, [el('td', { text: 'Agents active' }), el('td', { class: 'strong mono', text: fmtInt(actors) })]),
    el('tr', {}, [el('td', { text: 'Resources touched' }), el('td', { class: 'strong mono', text: fmtInt(resources) })]),
    el('tr', {}, [el('td', { text: 'Shared-page writes' }), el('td', { class: 'strong mono', text: fmtInt(wiki) })]),
  ];

  if (selectedFilterNode) {
    rows.push(el('tr', {}, [
      el('td', { text: 'Selected node' }),
      el('td', { class: 'strong mono', style: 'color:var(--pastel-blue);', text: truncate(selectedFilterNode.id, 16) }),
    ]));
  }

  host.appendChild(el('table', { class: 'data' }, el('tbody', {}, rows)));
}

function renderRail() {
  const now = cursorTime();
  const host = root.querySelector('#pb-rail');
  if (!host) return;
  let revealed = 0;
  for (const card of host.children) {
    const at = card.dataset.at;
    const show = now && at && at <= now;
    card.classList.toggle('revealed', !!show);
    if (show) revealed += 1;
  }
  const badge = root.querySelector('#pb-revealed');
  if (badge) badge.textContent = `${revealed} / ${findings.length} surfaced`;
}

function update() {
  if (strip) strip.setCursor(events.length ? (cursor + 1) / events.length : 0);
  const clock = root.querySelector('#pb-clock');
  if (clock) clock.textContent = fmtClock(cursorTime());
  const slider = root.querySelector('#pb-range');
  if (slider && Number(slider.value) !== cursor) slider.value = String(cursor);
  const pill = root.querySelector('#pb-prog-pill');
  if (pill) pill.textContent = `${fmtInt(cursor + 1)} / ${fmtInt(events.length)}`;

  renderTape();
  renderCounters();
  renderRail();
}

function seekFraction(frac) {
  cursor = Math.max(0, Math.min(events.length - 1, Math.round(frac * (events.length - 1))));
  update();
}

function stopTimer() {
  if (timerId != null) {
    clearInterval(timerId);
    timerId = null;
  }
}

function setPlaying(next) {
  playing = next;
  const btn = root.querySelector('#pb-play');
  if (btn) btn.textContent = playing ? 'Pause' : 'Play';
  stopTimer();
  if (!playing || !events.length) return;
  timerId = setInterval(() => {
    const step = SPEEDS[speedIdx];
    cursor = Math.min(events.length - 1, cursor + step);
    update();
    if (cursor >= events.length - 1) setPlaying(false);
  }, 60);
}

function controls() {
  const play = el('button', { class: 'btn btn-action btn-primary-action', id: 'pb-play' }, 'Play');
  play.onclick = () => setPlaying(!playing);

  const speed = el('button', { class: 'btn btn-action', id: 'pb-speed' }, `${SPEEDS[speedIdx]}×`);
  speed.onclick = () => {
    speedIdx = (speedIdx + 1) % SPEEDS.length;
    speed.textContent = `${SPEEDS[speedIdx]}×`;
    if (playing) setPlaying(true);
  };

  const range = el('input', {
    type: 'range', id: 'pb-range', min: '0',
    max: String(Math.max(0, events.length - 1)), value: '0', step: '1',
  });
  range.oninput = () => {
    setPlaying(false);
    cursor = Number(range.value);
    update();
  };

  const progressPill = el('div', { class: 'playback-prog-pill mono', id: 'pb-prog-pill', text: `1 / ${fmtInt(events.length)}` });

  return el('div', {}, [
    el('div', { class: 'row-wrap', style: 'margin-bottom:10px; justify-content: space-between;' }, [
      el('div', { class: 'row' }, [play, speed]),
      progressPill,
    ]),
    el('div', { class: 'scrub-row' }, [range, el('div', { class: 'clock', id: 'pb-clock', text: '—' })]),
  ]);
}

function simLegend() {
  return el('div', { class: 'sim-legend-bar' }, [
    el('div', { class: 'sim-legend-item' }, [el('span', { class: 'sim-dot dot-normal' }), 'Normal Agent']),
    el('div', { class: 'sim-legend-item' }, [el('span', { class: 'sim-dot dot-alert' }), 'Violating Agent (Surfaced)']),
    el('div', { class: 'sim-legend-item' }, [el('span', { class: 'sim-pebble pebble-tool' }), 'Benchmark Tool']),
    el('div', { class: 'sim-legend-item' }, [el('span', { class: 'sim-pebble pebble-wiki' }), 'Wiki Resource']),
    el('div', { class: 'sim-legend-item' }, [el('span', { class: 'sim-pulse-line' }), 'Live Communication Filament']),
  ]);
}

function railCards() {
  const host = el('div', { class: 'findings-rail', id: 'pb-rail' });
  const sorted = findings
    .slice()
    .sort((a, b) => String(a.first_evidence_time || '').localeCompare(String(b.first_evidence_time || '')));
  for (const f of sorted) {
    host.appendChild(el('div', {
      class: 'finding-card',
      'data-at': f.first_evidence_time || '',
    }, [
      el('div', { class: 'fc-pattern', text: humanise(f.pattern) }),
      el('div', { class: 'fc-meta', text: `${f.severity} · ${truncate((f.actors || []).join(', '), 34)}` }),
      el('div', { class: 'fc-meta', text: fmtTsShort(f.first_evidence_time) }),
    ]));
  }
  return host;
}

export async function mount(el_, params) {
  root = el_;
  root.innerHTML = '<div class="page-wrap"><div id="pb-host"></div></div>';
  const host = root.querySelector('#pb-host');

  await load(['events', 'findings']);
  const s = snapshot();
  events = (s.events || []).slice();
  findings = s.findings || [];
  cursor = 0;
  playing = false;
  speedIdx = 1;
  selectedFilterNode = null;
  hoveredNode = null;

  if (!events.length) {
    host.appendChild(panel(
      'State playback',
      null,
      emptyState('No events loaded', 'Open Overview and load the benchmark fleet, then come back.'),
    ));
    return;
  }

  // 1. Scrubber & Density Panel
  const stripPanel = panel(
    'Event density & timeline scrubber',
    'Ordered event stream with shared wiki page writes highlighted. Drag slider or scrub heat strip to replay.',
    [],
  );
  host.appendChild(stripPanel);
  strip = heatStrip(stripPanel, { height: 60 });
  strip.setData(buildBuckets());
  strip.onSeek(seekFraction);
  stripPanel.appendChild(controls());

  // 2. Build Mini Simulation Canvas Element
  const simPanel = el('div', { class: 'sim-canvas-panel' });
  simCanvas = el('canvas', { class: 'sim-canvas' });
  simCtx = simCanvas.getContext('2d');
  simPanel.appendChild(simCanvas);
  simPanel.appendChild(simLegend());

  // Setup interactive listeners on simulation canvas
  simCanvas.addEventListener('mousemove', (e) => {
    const rect = simCanvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    hoveredNode = hitTest(mx, my);
    simCanvas.style.cursor = hoveredNode ? 'pointer' : 'default';
  });

  simCanvas.addEventListener('mouseleave', () => {
    hoveredNode = null;
  });

  simCanvas.addEventListener('click', (e) => {
    const rect = simCanvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const clicked = hitTest(mx, my);
    if (clicked) {
      selectedFilterNode = (selectedFilterNode && selectedFilterNode.id === clicked.id) ? null : clicked;
    } else {
      selectedFilterNode = null;
    }
    renderTape();
    renderCounters();
  });

  // 3. Main 3-column Layout
  const centerCol = el('div', { class: 'playback-center-col' }, [
    panel('Live fleet simulation', 'Interactive canvas showing communication filaments and alert flares as telemetry unfolds. Click node to filter tape.', simPanel),
    panel('Event tape', 'Chronological window of raw events around the current playback cursor.', [
      el('div', { id: 'tape-filter-host' }),
      el('div', { class: 'event-tape', id: 'tape' }),
    ]),
  ]);

  const layout = el('div', { class: 'playback-layout', style: 'margin-top:16px;' }, [
    panel('Replay telemetry', null, el('div', { id: 'pb-counters' })),
    centerCol,
    panel('Findings as they surface', null, [
      el('div', { class: 'section-sub mono', id: 'pb-revealed', text: `0 / ${findings.length} surfaced` }),
      railCards(),
    ]),
  ]);
  host.appendChild(layout);

  // Initialize nodes and start simulation
  initSimulationData();
  resizeSimulation();

  simResizeObserver = new ResizeObserver(() => {
    resizeSimulation();
  });
  simResizeObserver.observe(simPanel);

  simRafId = requestAnimationFrame(drawSimulation);

  update();
}

export function unmount() {
  stopTimer();
  playing = false;

  if (simRafId != null) {
    cancelAnimationFrame(simRafId);
    simRafId = null;
  }
  if (simResizeObserver) {
    simResizeObserver.disconnect();
    simResizeObserver = null;
  }

  simCanvas = null;
  simCtx = null;
  simNodes = [];
  simNodeMap = new Map();
  hoveredNode = null;
  selectedFilterNode = null;

  if (strip) {
    strip.destroy();
    strip = null;
  }
  events = [];
  findings = [];
  root = null;
}
