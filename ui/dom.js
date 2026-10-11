const SVG_NS = 'http://www.w3.org/2000/svg';

function fill(node, attrs, children) {
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (name === 'text') node.textContent = value;
    else if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) node.append(child);
  }
  return node;
}

export function el(tag, attrs = {}, ...children) {
  return fill(document.createElement(tag), attrs, children);
}

export function svg(tag, attrs = {}, ...children) {
  return fill(document.createElementNS(SVG_NS, tag), attrs, children);
}

export const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

export function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Resolves once the browser has painted, so a working state is visible before
 * a blocking call. A hidden page paints nothing, so a timer backs the frame up.
 */
export async function afterPaint() {
  await Promise.race([new Promise((resolve) => requestAnimationFrame(resolve)), wait(120)]);
  await wait(0);
}

/**
 * Calls `draw(t)` with t from 0 to 1 over `ms` milliseconds; instant under
 * reduced motion. It still finishes on time when the page is hidden and no
 * frames are delivered.
 */
export function tween(ms, draw) {
  if (prefersReducedMotion() || ms <= 0) {
    draw(1);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      draw(1);
      resolve();
    };
    const frame = (now) => {
      if (done) return;
      const t = clamp((now - started) / ms, 0, 1);
      if (t >= 1) finish();
      else {
        draw(t);
        requestAnimationFrame(frame);
      }
    };
    requestAnimationFrame(frame);
    setTimeout(finish, ms + 200);
  });
}

export const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

/** Redraws whenever the node changes size; `draw` receives the size in CSS pixels. */
export function drawOnResize(node, draw) {
  let width = 0;
  let height = 0;
  const redraw = () => {
    if (width > 0 && height > 0) draw(width, height);
  };
  const observer = new ResizeObserver(([entry]) => {
    const box = entry.contentRect;
    if (Math.round(box.width) === width && Math.round(box.height) === height) return;
    width = Math.round(box.width);
    height = Math.round(box.height);
    redraw();
  });
  observer.observe(node);
  return { redraw };
}
