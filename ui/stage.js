import { clamp, drawOnResize, easeInOut, el, prefersReducedMotion, svg, tween, wait } from './dom.js';
import { CORE, HAIR, INK_1, INK_2, LINK, PLATE, SEAM_DARK, TRAP_A, TRAP_B } from './palette.js';

/** Gate name to its letter and an optional small mark set below (axis) or above (dagger). */
const GATE_LETTERS = {
  h: ['H'], x: ['X'], y: ['Y'], z: ['Z'], s: ['S'], t: ['T'], p: ['P'], u: ['U'], id: ['I'],
  sdg: ['S', '†', -5], tdg: ['T', '†', -5],
  sx: ['V'], sxdg: ['V', '†', -5],
  rx: ['R', 'x', 3], ry: ['R', 'y', 3], rz: ['R', 'z', 3],
};
const GUTTER = 64;
const MARGIN = 14;
const PAIR_LABEL_ROOM = 56;
const MAX_FLIGHT_MS = 600;
const RUN_BUDGET_MS = 3600;

function glow(id, colour) {
  return svg('radialGradient', { id },
    svg('stop', { offset: 0, 'stop-color': colour, 'stop-opacity': 1 }),
    svg('stop', { offset: 0.26, 'stop-color': colour, 'stop-opacity': 0.42 }),
    svg('stop', { offset: 1, 'stop-color': colour, 'stop-opacity': 0 }));
}

function definitions() {
  return svg('defs', {},
    glow('seam-glow-a', TRAP_A),
    glow('seam-glow-b', TRAP_B),
    glow('seam-glow-link', LINK),
    svg('linearGradient', { id: 'seam-streak', gradientUnits: 'userSpaceOnUse', x1: -46, y1: 0, x2: 0, y2: 0 },
      svg('stop', { offset: 0, 'stop-color': LINK, 'stop-opacity': 0 }),
      svg('stop', { offset: 1, 'stop-color': LINK, 'stop-opacity': 1 })));
}

function diamond(x, y, half, attrs) {
  return svg('path', { d: `M${x} ${y - half}l${half} ${half}-${half} ${half}-${half}-${half}z`, ...attrs });
}

function measure(scene, width, height) {
  const rows = scene.wires.length;
  const upper = scene.wires.filter((wire) => wire.module === 0).length;
  const titleRoom = 38;
  const seamHeight = clamp(height * 0.14, 44, 56);
  const rowPitch = clamp((height - 2 * titleRoom - seamHeight) / rows, 15, rows > 4 ? 60 : 68);
  const blockHeight = rows * rowPitch + seamHeight;
  const top = (height - blockHeight) / 2;
  const seamTop = top + upper * rowPitch;

  const fixed = GUTTER + 30;
  const colPitch = clamp((width - 2 * MARGIN - fixed) / scene.columns, 4, 68);
  const left = Math.max(MARGIN, (width - fixed - scene.columns * colPitch) / 2);
  const ionX = left + GUTTER;
  const wireStart = ionX + 14;
  const box = clamp(Math.min(colPitch - 2.5, rowPitch - 10), 4, 24);

  return {
    width,
    rowPitch,
    colPitch,
    box,
    top,
    bottom: top + blockHeight,
    seamTop,
    seamHeight,
    seamY: seamTop + seamHeight / 2,
    left,
    ionX,
    wireStart,
    wireEnd: wireStart + 8 + scene.columns * colPitch,
    rowY: (row) => (row < upper
      ? top + (row + 0.5) * rowPitch
      : seamTop + seamHeight + (row - upper + 0.5) * rowPitch),
    columnX: (column) => wireStart + 8 + (column + 0.5) * colPitch,
  };
}

function drawSeam(g) {
  const edge = (y) => svg('line', { x1: 0, x2: g.width, y1: y, y2: y, stroke: HAIR });
  return svg('g', {},
    svg('rect', { x: 0, y: g.seamTop, width: g.width, height: g.seamHeight, fill: SEAM_DARK }),
    edge(g.seamTop),
    edge(g.seamTop + g.seamHeight),
    svg('line', {
      x1: g.ionX + 13, x2: g.width, y1: g.seamY, y2: g.seamY,
      stroke: LINK, 'stroke-width': 1, 'stroke-dasharray': '2 5', opacity: 0.6,
    }),
    svg('rect', { x: g.ionX - 12, y: g.seamY - 8, width: 24, height: 16, fill: SEAM_DARK, stroke: INK_2 }),
    diamond(g.ionX, g.seamY, 4.5, { fill: 'none', stroke: LINK }),
    svg('text', { class: 'stage-note', x: g.ionX - 19, y: g.seamY + 4.5, 'text-anchor': 'end', text: 'memory' }),
    svg('text', { class: 'stage-note', x: g.width - 14, y: g.seamY - 7, 'text-anchor': 'end', text: 'the seam' }));
}

