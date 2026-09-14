// Findings browser: filterable table on the left, full cited evidence on the right.
// Makes "inspectable findings with cited evidence" concrete rather than asserted.

import { api } from '../core/api.js';
import { load, snapshot } from '../core/store.js';
import { setParam } from '../core/router.js';
import { el, panel, emptyState, toast } from '../core/ui.js';
import { STATUS_TAG } from '../core/palette.js';
import { fmtUSD, fmtInt, fmtTs, fmtTsShort, humanise, truncate } from '../core/format.js';

let root = null;
let findings = [];
let judgments = [];
let filters = { q: '', pattern: '', severity: '' };
let selectedId = null;

function matches(f) {
  if (filters.pattern && f.pattern !== filters.pattern) return false;
  if (filters.severity && f.severity !== filters.severity) return false;
  if (filters.q) {
    const hay = [
      f.finding_id, f.pattern, f.severity, f.assessment, f.explanation,
      ...(f.actors || []), ...(f.target_resources || []),
    ].join(' ').toLowerCase();
    if (!hay.includes(filters.q.toLowerCase())) return false;
  }
  return true;
}

function renderTable() {
  const host = root.querySelector('#fd-table');
  if (!host) return;
  host.innerHTML = '';

  const rows = findings.filter(matches);
  if (!rows.length) {
    host.appendChild(emptyState(
      findings.length ? 'No findings match these filters' : 'No findings yet',
      findings.length ? 'Try clearing the search box.' : 'Load the benchmark fleet from Overview.',
    ));
    return;
  }

  const table = el('table', { class: 'data' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Pattern' }),
      el('th', { text: 'Sev' }),
      el('th', { text: 'Actors' }),
      el('th', { text: 'First evidence' }),
      el('th', { text: 'Cited' }),
    ])),
  ]);
  const tbody = el('tbody');
  for (const f of rows) {
    const tr = el('tr', {
      class: `clickable${f.finding_id === selectedId ? ' selected' : ''}`,
      onclick: () => select(f.finding_id),
    }, [
      el('td', { class: 'strong', text: humanise(f.pattern) }),
      el('td', {}, el('span', { class: `tag ${STATUS_TAG[f.severity] || ''}`, text: f.severity })),
      el('td', { text: truncate((f.actors || []).join(', '), 38) }),
      el('td', { class: 'mono', text: fmtTsShort(f.first_evidence_time) }),
      el('td', { class: 'mono', text: String((f.evidence_ids || []).length) }),
    ]);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  host.appendChild(table);

  const count = root.querySelector('#fd-count');
  if (count) count.textContent = `${rows.length} of ${findings.length} findings`;
}

