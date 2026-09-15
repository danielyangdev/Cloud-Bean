// Dynamic Mathematical Topology Mesh Canvas.
// Generates an ambient, non-distracting graph constellation based on proximity network theory
// (Delaunay/Erdős–Rényi spatial interaction topology) matching Raindrop.ai's clean aesthetic.

let canvas = null;
let ctx = null;
let width = 0;
let height = 0;
let nodes = [];
let rafId = null;

const CONNECTION_DIST = 130;
const NODE_COUNT_FACTOR = 32;

function resize() {
  if (!canvas) return;
  width = window.innerWidth;
  height = window.innerHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.position = 'fixed';
  canvas.style.top = '0';
  canvas.style.left = '0';
  canvas.style.pointerEvents = 'none';
  canvas.style.zIndex = '0';
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  if (ctx) {
    ctx.resetTransform();
    ctx.scale(dpr, dpr);
  }
}

function initNodes() {
  nodes = [];
  const targetCount = Math.min(45, Math.max(22, Math.floor(width / NODE_COUNT_FACTOR)));
  for (let i = 0; i < targetCount; i++) {
    nodes.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.30,
      vy: (Math.random() - 0.5) * 0.30,
      r: 1.4 + Math.random() * 1.6,
      phase: Math.random() * Math.PI * 2,
      phaseSpeed: 0.01 + Math.random() * 0.015,
      color: Math.random() < 0.45 ? 'blue' : (Math.random() < 0.75 ? 'violet' : 'mint'),
    });
  }
}

function loop() {
  if (document.hidden) {
    rafId = requestAnimationFrame(loop);
    return;
  }

  ctx.clearRect(0, 0, width, height);

  // 1. Update node positions with gentle Brownian drift & boundary wrap
  for (const n of nodes) {
    n.x += n.vx;
    n.y += n.vy;
    n.phase += n.phaseSpeed;

    if (n.x < -20) n.x = width + 15;
    if (n.x > width + 20) n.x = -15;
    if (n.y < -20) n.y = height + 15;
    if (n.y > height + 20) n.y = -15;
  }

  // 2. Draw proximity filaments (Erdős–Rényi spatial interaction topology)
  for (let i = 0; i < nodes.length; i++) {
    const n1 = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const n2 = nodes[j];
      const dx = n2.x - n1.x;
      const dy = n2.y - n1.y;
      const distSq = dx * dx + dy * dy;

      if (distSq < CONNECTION_DIST * CONNECTION_DIST) {
        const dist = Math.sqrt(distSq);
        const factor = 1 - dist / CONNECTION_DIST;
        const lineAlpha = factor * 0.08; // delicate subtle filament against dark gray

        ctx.beginPath();
        ctx.moveTo(n1.x, n1.y);
        ctx.lineTo(n2.x, n2.y);
        ctx.strokeStyle = `rgba(125, 211, 252, ${lineAlpha})`;
        ctx.lineWidth = 1.0;
        ctx.stroke();
      }
    }
  }

  // 3. Draw nodes with delicate pulsing aura
  for (const n of nodes) {
    const pulse = 0.8 + 0.2 * Math.sin(n.phase);
    const nodeAlpha = 0.25 + 0.15 * pulse;

    // Subtle outer halo
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r * 2.2, 0, Math.PI * 2);
    if (n.color === 'blue') {
      ctx.fillStyle = `rgba(56, 189, 248, ${nodeAlpha * 0.20})`;
    } else if (n.color === 'violet') {
      ctx.fillStyle = `rgba(168, 85, 247, ${nodeAlpha * 0.18})`;
    } else {
      ctx.fillStyle = `rgba(52, 211, 153, 0.18)`;
    }
    ctx.fill();

    // Node nucleus
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(241, 243, 247, ${nodeAlpha * 1.2})`;
    ctx.fill();
  }

  rafId = requestAnimationFrame(loop);
}

export function initBackgroundMesh() {
  canvas = document.getElementById('ambient-bg-canvas');
  if (!canvas) return;
  ctx = canvas.getContext('2d');
  resize();
  initNodes();
  window.addEventListener('resize', () => {
    resize();
    initNodes();
  });
  if (rafId) cancelAnimationFrame(rafId);
  loop();
}