function drawTitles(g) {
  const x = g.left;
  const upperY = g.top - 14;
  const lowerY = g.bottom + 26;
  return svg('g', {},
    svg('circle', { cx: x + 6, cy: upperY - 6, r: 5.5, fill: 'none', stroke: INK_1 }),
    svg('text', { class: 'stage-trap', x: x + 19, y: upperY, text: 'Trap A' }),
    svg('rect', { x: x + 0.5, y: lowerY - 11.5, width: 11, height: 11, fill: 'none', stroke: INK_1 }),
    svg('text', { class: 'stage-trap', x: x + 19, y: lowerY, text: 'Trap B' }));
}

function drawWire(wire, y, g) {
  const line = (dy, width) => svg('line', {
    x1: g.wireStart, x2: g.wireEnd, y1: y + dy, y2: y + dy, stroke: INK_2, 'stroke-width': width,
  });
  return wire.module === 0 ? [line(0, 1)] : [line(-1.7, 0.8), line(1.7, 0.8)];
}

function drawIon(wire, y, g) {
  const x = g.ionX;
  const r = clamp(g.rowPitch * 0.2, 5, 10);
  const kind = wire.kind === 'link' ? 'link' : wire.module === 0 ? 'a' : 'b';
  const outline = { fill: 'none', stroke: INK_1, 'stroke-width': 0.9, opacity: 0.7 };
  const mark = {
    a: () => svg('circle', { cx: x, cy: y, r, ...outline }),
    b: () => svg('rect', { x: x - r, y: y - r, width: 2 * r, height: 2 * r, ...outline }),
    link: () => diamond(x, y, r + 1, outline),
  }[kind]();
  return svg('g', {},
    svg('circle', { cx: x, cy: y, r: r * 3.4, fill: `url(#seam-glow-${kind})` }),
    mark,
    svg('circle', { cx: x, cy: y, r: r * 0.36, fill: CORE }));
}

function drawBox(x, y, name, g) {
  const half = g.box / 2;
  const parts = [svg('rect', { x: x - half, y: y - half, width: g.box, height: g.box, fill: PLATE, stroke: INK_2 })];
  if (g.box >= 15.5) {
    const [letter, small, shift] = GATE_LETTERS[name] ?? [name.charAt(0).toUpperCase()];
    parts.push(svg('text', { class: 'stage-gate-letter', x, y: y + 4.8 }, letter,
      small ? svg('tspan', { class: 'stage-gate-mark', dy: shift, text: small }) : null));
  }
  return parts;
}

function drawMeter(x, y, g) {
  const half = g.box / 2;
  const parts = [svg('rect', { x: x - half, y: y - half, width: g.box, height: g.box, fill: PLATE, stroke: INK_2 })];
  if (g.box >= 14) {
    const k = g.box / 21;
    parts.push(svg('path', {
      d: `M${x - 6.5 * k} ${y + 5 * k}a${6.5 * k} ${6.5 * k} 0 0 1 ${13 * k} 0M${x} ${y + 5 * k}l${4.5 * k} ${-10 * k}`,
      fill: 'none', stroke: INK_1,
    }));
  }
  return parts;
}

function drawControl(x, y, g) {
  return svg('circle', { cx: x, cy: y, r: clamp(g.box * 0.16, 1.6, 3.4), fill: INK_1 });
}

function drawTarget(x, y, g) {
  const r = clamp(g.box * 0.33, 2.6, 7);
  return svg('g', {},
    svg('circle', { cx: x, cy: y, r, fill: PLATE, stroke: INK_1, 'stroke-width': 1.1 }),
    svg('path', { d: `M${x - r} ${y}h${2 * r}M${x} ${y - r}v${2 * r}`, fill: 'none', stroke: INK_1, 'stroke-width': 1.1 }));
}

function drawOp(op, g) {
  const x = g.columnX(op.column);
  const ys = op.rows.map(g.rowY);
  const node = svg('g', { class: 'stage-op' });
  if (op.glyph === 'box') node.append(...drawBox(x, ys[0], op.name, g));
  else if (op.glyph === 'measure') node.append(...drawMeter(x, ys[0], g));
  else {
    const lit = op.cross && !op.classical;
    node.append(svg('line', {
      x1: x, x2: x, y1: ys[0], y2: ys[1],
      stroke: lit ? LINK : INK_1,
      'stroke-width': lit ? 1.3 : 1,
      'stroke-dasharray': op.classical ? '2 3' : null,
    }));
    if (op.glyph === 'pair') {
      node.append(...ys.map((y) => diamond(x, y, 3.6, { fill: LINK })));
    } else {
      node.append(drawControl(x, ys[0], g), op.name === 'cz' ? drawControl(x, ys[1], g) : drawTarget(x, ys[1], g));
    }
    if (op.note) node.append(svg('text', { class: 'stage-note', x: x + 7, y: g.seamY + 16, text: op.note }));
  }
  return { op, node, x, ys };
}

