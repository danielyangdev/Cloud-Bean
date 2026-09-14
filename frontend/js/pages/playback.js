// State playback: scrub the fleet's event stream and watch findings surface.
//
// The whole event stream is fetched once and the cursor is pure client state, so
// scrubbing is instant and makes no network calls. The axis is ordinal (event
// index) rather than wall-clock, so density is even no matter how the underlying
// timestamps cluster; the real timestamp is shown as the label.

import { load, snapshot } from '../core/store.js';
import { heatStrip } from '../charts/chart.js';
import { el, panel, emptyState } from '../core/ui.js';
import { fmtInt, fmtClock, fmtTsShort, humanise, truncate, stripPrefix, escapeHtml } from '../core/format.js';

const BUCKETS = 140;
const TAPE_ROWS = 34;
const SPEEDS = [1, 4, 16, 64];

let root = null;
let strip = null;
let events = [];
let findings = [];
let cursor = 0;          // event ordinal
let playing = false;
let speedIdx = 1;
let timerId = null;

function isWiki(ev) {
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

function renderTape() {
  const host = root.querySelector('#tape');
  if (!host) return;
  const start = Math.max(0, cursor - TAPE_ROWS + 6);
  const slice = events.slice(start, start + TAPE_ROWS);
  host.innerHTML = slice.map((ev, i) => {
    const idx = start + i;
    const cls = `tape-row${idx === cursor ? ' cursor' : ''}${isWiki(ev) ? ' wiki' : ''}`;
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
  host.appendChild(el('table', { class: 'data' }, el('tbody', {}, [
    el('tr', {}, [el('td', { text: 'Events replayed' }), el('td', { class: 'strong mono', text: `${fmtInt(cursor + 1)} / ${fmtInt(events.length)}` })]),
    el('tr', {}, [el('td', { text: 'Agents active' }), el('td', { class: 'strong mono', text: fmtInt(actors) })]),
    el('tr', {}, [el('td', { text: 'Resources touched' }), el('td', { class: 'strong mono', text: fmtInt(resources) })]),
    el('tr', {}, [el('td', { text: 'Shared-page writes' }), el('td', { class: 'strong mono', text: fmtInt(wiki) })]),
  ])));
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
  strip.setCursor(events.length ? (cursor + 1) / events.length : 0);
  const clock = root.querySelector('#pb-clock');
  if (clock) clock.textContent = fmtClock(cursorTime());
  const slider = root.querySelector('#pb-range');
  if (slider && Number(slider.value) !== cursor) slider.value = String(cursor);
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

  const restart = el('button', { class: 'btn btn-action' }, 'Restart');
  restart.onclick = () => {
    setPlaying(false);
    cursor = 0;
    update();
  };

  const end = el('button', { class: 'btn btn-action' }, 'Jump to End');
  end.onclick = () => {
    setPlaying(false);
    cursor = Math.max(0, events.length - 1);
    update();
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

  return el('div', {}, [
    el('div', { class: 'row-wrap', style: 'margin-bottom:10px;' }, [play, speed, restart, end]),
    el('div', { class: 'scrub-row' }, [range, el('div', { class: 'clock', id: 'pb-clock', text: '—' })]),
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

  if (!events.length) {
    host.appendChild(panel(
      'State playback',
      null,
      emptyState('No events loaded', 'Open Overview and load the benchmark fleet, then come back.'),
    ));
    return;
  }

  const stripPanel = panel(
    'Event density',
    'Each column is a slice of the ordered event stream; violet marks writes to shared wiki pages. Click to seek.',
    [],
  );
  host.appendChild(stripPanel);
  strip = heatStrip(stripPanel, { height: 64 });
  strip.setData(buildBuckets());
  strip.onSeek(seekFraction);
  stripPanel.appendChild(controls());

  const layout = el('div', { class: 'playback-layout', style: 'margin-top:16px;' }, [
    panel('Replay state', null, el('div', { id: 'pb-counters' })),
    panel('Event tape', 'The window of raw events around the cursor.', el('div', { class: 'event-tape', id: 'tape' })),
    panel('Findings as they surface', null, [
      el('div', { class: 'section-sub mono', id: 'pb-revealed', text: `0 / ${findings.length} surfaced` }),
      railCards(),
    ]),
  ]);
  host.appendChild(layout);

  update();
}

export function unmount() {
  stopTimer();
  playing = false;
  if (strip) {
    strip.destroy();
    strip = null;
  }
  events = [];
  findings = [];
  root = null;
}
