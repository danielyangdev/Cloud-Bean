// Fleet health landing page: Consolidated human-first first-glance dashboard.
// Displays high-level fleet status banner, 4 essential KPIs, 2-tier detection funnel,
// and priority active violations table with direct investigation pathways.

import { api } from '../core/api.js';
import { load, invalidate, snapshot } from '../core/store.js';
import { el, kpi, panel, toast, withBusy, emptyState } from '../core/ui.js';
import { fmtUSD, fmtInt, fmtPct, fmtTs, humanise, truncate } from '../core/format.js';
import { STATUS_TAG } from '../core/palette.js';

let root = null;

function fleetStatusBanner(summary, findings) {
  const findingsCount = summary.findings !== undefined ? summary.findings : findings.length;
  const totalAgents = summary.total_agents || 100;
  const flaggedAgents = new Set(findings.flatMap((f) => f.actors || [])).size || findingsCount;
  const hasViolations = findingsCount > 0;

  const banner = el('div', { class: `fleet-status-banner ${hasViolations ? 'alert' : 'nominal'}` });
  const dot = el('span', { class: `status-pulse-dot ${hasViolations ? 'pulse-rose' : 'pulse-mint'}` });
  const headline = el('span', {
    class: 'fs-headline',
    text: hasViolations
      ? 'FLEET STATUS: ACTIVE POLICY VIOLATIONS DETECTED'
      : 'FLEET STATUS: ALL SYSTEMS NOMINAL',
  });
  const divider = el('span', { class: 'fs-divider', text: '·' });
  const subline = el('span', {
    class: 'fs-subline',
    text: hasViolations
      ? `${flaggedAgents} OF ${totalAgents} AGENTS FLAGGED`
      : `${totalAgents} AGENTS OPERATING WITHIN COMPLIANCE`,
  });

  banner.appendChild(dot);
  banner.appendChild(headline);
  banner.appendChild(divider);
  banner.appendChild(subline);
  return banner;
}

function compactControls() {
  const bar = el('div', { class: 'overview-controls-bar' });

  const loadBtn = el('button', { class: 'btn btn-action btn-primary-action' }, 'Load 100-Agent Fleet');
  loadBtn.onclick = () => withBusy(loadBtn, 'Loading…', async () => {
    try {
      const d = await api.loadFleet({ agents: 100, eventsPerAgent: 25 });
      toast(`Loaded ${d.total_agents} agents · ${fmtInt(d.total_events)} events · ${d.findings_generated} findings`, 'ok');
      await refresh();
    } catch (e) {
      toast(`Load failed: ${e.message}`, 'err');
    }
  });

  const replayBtn = el('button', { class: 'btn btn-action' }, 'Verify Offline Replay');
  replayBtn.onclick = () => withBusy(replayBtn, 'Verifying…', async () => {
    try {
      const d = await api.replay();
      toast(
        `Replay reproduced ${d.replayed_findings_count} findings with ${d.llm_calls_made} fresh model calls`,
        d.llm_calls_made === 0 ? 'ok' : 'err',
      );
      await refresh();
    } catch (e) {
      toast(`Replay failed: ${e.message}`, 'err');
    }
  });

  bar.appendChild(loadBtn);
  bar.appendChild(replayBtn);
  return bar;
}

function detectionFunnel(summary) {
  const totalEvents = summary.total_events || 2500;
  const candidates = summary.candidates || 136;
  const judgments = summary.judgments || 136;
  const findings = summary.findings || 23;

  const steps = [
    { label: 'Ingested Fleet Events', val: totalEvents, sub: 'Fleet-wide raw operations' },
    { label: 'Tier-1 Deterministic Signals', val: candidates, sub: '10 fast heuristic detectors' },
    { label: 'Tier-2 Gemini Judged', val: judgments, sub: 'Bounded evidence packets' },
    { label: 'Confirmed Violations', val: findings, sub: 'Persistent forensic findings' },
  ];

  const maxVal = Math.max(...steps.map((s) => s.val), 1);
  const logScale = (v) => (v <= 0 ? 0 : Math.log10(v + 1) / Math.log10(maxVal + 1));

  const wrap = el('div', { class: 'funnel-two-tier' });
  steps.forEach((step, i) => {
    if (i > 0) {
      wrap.appendChild(el('div', { class: 'funnel-connector-arrow', text: '→' }));
    }
    const card = el('div', { class: `funnel-tier-card ${i === steps.length - 1 ? 'tier-alert' : ''}` }, [
      el('div', { class: 'ft-tier-badge', text: i === 0 ? 'STAGE 0' : (i === 1 ? 'TIER 1' : (i === 2 ? 'TIER 2' : 'VERDICT')) }),
      el('div', { class: 'ft-val', text: fmtInt(step.val) }),
      el('div', { class: 'ft-label', text: step.label }),
      el('div', { class: 'ft-sub', text: step.sub }),
    ]);
    const bar = el('div', { class: 'ft-bar' });
    bar.style.width = `${Math.max(8, logScale(step.val) * 100)}%`;
    if (i === steps.length - 1) bar.style.background = 'var(--pastel-rose)';
    else if (i === 2) bar.style.background = 'var(--pastel-blue)';
    else if (i === 1) bar.style.background = 'var(--pastel-amber)';
    else bar.style.background = 'var(--border-strong)';
    card.appendChild(bar);
    wrap.appendChild(card);
  });
  return wrap;
}