function assignLanes(spans, gap) {
  const ends = [];
  return spans.map(({ from, to }) => {
    let lane = ends.findIndex((end) => end + gap < from);
    if (lane < 0) lane = ends.length;
    ends[lane] = to;
    return lane;
  });
}

function laneOffsets(lanes, seamHeight) {
  const count = Math.max(1, ...lanes.map((lane) => lane + 1));
  if (count === 1) return [0];
  const step = Math.min(7, (seamHeight / 2 - 15) / Math.ceil(count / 2));
  return Array.from({ length: count }, (_, lane) => (lane % 2 === 0 ? -1 : 1) * step * (1 + Math.floor(lane / 2)));
}

/** One amber segment per pair, spanning the crossing gates it serves; neighbours sit on separate lanes. */
function drawPairs(scene, drawnOps, g) {
  const spans = scene.pairs
    .map((pair) => {
      const gates = pair.ops.map((index) => drawnOps[index]).sort((a, b) => a.x - b.x);
      return { pair, gates, from: gates[0].x, to: gates[gates.length - 1].x };
    })
    .sort((a, b) => a.from - b.from);
  const lanes = assignLanes(spans, PAIR_LABEL_ROOM);
  const offsets = laneOffsets(lanes, g.seamHeight);
  const half = clamp(g.colPitch * 0.3, 4, 6.5);

  return spans.map((span, order) => {
    const offset = offsets[lanes[order]];
    const y = g.seamY + offset;
    const strength = span.pair.strength ?? 1;
    const node = svg('g', {});
    const bar = svg('line', {
      x1: span.from, x2: span.to, y1: y, y2: y, stroke: LINK, 'stroke-width': 2, opacity: strength,
    });
    if (span.to > span.from) {
      node.append(bar, ...span.gates.slice(1).map((gate) => svg('circle', { cx: gate.x, cy: y, r: 2.4, fill: LINK })));
    }
    if (span.pair.raw === 2) {
      const rawX = span.from - Math.max(24, half * 3.6);
      for (const dy of [-8, 8]) {
        node.append(
          svg('line', { x1: rawX, x2: span.from, y1: y + dy, y2: y, stroke: LINK, 'stroke-width': 1, opacity: 0.7 }),
          diamond(rawX, y + dy, 3.6, { fill: SEAM_DARK, stroke: LINK }));
      }
    }
    const mark = diamond(span.from, y, half, { fill: LINK, 'fill-opacity': strength, stroke: LINK, 'stroke-width': 1.2 });
    const text = span.pair.label ?? (scene.pairs.length === 1 ? 'one pair' : `pair ${order + 1}`);
    node.append(mark, svg('text', {
      class: 'stage-note stage-pair-label', x: span.from + half + 5, y: offset > 0 ? y + 15 : y - 7, text,
    }));
    return { ...span, node, mark, bar, y, strength };
  });
}

