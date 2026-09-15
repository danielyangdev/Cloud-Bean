// Thin wrapper over the Cloud-Bean REST API. One function per endpoint.

async function req(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

const postJSON = (path, body) => req(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

export const api = {
  health: () => req('/api/v1/health'),
  graph: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return req(`/api/v1/graph${q ? '?' + q : ''}`);
  },
  findings: () => req('/api/v1/findings'),
  candidateGroups: () => req('/api/v1/candidate-groups'),
  budget: () => req('/api/v1/budget'),
  events: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return req(`/api/v1/events${q ? '?' + q : ''}`);
  },
  judgments: () => req('/api/v1/judgments'),
  evidenceList: () => req('/api/v1/evidence'),
  evidencePacket: (id) => req(`/api/v1/evidence/${encodeURIComponent(id)}`),
  metricsSummary: () => req('/api/v1/metrics/summary'),
  loadFleet: ({ agents = 100, eventsPerAgent = 25, retime = true, includeClean = true } = {}) =>
    postJSON(
      `/api/v1/load-benchmark-fleet?limit_agents=${agents}` +
      `&events_per_agent=${eventsPerAgent}&retime=${retime}&include_clean=${includeClean}`
    ),
  ingest: (events, enableAudit = false) =>
    postJSON('/api/v1/ingest/events', { events, enable_audit: enableAudit }),
  replay: () => postJSON('/api/v1/replay', { enable_audit: false }),
  injectFailure: (mode, rate = 0.3, seed = 42) =>
    postJSON('/api/v1/failures/inject', { mode, rate, seed }),
  reset: () => postJSON('/api/v1/reset', {}),
};