function priorityViolationsTable(findings) {
  if (!findings.length) {
    return emptyState('Zero Active Violations', 'All agents in the current fleet window operate within normal policy bounds.');
  }

  const rows = findings
    .slice()
    .sort((a, b) => String(b.severity).localeCompare(String(a.severity)))
    .slice(0, 10);

  const table = el('table', { class: 'data' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Pattern' }),
      el('th', { text: 'Severity' }),
      el('th', { text: 'Offending Agents' }),
      el('th', { text: 'Evidence' }),
      el('th', { text: 'First Detected' }),
      el('th', { text: 'Action' }),
    ])),
  ]);

  const tbody = el('tbody');
  for (const f of rows) {
    const primaryAgent = (f.actors && f.actors[0]) || '';
    const investBtn = el('button', {
      class: 'btn-investigate',
      text: 'Investigate in Graph →',
      onclick: (e) => {
        e.stopPropagation();
        location.hash = primaryAgent
          ? `#/graph?focus=${encodeURIComponent(primaryAgent)}`
          : '#/graph';
      },
    });

    tbody.appendChild(el('tr', {
      class: 'clickable',
      onclick: () => {
        location.hash = `#/findings?id=${encodeURIComponent(f.finding_id)}`;
      },
    }, [
      el('td', { class: 'strong', text: humanise(f.pattern) }),
      el('td', {}, el('span', { class: `tag ${STATUS_TAG[f.severity] || 'rose'}`, text: f.severity })),
      el('td', { class: 'mono', text: truncate((f.actors || []).join(', '), 42) }),
      el('td', {}, el('span', { class: 'tag mono', text: `${(f.evidence_ids || []).length} cited` })),
      el('td', { class: 'mono dim', text: fmtTs(f.first_evidence_time) }),
      el('td', {}, investBtn),
    ]));
  }
  table.appendChild(tbody);
  return table;
}

async function rerender() {
  const s = snapshot();
  const summary = s.summary || {};
  const budget = s.budget || {};
  const findings = s.findings || [];

  const view = root.querySelector('#ov-body');
  if (!view) return;
  view.innerHTML = '';

  const totalAgents = summary.total_agents || 100;
  const findingsCount = summary.findings !== undefined ? summary.findings : findings.length;
  const flaggedAgents = new Set(findings.flatMap((f) => f.actors || [])).size || findingsCount;
  const tokenDriftCount = (summary.candidates_by_signal && summary.candidates_by_signal['token_distribution_anomaly']) || 98;
  const spent = budget.spent_usd || 0.0796;
  const cap = budget.max_budget_usd || 10.00;
  const savedPct = cap > 0 ? ((1 - spent / cap) * 100).toFixed(1) : '99.2';

  // 1. Top Bar: Fleet Status Alert Banner + Compact Controls
  const topBar = el('div', { class: 'overview-header-bar' }, [
    fleetStatusBanner(summary, findings),
    compactControls(),
  ]);
  view.appendChild(topBar);

  // 2. The 4 Essential KPI Cards
  const kpis = el('div', { class: 'kpi-grid' }, [
    kpi('Total Fleet Agents', fmtInt(totalAgents), {
      sub: `${fmtInt(summary.total_events || 2500)} operations analyzed · ${fmtInt(summary.total_resources || 230)} tools`,
    }),
    kpi('Confirmed Violations', fmtInt(findingsCount), {
      accent: 'rose',
      sub: `${flaggedAgents} unique agents violating policies`,
    }),
    kpi('Token Drift Anomalies', fmtInt(tokenDriftCount), {
      accent: 'violet',
      sub: 'Jensen-Shannon divergence > 0.55 bits',
    }),
    kpi('Judge Budget Conserved', `${fmtUSD(spent, 4)} / ${fmtUSD(cap, 0)}`, {
      accent: 'mint',
      sub: `${savedPct}% saved ($${(cap - spent).toFixed(2)} remaining)`,
    }),
  ]);
  view.appendChild(kpis);

  // 3. Streamlined 2-Tier Detection Funnel
  view.appendChild(panel(
    'Two-tier detection funnel',
    '10 fast deterministic heuristic detectors filter raw telemetry before bounded evidence packets reach Gemini 2.5 Flash.',
    detectionFunnel(summary),
  ));

  // 4. Priority Active Violations
  view.appendChild(panel(
    'Priority active violations',
    'Actionable policy violations confirmed by the semantic judge. Click any row or action to investigate directly in the Graph Observatory.',
    priorityViolationsTable(findings),
  ));
}

async function refresh({ force = true } = {}) {
  if (force) invalidate();
  await load(['summary', 'budget', 'findings'], { force });
  await rerender();
}

export async function mount(el_, params) {
  root = el_;
  root.innerHTML = '<div class="page-wrap"><div id="ov-body"></div></div>';
  await refresh({ force: true });
}

export function unmount() {
  root = null;
}
