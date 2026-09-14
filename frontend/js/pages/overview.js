// Fleet health landing page: KPIs, the detection funnel, signal coverage,
// top findings, and the demo control rail.

import { api } from '../core/api.js';
import { load, invalidate, snapshot } from '../core/store.js';
import { el, kpi, panel, toast, withBusy, emptyState } from '../core/ui.js';
import { fmtUSD, fmtInt, fmtPct, fmtTs, humanise, truncate } from '../core/format.js';
import { STATUS_TAG } from '../core/palette.js';

const ALL_SIGNALS = [
  'emerging_hub',
  'conflicting_writes',
  'shared_artifact_reuse',
  'collective_overload',
  'synchronized_burstiness',
  'rapid_adoption_latency',
  'proxy_tunneling_anomaly',
  'token_distribution_anomaly',
  'compression_distance_anomaly',
  'audit_sample',
];

let root = null;

function funnel(summary) {
  const steps = [
    ['Events ingested', summary.total_events],
    ['Candidate groups', summary.candidates],
    ['Evidence packets', summary.evidence_packets],
    ['Judgments recorded', summary.judgments],
    ['Findings', summary.findings],
  ];
  // The funnel spans orders of magnitude (thousands of events down to a handful of
  // findings), so a linear bar makes every step after the first invisible. A log
  // scale keeps the narrowing legible while still shrinking monotonically.
  const max = Math.max(...steps.map(([, v]) => v), 1);
  const scale = (v) => (v <= 0 ? 0 : Math.log10(v + 1) / Math.log10(max + 1));

  const wrap = el('div', { class: 'funnel' });
  steps.forEach(([label, value], i) => {
    if (i) wrap.appendChild(el('div', { class: 'funnel-arrow', text: '→' }));
    const step = el('div', { class: 'funnel-step' }, [
      el('div', { class: 'fs-val', text: fmtInt(value) }),
      el('div', { class: 'fs-label', text: label }),
    ]);
    const bar = el('div', { class: 'fs-bar' });
    bar.style.width = `${Math.max(6, scale(value) * 100)}%`;
    if (i === steps.length - 1) bar.style.background = 'var(--pastel-rose)';
    else if (i > 0) bar.style.background = 'var(--pastel-amber)';
    step.appendChild(bar);
    wrap.appendChild(step);
  });
  return wrap;
}

function signalGrid(summary) {
  const counts = summary.candidates_by_signal || {};
  const grid = el('div', { class: 'signal-grid' });
  for (const name of ALL_SIGNALS) {
    const n = counts[name] || 0;
    grid.appendChild(el('div', { class: `signal-tile ${n ? 'fired' : 'idle'}` }, [
      el('div', { class: 'st-name', text: humanise(name) }),
      el('div', { class: 'st-count', text: n ? `${n} flagged` : 'idle' }),
    ]));
  }
  return grid;
}