async function renderDetail() {
  const host = root.querySelector('#fd-detail');
  if (!host) return;
  host.innerHTML = '';

  const f = findings.find((x) => x.finding_id === selectedId);
  if (!f) {
    host.appendChild(panel('Evidence', null, emptyState('Select a finding', 'Its cited evidence appears here.')));
    return;
  }

  const head = el('div', {}, [
    el('div', { class: 'section-title', text: humanise(f.pattern) }),
    el('div', { class: 'row-wrap', style: 'margin-bottom:10px;' }, [
      el('span', { class: `tag ${STATUS_TAG[f.severity] || ''}`, text: f.severity }),
      el('span', { class: 'tag', text: f.assessment }),
      el('span', { class: 'tag mono', text: f.finding_id }),
      f.is_audit_sample ? el('span', { class: 'tag blue', text: 'audit sample' }) : null,
    ]),
    el('div', { class: 'section-sub', style: 'margin-bottom:12px;', text: f.explanation || '—' }),
  ]);

  const facts = el('table', { class: 'data' }, el('tbody', {}, [
    el('tr', {}, [el('td', { text: 'Actors' }), el('td', { class: 'strong', text: (f.actors || []).join(', ') || '—' })]),
    el('tr', {}, [el('td', { text: 'Resources' }), el('td', { text: (f.target_resources || []).join(', ') || '—' })]),
    el('tr', {}, [el('td', { text: 'First evidence' }), el('td', { class: 'mono', text: fmtTs(f.first_evidence_time) })]),
    el('tr', {}, [el('td', { text: 'Detected at' }), el('td', { class: 'mono', text: fmtTs(f.detected_at) })]),
    el('tr', {}, [el('td', { text: 'Cited evidence' }), el('td', { class: 'mono', text: (f.evidence_ids || []).join(', ') || '—' })]),
  ]));

  const detail = panel(null, null, [head, facts]);
  host.appendChild(detail);

  // Judge record for this finding, if one was accepted.
  const j = judgments.find((x) => x.check_key === f.check_key);
  if (j) {
    const usage = j.billed_usage || {};
    host.appendChild(panel('Judge record', null, el('table', { class: 'data' }, el('tbody', {}, [
      el('tr', {}, [el('td', { text: 'Model' }), el('td', { class: 'mono strong', text: j.model || '—' })]),
      el('tr', {}, [el('td', { text: 'Assessment' }), el('td', { text: j.assessment || '—' })]),
      el('tr', {}, [el('td', { text: 'Billed tokens' }), el('td', { class: 'mono', text: `${fmtInt(usage.prompt_tokens)} in / ${fmtInt(usage.completion_tokens)} out` })]),
      el('tr', {}, [el('td', { text: 'Cost' }), el('td', { class: 'mono', text: fmtUSD(usage.estimated_cost_usd, 6) })]),
      el('tr', {}, [el('td', { text: 'Missing context' }), el('td', { text: (j.missing_context || []).join(', ') || 'none reported' })]),
    ]))));
  }

  // Full evidence packet: the chronological record the judge actually read.
  // A finding cites evidence IDs (ev_01), not packet IDs — the judgment for the same
  // check_key is what carries packet_id, so resolve through it rather than guessing.
  const packetId = j && j.packet_id ? j.packet_id : null;
  const packetPanel = panel('Cited evidence packet', null, el('div', { class: 'dim', text: 'Loading…' }));
  host.appendChild(packetPanel);

  // Resolve the packet lazily. The full packet list is ~1.4MB, so it is fetched
  // once only if the direct lookup misses, and then reused from the store.
  let packet = null;
  if (packetId) {
    try {
      packet = await api.evidencePacket(packetId);
    } catch (_) { /* finding cites evidence IDs, which are not packet IDs */ }
  }
  if (!packet) {
    await load(['evidence']);
    const packets = snapshot().evidence || [];
    packet = packets.find((p) =>
      (p.chronological_events || []).some((e) => (f.evidence_ids || []).includes(e.evidence_id)));
  }

  packetPanel.innerHTML = '';
  packetPanel.appendChild(el('div', { class: 'section-title', text: 'Cited evidence packet' }));
  if (!packet) {
    packetPanel.appendChild(emptyState('Packet not resolvable', 'This finding cites evidence IDs that no stored packet matches.'));
    return;
  }

  packetPanel.appendChild(el('div', { class: 'row-wrap', style: 'margin-bottom:10px;' }, [
    el('span', { class: 'tag mono', text: packet.packet_id }),
    el('span', { class: 'tag', text: `~${fmtInt(packet.token_count_estimate)} tokens` }),
    el('span', { class: 'tag', text: `${(packet.chronological_events || []).length} events` }),
  ]));

  if ((packet.trigger_reasons || []).length) {
    packetPanel.appendChild(el('div', { class: 'section-sub', text: `Triggered by: ${packet.trigger_reasons.join(', ')}` }));
  }
  if ((packet.missing_context_flags || []).length) {
    packetPanel.appendChild(el('div', { class: 'row-wrap', style: 'margin-bottom:10px;' },
      packet.missing_context_flags.map((m) => el('span', { class: 'tag amber', text: m }))));
  }
  if ((packet.applicable_policies || []).length) {
    packetPanel.appendChild(el('div', { class: 'section-sub', text: 'Policies: ' +
      packet.applicable_policies.map((p) => `${p.policy_id} — ${p.rule}`).join(' · ') }));
  }

  const timeline = el('div', {});
  for (const ev of packet.chronological_events || []) {
    const wiki = String(ev.action_type || '').includes('write')
      || String(ev.summary || '').toLowerCase().includes('wiki');
    timeline.appendChild(el('div', { class: `evidence-event${wiki ? ' is-wiki' : ''}` }, [
      el('div', { class: 'ee-head', text: `${ev.evidence_id} · ${fmtTsShort(ev.timestamp)} · ${ev.actor_id}` }),
      el('div', { class: 'ee-summary', text: ev.summary || ev.action_type || '—' }),
      ev.snippet ? el('div', { class: 'ee-snippet', text: ev.snippet }) : null,
    ]));
  }
  packetPanel.appendChild(timeline);
}

function select(id) {
  selectedId = id;
  setParam('id', id);
  renderTable();
  renderDetail();
}

function filterBar() {
  const patterns = [...new Set(findings.map((f) => f.pattern))].sort();
  const severities = [...new Set(findings.map((f) => f.severity))].sort();

  const q = el('input', { class: 'filter-input', type: 'search', placeholder: 'Search actor, pattern, explanation…' });
  q.oninput = () => { filters.q = q.value; renderTable(); };

  const pSel = el('select', { class: 'filter-input' }, [
    el('option', { value: '', text: 'All patterns' }),
    ...patterns.map((p) => el('option', { value: p, text: humanise(p) })),
  ]);
  pSel.onchange = () => { filters.pattern = pSel.value; renderTable(); };

  const sSel = el('select', { class: 'filter-input' }, [
    el('option', { value: '', text: 'All severities' }),
    ...severities.map((s) => el('option', { value: s, text: s })),
  ]);
  sSel.onchange = () => { filters.severity = sSel.value; renderTable(); };

  return el('div', { class: 'row-wrap', style: 'margin-bottom:12px;' }, [
    q, pSel, sSel,
    el('span', { class: 'spacer' }),
    el('span', { class: 'dim mono', id: 'fd-count', style: 'font-size:0.68rem;' }),
  ]);
}

export async function mount(el_, params = {}) {
  root = el_;
  root.innerHTML = '<div class="page-wrap"><div id="fd-host"></div></div>';
  const host = root.querySelector('#fd-host');

  await load(['findings', 'judgments']);
  const s = snapshot();
  findings = s.findings || [];
  judgments = s.judgments || [];
  filters = { q: '', pattern: '', severity: '' };
  selectedId = params.id || (findings[0] && findings[0].finding_id) || null;

  const layout = el('div', { class: 'findings-layout' }, [
    el('div', {}, [
      panel('Findings', 'Every confirmed finding, with the evidence the judge cited.', [
        filterBar(),
        el('div', { id: 'fd-table' }),
      ]),
    ]),
    el('div', { id: 'fd-detail' }),
  ]);
  host.appendChild(layout);

  renderTable();
  await renderDetail();
}

export function unmount() {
  root = null;
  findings = [];
  judgments = [];
  selectedId = null;
}
