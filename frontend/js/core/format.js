// Display formatting helpers.

export const fmtUSD = (n, dp = 4) =>
  `$${Number(n || 0).toFixed(dp)}`;

export const fmtInt = (n) =>
  Number(n || 0).toLocaleString('en-US');

export const fmtPct = (n, dp = 1) =>
  `${Number(n || 0).toFixed(dp)}%`;

export const fmtNum = (n, dp = 3) => {
  const v = Number(n);
  if (!isFinite(v)) return '—';
  return v.toFixed(dp);
};

/** "2026-06-18T19:00:00Z" -> "Jun 18, 19:00:00" */
export function fmtTs(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `${month} ${day}, ${hh}:${mm}:${ss}`;
}

/** Compact clock for the playback scrubber: "Jun 18 19:00" */
export function fmtClock(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${month} ${day} ${hh}:${mm} UTC`;
}

export const fmtTsShort = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return String(iso).slice(0, 16);
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `${mo}/${day} ${hh}:${mm}:${ss}`;
};

/** Humanise a snake_case signal or pattern name. */
export const humanise = (s) =>
  String(s || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

export const truncate = (s, n = 40) => {
  const str = String(s == null ? '' : s);
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
};

/** Strip the "agent:" / "resource:" / "wiki:" / "tool:" prefix for display. */
export const stripPrefix = (s) => String(s || '').replace(/^(agent|resource|wiki|tool):/, '');

export function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
