// Hand-rolled canvas charts. No charting library, so the demo works fully offline
// and there is no build step. Each factory returns { destroy() } for page teardown.

import { PALETTE, alpha } from '../core/palette.js';
import { el } from '../core/ui.js';

/** Size a canvas for the device pixel ratio and return its 2D context.
 *  Both the CSS size and the backing store are set explicitly: relying on a
 *  `width:100%` rule while sizing the backing store from the parent lets the two
 *  disagree, which renders every glyph horizontally squashed. */
function setup(canvas, cssHeight) {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(200, Math.floor(canvas.parentElement.clientWidth || 600));
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: cssWidth, h: cssHeight };
}

function mkBox(host, height) {
  const box = el('div', { class: 'chart-box' });
  const canvas = el('canvas');
  const tip = el('div', { class: 'chart-tooltip' });
  box.appendChild(canvas);
  box.appendChild(tip);
  host.appendChild(box);
  return { box, canvas, tip, height };
}

/**
 * Re-render whenever the container's width actually changes.
 *
 * Charts are built as their panels are appended to a CSS grid, so the first
 * measurement can be taken while the grid is still one column wide. Without this
 * the canvas keeps that stale width and overflows once the grid reflows.
 */
function observeWidth(box, render) {
  let last = 0;
  const ro = new ResizeObserver(() => {
    const w = Math.floor(box.clientWidth);
    if (w && w !== last) {
      last = w;
      render();
    }
  });
  ro.observe(box);
  return () => ro.disconnect();
}

function showTip(tip, box, x, y, text) {
  tip.textContent = text;
  tip.classList.add('visible');
  const bw = box.clientWidth;
  const tw = tip.offsetWidth || 120;
  tip.style.left = `${Math.max(4, Math.min(bw - tw - 4, x - tw / 2))}px`;
  tip.style.top = `${Math.max(0, y - 34)}px`;
}

const hideTip = (tip) => tip.classList.remove('visible');

/**
 * Horizontal bar chart. data: [{ label, value, color? }]
 */
export function horizontalBars(host, data, { height, maxLabel = 190 } = {}) {
  const rows = data.slice();
  const h = height || Math.max(80, rows.length * 26 + 16);
  const { box, canvas, tip } = mkBox(host, h);
  let hot = -1;

  function render() {
    const { ctx, w } = setup(canvas, h);
    ctx.clearRect(0, 0, w, h);
    if (!rows.length) return;
    const max = Math.max(...rows.map((r) => r.value), 1);
    const barH = 14;
    const gap = (h - 16) / rows.length;
    // Reserve room for the widest value on the right so numbers are never clipped.
    ctx.font = '500 11px JetBrains Mono, monospace';
    const valueW = Math.ceil(Math.max(...rows.map((r) => ctx.measureText(String(r.value)).width))) + 14;
    const labelW = Math.min(maxLabel, Math.max(70, Math.round(w * 0.40)));
    const trackX = labelW + 10;
    const trackW = Math.max(20, w - trackX - valueW);

    rows.forEach((r, i) => {
      const y = 8 + i * gap + (gap - barH) / 2;
      ctx.font = '500 11px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = i === hot ? PALETTE.textPrimary : PALETTE.textSecondary;
      let label = r.label;
      if (ctx.measureText(label).width > labelW - 6) {
        while (label.length > 3 && ctx.measureText(`${label}…`).width > labelW - 6) {
          label = label.slice(0, -1);
        }
        label += '…';
      }
      ctx.fillText(label, labelW, y + barH / 2);

      const color = r.color || PALETTE.blue;
      ctx.fillStyle = alpha(PALETTE.borderSubtle, 0.6);
      ctx.fillRect(trackX, y, trackW, barH);
      const bw = Math.max(2, (r.value / max) * trackW);
      ctx.fillStyle = i === hot ? color : alpha(color, 0.78);
      ctx.fillRect(trackX, y, bw, barH);

      ctx.font = '500 11px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = i === hot ? PALETTE.textPrimary : PALETTE.textSecondary;
      ctx.fillText(String(r.value), trackX + trackW + 8, y + barH / 2);
    });
  }

  function onMove(e) {
    const rect = canvas.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const gap = (h - 16) / Math.max(1, rows.length);
    const idx = Math.floor((y - 8) / gap);
    const next = idx >= 0 && idx < rows.length ? idx : -1;
    if (next !== hot) {
      hot = next;
      render();
    }
    if (hot >= 0) {
      showTip(tip, box, e.clientX - rect.left, y, `${rows[hot].label}: ${rows[hot].value}`);
    } else hideTip(tip);
  }
  function onLeave() {
    hot = -1;
    hideTip(tip);
    render();
  }

  canvas.addEventListener('mousemove', onMove);
  canvas.addEventListener('mouseleave', onLeave);
  const stopObserving = observeWidth(box, render);
  render();

  return {
    destroy() {
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mouseleave', onLeave);
      stopObserving();
    },
  };
}

