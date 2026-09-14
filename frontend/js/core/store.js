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

// Cache generation. Navigation reuses whatever is cached; only a mutation (fleet
// load, replay, failure injection, reset) bumps this, which drops the cache. That
// keeps the numbers consistent after a mutation without refetching ~2.7MB of events
// and evidence packets every time the user changes page.
let generation = 0;
let cachedAt = -1;

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

/** Drop caches so the next load() refetches. Call after any mutating request. */
export function invalidate() {
  generation += 1;
  for (const key of Object.keys(state)) state[key] = null;
}

/** Drop caches only if a mutation happened since they were filled. */
export function invalidateIfStale() {
  if (cachedAt !== generation) {
    for (const key of Object.keys(state)) state[key] = null;
  }
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
    cachedAt = generation;
    emit();
  }
  return state;
}
