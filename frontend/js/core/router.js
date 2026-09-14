// Minimal hash router. Every page module exports { mount(root, params), unmount() }.
// Routes are hash-based so each demo step is deep-linkable and survives a reload.

import { invalidateIfStale } from './store.js';

const routes = new Map();
let current = null;
let currentName = null;
let rootEl = null;

export function register(name, mod) {
  routes.set(name, mod);
}

function parseHash() {
  const raw = (location.hash || '').replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const params = Object.fromEntries(new URLSearchParams(query || ''));
  return { name: path || 'graph', params };
}

function syncNav(name) {
  document.querySelectorAll('nav.main-nav a').forEach((a) => {
    const target = (a.getAttribute('href') || '').replace(/^#\/?/, '').split('?')[0];
    if (target === name) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

async function navigate() {
  const { name, params } = parseHash();
  const mod = routes.get(name);
  if (!mod) {
    location.hash = '#/graph';
    return;
  }

  // Tear the previous page down before clearing the DOM it holds references to,
  // so animation loops and listeners never outlive their page.
  if (current && typeof current.unmount === 'function') {
    try {
      current.unmount();
    } catch (err) {
      console.error('unmount failed', err);
    }
  }

  // Reuse cached slices across navigation, dropping them only when a mutation has
  // happened since they were filled. Refetching unconditionally kept the numbers
  // consistent but re-pulled megabytes of events and evidence on every page change.
  invalidateIfStale();

  current = mod;
  currentName = name;
  rootEl.innerHTML = '';
  document.body.className = `page-${name}`;
  syncNav(name);

  try {
    await mod.mount(rootEl, params);
  } catch (err) {
    console.error(`mount ${name} failed`, err);
    rootEl.innerHTML =
      `<div class="page-wrap"><div class="empty-state">` +
      `<strong>This page failed to load.</strong>${err.message}</div></div>`;
  }
}

/** Update the query portion of the current route without a full remount. */
export function setParam(key, value) {
  const { name, params } = parseHash();
  if (value == null) delete params[key];
  else params[key] = value;
  const q = new URLSearchParams(params).toString();
  const next = `#/${name}${q ? '?' + q : ''}`;
  history.replaceState(null, '', next);
}

export function currentRoute() {
  return currentName;
}

export function start(el) {
  rootEl = el;
  window.addEventListener('hashchange', navigate);
  if (!location.hash) location.hash = '#/overview';
  else navigate();
}