export function createStage(host) {
  const figure = svg('svg', { role: 'img', focusable: 'false' });
  const buttons = el('div', { class: 'qubit-buttons' });
  host.append(figure, buttons);

  let scene = null;
  let options = {};
  let drawing = null;
  let playId = 0;
  const sizer = drawOnResize(host, render);

  function render(width, height) {
    if (!scene) return;
    playId += 1;
    const g = measure(scene, width, height);
    const ops = scene.ops.map((op) => drawOp(op, g));
    const pairs = drawPairs(scene, ops, g);
    const effects = svg('g', {});

    figure.setAttribute('viewBox', `0 0 ${width} ${height}`);
    figure.setAttribute('aria-label', scene.summary);
    figure.replaceChildren(
      definitions(),
      drawSeam(g),
      drawTitles(g),
      ...scene.wires.flatMap((wire, row) => drawWire(wire, g.rowY(row), g)),
      ...scene.wires.map((wire, row) => drawIon(wire, g.rowY(row), g)),
      ...ops.map((drawn) => drawn.node),
      ...pairs.map((placed) => placed.node),
      ...drawWireLabels(g),
      effects,
    );
    drawing = { g, ops, pairs, effects };
    applyEmphasis();
    placeButtons(g);
  }

  function drawWireLabels(g) {
    if (options.onMove) return [];
    return scene.wires.map((wire, row) => svg('text', {
      class: 'stage-wire-label', x: g.ionX - 17, y: g.rowY(row) + 5, 'text-anchor': 'end', text: wire.label,
    }));
  }

  function placeButtons(g) {
    const focused = buttons.contains(document.activeElement) ? document.activeElement.dataset.qubit : null;
    const nodes = [];
    if (options.onMove) {
      scene.wires.forEach((wire, row) => {
        const here = wire.module === 0 ? 'A' : 'B';
        const there = wire.module === 0 ? 'B' : 'A';
        const allowed = options.canMove ? options.canMove(wire.qubit) : true;
        const move = () => allowed && options.onMove(wire.qubit);
        nodes.push(el('button', {
          type: 'button',
          class: 'qubit-button',
          'data-qubit': wire.qubit,
          style: `left:${g.ionX - 12}px;top:${g.rowY(row)}px`,
          'aria-label': allowed
            ? `${wire.label}, in Trap ${here}. Move it to Trap ${there}.`
            : `${wire.label}, in Trap ${here}. It cannot move: each trap keeps at least one qubit.`,
          'aria-disabled': allowed ? null : 'true',
          onclick: move,
          onkeydown: (event) => {
            const towardOther = wire.module === 0 ? 'ArrowDown' : 'ArrowUp';
            if (event.key !== towardOther) return;
            event.preventDefault();
            move();
          },
        },
        el('span', { class: 'arrow', 'aria-hidden': 'true', text: wire.module === 0 ? '↓' : '↑' }),
        wire.label));
      });
    }
    buttons.replaceChildren(...nodes);
    if (focused != null) buttons.querySelector(`[data-qubit="${focused}"]`)?.focus();
  }

  function applyEmphasis() {
    if (!drawing) return;
    for (const { op, node } of drawing.ops) {
      node.classList.toggle('stage-dim', Boolean(options.emphasis) && !options.emphasis(op));
    }
  }

  function setWaiting(placed, waiting) {
    placed.mark.setAttribute('fill-opacity', waiting ? 0 : placed.strength);
    placed.bar.setAttribute('opacity', waiting ? 0.25 : placed.strength);
    for (const gate of placed.gates) gate.node.firstChild.setAttribute('opacity', waiting ? 0.3 : 1);
  }

  function fly({ g, effects }, placed, ms) {
    const photon = svg('g', {},
      svg('line', { x1: -46, x2: 0, y1: 0, y2: 0, stroke: 'url(#seam-streak)', 'stroke-width': 3.5, 'stroke-linecap': 'round' }),
      svg('circle', { r: 19, fill: 'url(#seam-glow-link)' }),
      svg('circle', { r: 3, fill: CORE }));
    effects.append(photon);
    return tween(ms, (t) => {
      const e = easeInOut(t);
      const x = g.ionX + (placed.from - g.ionX) * e;
      const y = g.seamY + (placed.y - g.seamY) * e;
      photon.setAttribute('transform', `translate(${x} ${y})`);
    }).then(() => photon.remove());
  }

  function fade(node, ms, peak) {
    drawing.effects.append(node);
    tween(ms, (t) => node.setAttribute('opacity', peak * (1 - t) ** 2)).then(() => node.remove());
  }

  function ignite(placed) {
    fade(svg('circle', { cx: placed.from, cy: placed.y, r: 26, fill: 'url(#seam-glow-link)' }), 700, 1);
  }

  function flash(gate) {
    const [y1, y2] = gate.ys;
    fade(svg('line', {
      x1: gate.x, x2: gate.x, y1, y2, stroke: LINK, 'stroke-width': 6, 'stroke-linecap': 'round',
    }), 520, 0.4);
  }

  /** Delivers the pairs along the fibre one at a time; each crossing gate lights as its pair is spent. */
  async function play() {
    if (!drawing || drawing.pairs.length === 0 || prefersReducedMotion()) return;
    const id = ++playId;
    const current = drawing;
    const flight = clamp(RUN_BUDGET_MS / current.pairs.length, 240, MAX_FLIGHT_MS);
    for (const placed of current.pairs) setWaiting(placed, true);
    for (const placed of current.pairs) {
      await fly(current, placed, flight);
      if (id !== playId) return;
      setWaiting(placed, false);
      ignite(placed);
      for (const gate of placed.gates) {
        flash(gate);
        await wait(Math.min(130, flight / 3));
        if (id !== playId) return;
      }
    }
    await wait(180);
  }

  return {
    show(nextScene, nextOptions = {}) {
      scene = nextScene;
      options = nextOptions;
      sizer.redraw();
    },
    emphasise(predicate) {
      options = { ...options, emphasis: predicate };
      applyEmphasis();
    },
    play,
  };
}