/**
 * Cumulative line chart with an optional horizontal rule (e.g. a budget cap).
 * points: [{ x: Date|number, y: number, label? }]
 */
export function lineChart(host, points, { height = 220, rule = null, ruleLabel = '', color, yFormat = (v) => String(v) } = {}) {
  const { box, canvas, tip } = mkBox(host, height);
  const stroke = color || PALETTE.mint;
  let hot = -1;

  function render() {
    const { ctx, w, h } = setup(canvas, height);
    ctx.clearRect(0, 0, w, h);
    const padL = 58, padR = 14, padT = 12, padB = 26;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    if (!points.length || plotW <= 0) {
      ctx.font = '500 11px Inter, sans-serif';
      ctx.fillStyle = PALETTE.textTertiary;
      ctx.textAlign = 'center';
      ctx.fillText('No data yet', w / 2, h / 2);
      return;
    }

    // Scale to the data, not to the rule. A budget cap orders of magnitude above
    // actual spend would otherwise flatten the whole series onto the axis; when the
    // rule is off-scale the caller reports it in the caption instead.
    const dataMax = Math.max(...points.map((p) => p.y), 1e-9);
    const ruleFits = rule != null && rule <= dataMax * 1.35;
    const yMax = (ruleFits ? Math.max(rule, dataMax) : dataMax) * 1.12;
    const xs = points.map((p) => +p.x);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const xSpan = xMax - xMin || 1;
    const px = (x) => padL + ((+x - xMin) / xSpan) * plotW;
    const py = (y) => padT + plotH - (y / yMax) * plotH;

    // gridlines + y labels
    ctx.strokeStyle = alpha(PALETTE.borderSubtle, 0.9);
    ctx.lineWidth = 1;
    ctx.font = '500 10px JetBrains Mono, monospace';
    ctx.fillStyle = PALETTE.textTertiary;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= 4; i++) {
      const v = (yMax / 4) * i;
      const y = py(v);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      ctx.fillText(yFormat(v), padL - 8, y);
    }

    // budget cap rule, drawn only when it is on-scale
    if (ruleFits) {
      ctx.save();
      ctx.strokeStyle = PALETTE.rose;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(padL, py(rule));
      ctx.lineTo(w - padR, py(rule));
      ctx.stroke();
      ctx.restore();
      if (ruleLabel) {
        ctx.font = '500 10px Inter, sans-serif';
        ctx.fillStyle = PALETTE.rose;
        ctx.textAlign = 'left';
        ctx.fillText(ruleLabel, padL + 6, py(rule) - 8);
      }
    }

    // area + line
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(px(p.x), py(p.y)) : ctx.moveTo(px(p.x), py(p.y))));
    ctx.lineTo(px(points[points.length - 1].x), py(0));
    ctx.lineTo(px(points[0].x), py(0));
    ctx.closePath();
    ctx.fillStyle = alpha(stroke, 0.12);
    ctx.fill();

    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(px(p.x), py(p.y)) : ctx.moveTo(px(p.x), py(p.y))));
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.6;
    ctx.stroke();

    if (hot >= 0 && hot < points.length) {
      const p = points[hot];
      ctx.beginPath();
      ctx.arc(px(p.x), py(p.y), 3.5, 0, Math.PI * 2);
      ctx.fillStyle = stroke;
      ctx.fill();
      ctx.strokeStyle = PALETTE.bgCanvas;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  function onMove(e) {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const padL = 58, padR = 14;
    const plotW = rect.width - padL - padR;
    if (!points.length || plotW <= 0) return;
    const t = Math.max(0, Math.min(1, (x - padL) / plotW));
    const idx = Math.round(t * (points.length - 1));
    if (idx !== hot) {
      hot = idx;
      render();
    }
    const p = points[idx];
    showTip(tip, box, x, e.clientY - rect.top, `${p.label || ''} ${yFormat(p.y)}`.trim());
  }
  function onLeave() {
    hot = -1;
    hideTip(tip);
    render();
  }

  canvas.addEventListener('mousemove', onMove);
  canvas.addEventListener('mouseleave', onLeave);
  const stopObserving = observeWidth(box, render);
  render();

  return {
    destroy() {
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mouseleave', onLeave);
      stopObserving();
    },
  };
}

