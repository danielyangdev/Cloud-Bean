// Small DOM helpers shared by pages. Keeps page modules declarative.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') {
      node.addEventListener(k.slice(2).toLowerCase(), v);
    } else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

export function toast(message, kind = '') {
  let host = document.getElementById('toast-host');
  if (!host) {
    host = el('div', { id: 'toast-host' });
    document.body.appendChild(host);
  }
  const node = el('div', { class: `toast ${kind}`.trim(), text: message });
  host.appendChild(node);
  setTimeout(() => {
    node.style.opacity = '0';
    setTimeout(() => node.remove(), 200);
  }, kind === 'err' ? 6000 : 3800);
  return node;
}

export function kpi(label, value, { sub, accent } = {}) {
  return el('div', { class: `kpi${accent ? ' accent-' + accent : ''}` }, [
    el('div', { class: 'kpi-label', text: label }),
    el('div', { class: 'kpi-val', text: String(value) }),
    sub ? el('div', { class: 'kpi-sub', text: sub }) : null,
  ]);
}

export function panel(title, sub, children) {
  return el('div', { class: 'panel' }, [
    title ? el('div', { class: 'section-title', text: title }) : null,
    sub ? el('div', { class: 'section-sub', text: sub }) : null,
    ...[].concat(children || []),
  ]);
}

export function button(label, onClick, { primary = false, id } = {}) {
  return el('button', {
    class: `btn btn-action${primary ? ' btn-primary-action' : ''}`,
    id,
    onclick: onClick,
  }, label);
}

/** Disable a button while an async action runs, restoring its label after. */
export async function withBusy(btn, label, fn) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

export function emptyState(title, detail) {
  return el('div', { class: 'empty-state' }, [
    el('strong', { text: title }),
    detail ? document.createTextNode(detail) : null,
  ]);
}
