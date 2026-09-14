// Global header pills. Single implementation so every route shows the same numbers.

import { api } from './api.js';
import { fmtUSD } from './format.js';

export async function refreshHeader() {
  try {
    const [budget, summary] = await Promise.all([api.budget(), api.metricsSummary()]);
    const spend = document.getElementById('metric-spend');
    if (spend) {
      spend.innerText = `${fmtUSD(budget.spent_usd)} / ${fmtUSD(budget.max_budget_usd, 2)}`;
    }
    const groups = document.getElementById('metric-hubs');
    if (groups) groups.innerText = summary.candidates ?? 0;
    const alerts = document.getElementById('metric-alerts');
    if (alerts) alerts.innerText = summary.findings ?? 0;
  } catch (_) {
    // Header is decorative; never block or fail a page on it.
  }
}