/**
 * Event density strip with a moving cursor, used by the playback page.
 * buckets: [{ total, highlight }]  — highlight is drawn in violet on top.
 */
export function heatStrip(host, { height = 64 } = {}) {
  const { box, canvas, tip } = mkBox(host, height);
  let buckets = [];
  let cursor = 0; // 0..1
  let onSeek = null;
  let hot = -1;

  function render() {
    const { ctx, w, h } = setup(canvas, height);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = alpha(PALETTE.borderSubtle, 0.35);
    ctx.fillRect(0, 0, w, h);
    if (!buckets.length) return;

    const max = Math.max(...buckets.map((b) => b.total), 1);
    const bw = w / buckets.length;
    buckets.forEach((b, i) => {
      const x = i * bw;
      const bh = (b.total / max) * (h - 10);
      ctx.fillStyle = i === hot ? PALETTE.blue : alpha(PALETTE.blue, 0.5);
      ctx.fillRect(x, h - bh, Math.max(1, bw - 0.5), bh);
      if (b.highlight) {
        const hh = (b.highlight / max) * (h - 10);
        ctx.fillStyle = PALETTE.violet;
        ctx.fillRect(x, h - hh, Math.max(1, bw - 0.5), hh);
      }
    });

    // played region + cursor
    ctx.fillStyle = alpha(PALETTE.bgCanvas, 0.55);
    ctx.fillRect(cursor * w, 0, w - cursor * w, h);
    ctx.strokeStyle = PALETTE.textPrimary;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(cursor * w) + 0.5, 0);
    ctx.lineTo(Math.round(cursor * w) + 0.5, h);
    ctx.stroke();
  }

  function onMove(e) {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const idx = Math.floor((x / rect.width) * buckets.length);
    hot = idx >= 0 && idx < buckets.length ? idx : -1;
    render();
    if (hot >= 0) {
      const b = buckets[hot];
      showTip(
        tip, box, x, e.clientY - rect.top,
        `${b.total} events${b.highlight ? ` · ${b.highlight} wiki` : ''}`
      );
    } else hideTip(tip);
  }
  function onLeave() {
    hot = -1;
    hideTip(tip);
    render();
  }
  function onClick(e) {
    if (!onSeek) return;
    const rect = canvas.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)));
  }

  canvas.addEventListener('mousemove', onMove);
  canvas.addEventListener('mouseleave', onLeave);
  canvas.addEventListener('click', onClick);
  canvas.style.cursor = 'pointer';
  const stopObserving = observeWidth(box, render);

  return {
    setData(next) { buckets = next || []; render(); },
    setCursor(frac) { cursor = frac; render(); },
    onSeek(fn) { onSeek = fn; },
    destroy() {
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mouseleave', onLeave);
      canvas.removeEventListener('click', onClick);
      stopObserving();
    },
  };
}
