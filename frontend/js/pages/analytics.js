// Analytics: signal/pattern distributions, shared-resource concentration, and
// cumulative judge spend against the cap. All charts are hand-rolled canvas.

import { load, snapshot } from '../core/store.js';
import { horizontalBars, lineChart } from '../charts/chart.js';
import { el, panel, emptyState } from '../core/ui.js';
import { PALETTE } from '../core/palette.js';
import { fmtUSD, fmtNum, humanise, stripPrefix, fmtTsShort } from '../core/format.js';

let root = null;
let charts = [];

function countBy(items, key) {
  const out = new Map();
  for (const it of items) {
    const k = typeof key === 'function' ? key(it) : it[key];
    if (k == null) continue;
    out.set(k, (out.get(k) || 0) + 1);
  }
  return [...out.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

function spendSeries(judgments, cap) {
  const sorted = judgments
    .filter((j) => j.evaluated_at)
    .slice()
    .sort((a, b) => String(a.evaluated_at).localeCompare(String(b.evaluated_at)));
  let running = 0;
  const points = sorted.map((j, i) => {
    const cost = (j.billed_usage && j.billed_usage.estimated_cost_usd) || 0;
    running += cost;
    return { x: i, y: running, label: `check ${i + 1} ·` };
  });
  return { points, total: running, cap };
}

function signalMetricsTable(candidates) {
  // Each detector emits a flat metrics dict per window. Show them as-is rather
  // than fabricating a time series the backend does not produce.
  const bySignal = new Map();
  for (const c of candidates) {
    if (!bySignal.has(c.trigger_signal)) bySignal.set(c.trigger_signal, c);
  }
  const table = el('table', { class: 'data' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Signal' }),
      el('th', { text: 'Actors' }),
      el('th', { text: 'Representative metrics' }),
    ])),
  ]);
  const tbody = el('tbody');
  for (const [signal, c] of bySignal) {
    const metrics = Object.entries(c.metrics || {})
      .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
      .slice(0, 4)
      .map(([k, v]) => `${k}=${typeof v === 'number' ? fmtNum(v, 3) : v}`)
      .join('  ');
    tbody.appendChild(el('tr', {}, [
      el('td', { class: 'strong', text: humanise(signal) }),
      el('td', { class: 'mono', text: String((c.actors || []).length) }),
      el('td', { class: 'mono dim', text: metrics || '—' }),
    ]));
  }
  table.appendChild(tbody);
  return table;
}

export async function mount(el_) {
  root = el_;
  root.innerHTML = '<div class="page-wrap"><div id="an-host"></div></div>';
  const host = root.querySelector('#an-host');

  await load(['candidates', 'findings', 'judgments', 'budget', 'events']);
  const s = snapshot();
  const candidates = s.candidates || [];
  const findings = s.findings || [];
  const judgments = s.judgments || [];
  const budget = s.budget || {};
  const events = s.events || [];

  if (!candidates.length && !events.length) {
    host.appendChild(panel(
      'Analytics',
      null,
      emptyState('Nothing to chart yet', 'Load the benchmark fleet from Overview first.'),
    ));
    return;
  }

  const grid = el('div', { class: 'chart-grid' });
  host.appendChild(grid);

  // 1. Candidates by trigger signal
  const p1 = panel('Candidates by signal', 'Which detectors selected groups for inspection.', []);
  grid.appendChild(p1);
  charts.push(horizontalBars(
    p1,
    countBy(candidates, 'trigger_signal').map((r) => ({ ...r, label: humanise(r.label), color: PALETTE.amber })),
  ));

  // 2. Findings by pattern
  const p2 = panel('Findings by pattern', 'Confirmed findings grouped by the pattern the judge assigned.', []);
  grid.appendChild(p2);
  const patterns = countBy(findings, 'pattern').map((r) => ({ ...r, label: humanise(r.label), color: PALETTE.rose }));
  if (patterns.length) charts.push(horizontalBars(p2, patterns));
  else p2.appendChild(emptyState('No findings yet', 'The judge has not confirmed any pattern on this window.'));

  // 3. Shared-resource concentration — the emerging-hub case, visually
  const p3 = panel(
    'Most-written shared resources',
    'Concentration is what drives the emerging-hub signal: many independent agents converging on one page.',
    [],
  );
  grid.appendChild(p3);
  const writes = events.filter((e) => String(e.target || '').startsWith('wiki:'));
  const topPages = countBy(writes, (e) => stripPrefix(e.target)).slice(0, 14);
  if (topPages.length) {
    charts.push(horizontalBars(p3, topPages.map((r) => ({ ...r, color: PALETTE.violet })), { maxLabel: 210 }));
  } else {
    p3.appendChild(emptyState('No shared-page writes', 'This window contains no wiki resource writes.'));
  }

  // 4. Cumulative spend vs cap
  const { points: pts0, total: total0, cap: cap0 } = spendSeries(judgments, budget.max_budget_usd || 0);
  const capOffScale = cap0 && total0 && cap0 > total0 * 1.35;
  const p4 = panel(
    'Cumulative judge spend',
    capOffScale
      ? `Cost accrues per recorded judgment. Spend is far under the ${fmtUSD(cap0, 2)} cap, so the axis is scaled to actual spend.`
      : 'Cost accrues per recorded judgment. The dashed rule is the hard budget cap.',
    [],
  );
  grid.appendChild(p4);
  const { points, total, cap } = { points: pts0, total: total0, cap: cap0 };
  if (points.length) {
    charts.push(lineChart(p4, points, {
      height: 220,
      rule: cap || null,
      ruleLabel: cap ? `cap ${fmtUSD(cap, 2)}` : '',
      color: PALETTE.mint,
      yFormat: (v) => fmtUSD(v, 3),
    }));
    p4.appendChild(el('div', {
      class: 'section-sub mono',
      style: 'margin-top:10px;margin-bottom:0;',
      text: `${points.length} judgments · ${fmtUSD(total)} spent` +
        (cap ? ` · ${fmtNum((total / cap) * 100, 2)}% of cap` : ''),
    }));
  } else {
    p4.appendChild(emptyState('No judgments recorded', 'Spend accrues once the judge evaluates evidence packets.'));
  }

  // 5. Per-signal metrics table
  if (candidates.length) {
    host.appendChild(panel(
      'Signal metrics',
      'One representative window per detector. These are per-window scalars, not time series.',
      signalMetricsTable(candidates),
    ));
  }
}

export function unmount() {
  for (const c of charts) {
    try { c.destroy(); } catch (_) { /* already gone */ }
  }
  charts = [];
  root = null;
}
