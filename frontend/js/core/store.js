// Cached fleet snapshot. Pages share one fetch rather than each hitting the API,
// which matters for the playback page: the full event stream is fetched once and
// then scrubbed entirely client-side.

import { api } from './api.js';

const state = {
  graph: null,
  findings: null,
  budget: null,
  summary: null,
  events: null,
  candidates: null,
  judgments: null,
  evidence: null,
};

const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  for (const fn of listeners) {
    try {
      fn(state);
    } catch (err) {
      console.error('store listener failed', err);
    }
  }
}

export function snapshot() {
  return state;
}

/** Drop caches so the next load() refetches. */
export function invalidate() {
  for (const key of Object.keys(state)) state[key] = null;
}

/**
 * Load the named slices, reusing cache unless force is set.
 * load(['summary','findings']) keeps pages from over-fetching.
 */
export async function load(keys, { force = false } = {}) {
  const fetchers = {
    graph: () => api.graph(),
    findings: () => api.findings(),
    budget: () => api.budget(),
    summary: () => api.metricsSummary(),
    candidates: () => api.candidateGroups(),
    judgments: () => api.judgments(),
    evidence: () => api.evidenceList(),
    events: async () => {
      const res = await api.events({ limit: 50000 });
      return res.events || [];
    },
  };

  const wanted = keys.filter((k) => force || state[k] == null);
  if (wanted.length) {
    const results = await Promise.all(wanted.map((k) => fetchers[k]()));
    wanted.forEach((k, i) => {
      state[k] = results[i];
    });
    emit();
  }
  return state;
}
