// Single source of truth for colour: read the CSS custom properties once so the
// canvas renderers and the stylesheet can never drift apart.

const VARS = {
  mint: '--pastel-mint',
  amber: '--pastel-amber',
  rose: '--pastel-rose',
  violet: '--pastel-violet',
  blue: '--pastel-blue',
  bgCanvas: '--bg-canvas',
  bgPanel: '--bg-panel',
  bgSurface: '--bg-surface',
  bgSurfaceHover: '--bg-surface-hover',
  borderSubtle: '--border-subtle',
  borderStrong: '--border-strong',
  textPrimary: '--text-primary',
  textSecondary: '--text-secondary',
  textTertiary: '--text-tertiary',
};

export const PALETTE = {};

export function initPalette() {
  const cs = getComputedStyle(document.documentElement);
  for (const [key, cssVar] of Object.entries(VARS)) {
    PALETTE[key] = cs.getPropertyValue(cssVar).trim() || '#888888';
  }
  return PALETTE;
}

/** Convert a #rrggbb token to rgba() at the given alpha. */
export function alpha(hex, a) {
  const h = (hex || '').replace('#', '');
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/** Node/resource status to palette key. */
export const STATUS_COLOR = {
  normal: 'mint',
  candidate: 'amber',
  concerning: 'rose',
  emerging_hub: 'amber',
  conflict_hotspot: 'rose',
  low_traffic: 'blue',
};

export function statusColor(status, fallback = 'mint') {
  return PALETTE[STATUS_COLOR[status] || fallback] || PALETTE.mint;
}

/** Tag class suffix used by .tag.<name> in pages.css. */
export const STATUS_TAG = {
  normal: 'mint',
  candidate: 'amber',
  concerning: 'rose',
  emerging_hub: 'amber',
  conflict_hotspot: 'rose',
  low_traffic: 'blue',
  critical: 'rose',
  high: 'rose',
  medium: 'amber',
  low: 'blue',
};