function findingsTable(findings) {
  if (!findings.length) {
    return emptyState('No findings yet', 'Load the benchmark fleet to run the detection pipeline.');
  }
  const rows = findings
    .slice()
    .sort((a, b) => String(b.severity).localeCompare(String(a.severity)))
    .slice(0, 12);

  const table = el('table', { class: 'data' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Pattern' }),
      el('th', { text: 'Severity' }),
      el('th', { text: 'Actors' }),
      el('th', { text: 'First evidence' }),
      el('th', { text: 'Evidence' }),
    ])),
  ]);
  const tbody = el('tbody');
  for (const f of rows) {
    tbody.appendChild(el('tr', { class: 'clickable', onclick: () => { location.hash = `#/findings?id=${encodeURIComponent(f.finding_id)}`; } }, [
      el('td', { class: 'strong', text: humanise(f.pattern) }),
      el('td', {}, el('span', { class: `tag ${STATUS_TAG[f.severity] || ''}`, text: f.severity })),
      el('td', { text: truncate((f.actors || []).join(', '), 44) }),
      el('td', { class: 'mono', text: fmtTs(f.first_evidence_time) }),
      el('td', {}, el('span', { class: 'tag mono', text: `${(f.evidence_ids || []).length} cited` })),
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
  view.innerHTML = '';

  const spent = budget.spent_usd || 0;
  const cap = budget.max_budget_usd || 0;

  const kpis = el('div', { class: 'kpi-grid' }, [
    kpi('Agents monitored', fmtInt(summary.total_agents), { sub: `${fmtInt(summary.total_resources)} resources touched` }),
    kpi('Events ingested', fmtInt(summary.total_events), {
      sub: summary.window && summary.window.start ? `since ${fmtTs(summary.window.start)}` : 'no window yet',
    }),
    kpi('Candidate groups', fmtInt(summary.candidates), { accent: 'amber', sub: 'selected for inspection' }),
    kpi('Confirmed findings', fmtInt(summary.findings), { accent: 'rose', sub: `${fmtInt(summary.judgments)} judgments recorded` }),
    kpi('Judge spend', fmtUSD(spent), {
      accent: 'mint',
      sub: cap ? `of ${fmtUSD(cap, 2)} cap · ${fmtPct((spent / cap) * 100)}` : 'no cap set',
    }),
    kpi('Evidence coverage', fmtPct((summary.coverage_ratio || 0) * 100), {
      accent: 'violet',
      sub: `${fmtInt(summary.events_covered_by_evidence)} events cited`,
    }),
  ]);
  view.appendChild(kpis);

  view.appendChild(panel(
    'Detection funnel',
    'Cheap rules and group statistics narrow the whole event stream down to the few groups worth paying a model to read.',
    funnel(summary),
  ));

  view.appendChild(panel(
    'Signal coverage',
    'Which of the ten Tier-1 detectors fired on the current window.',
    signalGrid(summary),
  ));

  view.appendChild(panel(
    'Top findings',
    'Click a row to open its cited evidence.',
    findingsTable(findings),
  ));
}

async function refresh({ force = true } = {}) {
  if (force) invalidate();
  await load(['summary', 'budget', 'findings'], { force });
  await rerender();
}

function controlRail() {
  const rail = el('div', { class: 'panel' });
  rail.appendChild(el('div', { class: 'section-title', text: 'Demo controls' }));
  rail.appendChild(el('div', {
    class: 'section-sub',
    text: 'Everything below runs against recorded traces and stored judgments — no live model calls.',
  }));

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

  const replayBtn = el('button', { class: 'btn btn-action' }, 'Verify Replay');
  replayBtn.onclick = () => withBusy(replayBtn, 'Replaying…', async () => {
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

  const resetBtn = el('button', { class: 'btn btn-action' }, 'Reset Events');
  resetBtn.onclick = () => withBusy(resetBtn, 'Resetting…', async () => {
    try {
      const d = await api.reset();
      toast(`Cleared ${fmtInt(d.events_cleared)} events from the working buffer`);
      await refresh();
    } catch (e) {
      toast(`Reset failed: ${e.message}`, 'err');
    }
  });

  rail.appendChild(el('div', { class: 'row-wrap' }, [loadBtn, replayBtn, resetBtn]));

  rail.appendChild(el('div', { class: 'section-title', text: 'Inject a failure', style: 'margin-top:16px;' }));
  rail.appendChild(el('div', {
    class: 'section-sub',
    text: 'Replays the current window through a fault to show findings stay stable under broken telemetry.',
  }));

  const modes = [
    ['duplicates', 'Duplicate Delivery'],
    ['reordering', 'Out-of-Order Delivery'],
    ['collector_outage', 'Collector Outage'],
    ['budget_exhaustion', 'Budget Exhaustion'],
  ];
  const faultRow = el('div', { class: 'row-wrap' });
  for (const [mode, label] of modes) {
    const b = el('button', { class: 'btn btn-action' }, label);
    b.onclick = () => withBusy(b, 'Injecting…', async () => {
      try {
        const d = await api.injectFailure(mode);
        const stable = d.findings_after === d.findings_before;
        const detail = mode === 'budget_exhaustion'
          ? `${d.checks_budget_exhausted} checks recorded as budget-exhausted rather than healthy`
          : `findings ${d.findings_before} → ${d.findings_after}${stable ? ' (unchanged)' : ' (CHANGED)'}`;
        toast(`${label}: ${detail}. ${d.note}`, stable ? 'ok' : 'err');
        await refresh();
      } catch (e) {
        toast(`${label} failed: ${e.message}`, 'err');
      }
    });
    faultRow.appendChild(b);
  }
  rail.appendChild(faultRow);
  return rail;
}

export async function mount(el_, params) {
  root = el_;
  root.innerHTML = '<div class="page-wrap"><div id="ov-controls"></div><div id="ov-body"></div></div>';
  root.querySelector('#ov-controls').appendChild(controlRail());
  await refresh({ force: true });
}

export function unmount() {
  root = null;
}
