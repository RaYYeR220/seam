import { drawOnResize, el, svg } from './dom.js';
import { EDGE, INK_1, INK_2, INK_3, LINK, PLATE } from './palette.js';

/** Below this size there is no room for axes; the hidden table still carries the data. */
const MIN_WIDTH = 120;
const MIN_HEIGHT = 70;

function dataTable(caption, head, rows) {
  return el('table', {},
    el('caption', { text: caption }),
    el('thead', {}, el('tr', {}, head.map((text) => el('th', { scope: 'col', text })))),
    el('tbody', {}, rows.map((row) => el('tr', {}, row.map((text) => el('td', { text }))))));
}

function chartDefinitions() {
  return svg('defs', {},
    svg('pattern', { id: 'seam-hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(-45)' },
      svg('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: EDGE, 'stroke-width': 1 })),
    svg('radialGradient', { id: 'seam-point-glow' },
      svg('stop', { offset: 0, 'stop-color': LINK, 'stop-opacity': 0.85 }),
      svg('stop', { offset: 0.4, 'stop-color': LINK, 'stop-opacity': 0.25 }),
      svg('stop', { offset: 1, 'stop-color': LINK, 'stop-opacity': 0 })));
}

function mark(shape, x, y, size, attrs) {
  if (shape === 'diamond') {
    const h = size * 1.3;
    return svg('path', { d: `M${x} ${y - h}l${h} ${h}-${h} ${h}-${h}-${h}z`, ...attrs });
  }
  return svg('circle', { cx: x, cy: y, r: size, ...attrs });
}

function interpolate(points, x) {
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    if (x <= x1) return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0 || 1);
  }
  return points.length ? points[points.length - 1][1] : null;
}

function mount(host, describe, draw) {
  const figure = svg('svg', { 'aria-hidden': 'true', focusable: 'false' });
  const tableSlot = el('div', { class: 'sr-only' });
  host.replaceChildren(figure, tableSlot);
  let spec = null;
  const sizer = drawOnResize(host, (width, height) => {
    if (!spec) return;
    if (width < MIN_WIDTH || height < MIN_HEIGHT) {
      figure.replaceChildren();
      return;
    }
    figure.setAttribute('viewBox', `0 0 ${width} ${height}`);
    figure.replaceChildren(chartDefinitions(), ...draw(spec, width, height));
  });
  return {
    update(next) {
      spec = next;
      tableSlot.replaceChildren(dataTable(next.label, ...describe(next)));
      sizer.redraw();
    },
    clear() {
      spec = null;
      figure.replaceChildren();
      tableSlot.replaceChildren();
    },
  };
}

/**
 * Curves against one horizontal axis. Theory is a line, measured values are
 * filled marks with a 95% whisker, exact values are outline marks.
 *
 * spec: { label, x: {min, max, ticks, title, format}, y: {min, max, ticks},
 *         series: [{ name, shape, dash, theory: [[x, y]], points: [{x, y, lo, hi, exact}], labelAt }],
 *         levels: [{ y, text }], loss: { from, text }, marks: [{ x, text }], cursor,
 *         table: { head, rows } }
 */
export function lineChart(host) {
  return mount(host, (spec) => [spec.table.head, spec.table.rows], (spec, width, height) => {
    const compact = height < 190 || width < 280;
    const frame = { left: 36, right: 12, top: 10, bottom: compact ? 22 : 40 };
    const plotWidth = width - frame.left - frame.right;
    const plotHeight = height - frame.top - frame.bottom;
    const floor = frame.top + plotHeight;
    const X = (v) => frame.left + ((v - spec.x.min) / (spec.x.max - spec.x.min)) * plotWidth;
    const Y = (v) => floor - ((v - spec.y.min) / (spec.y.max - spec.y.min)) * plotHeight;
    const inside = (v) => v >= spec.y.min && v <= spec.y.max;
    const parts = [];

    if (spec.loss && spec.loss.from < spec.x.max) {
      const from = X(Math.max(spec.loss.from, spec.x.min));
      parts.push(
        svg('rect', { x: from, y: frame.top, width: frame.left + plotWidth - from, height: plotHeight, fill: 'url(#seam-hatch)' }),
        svg('line', { x1: from, x2: from, y1: frame.top, y2: floor, stroke: EDGE, 'stroke-dasharray': '3 3' }));
    }

    parts.push(svg('path', { d: `M${frame.left} ${frame.top}V${floor}H${frame.left + plotWidth}`, fill: 'none', stroke: EDGE }));
    for (const tick of spec.y.ticks) {
      parts.push(
        svg('line', { x1: frame.left - 4, x2: frame.left, y1: Y(tick), y2: Y(tick), stroke: EDGE }),
        svg('text', { class: 'chart-tick', x: frame.left - 7, y: Y(tick) + 4.5, 'text-anchor': 'end', text: tick.toFixed(1) }));
    }
    spec.x.ticks.forEach((tick, index) => {
      const last = index === spec.x.ticks.length - 1;
      parts.push(
        svg('line', { x1: X(tick), x2: X(tick), y1: floor, y2: floor + 4, stroke: EDGE }),
        svg('text', {
          class: 'chart-tick', x: X(tick), y: floor + 18, 'text-anchor': last ? 'end' : 'middle', text: spec.x.format(tick),
        }));
    });
    if (!compact) {
      parts.push(svg('text', {
        class: 'chart-tick', x: frame.left + plotWidth / 2, y: floor + 36, 'text-anchor': 'middle', 'font-style': 'italic', text: spec.x.title,
      }));
    }

    for (const level of spec.levels ?? []) {
      if (!inside(level.y)) continue;
      parts.push(svg('line', {
        x1: frame.left, x2: frame.left + plotWidth, y1: Y(level.y), y2: Y(level.y), stroke: INK_3, 'stroke-dasharray': level.dash ?? '6 4',
      }));
      if (!compact) {
        parts.push(svg('text', {
          class: 'chart-label',
          x: level.end ? frame.left + plotWidth - 4 : frame.left + 7,
          y: Y(level.y) + (level.above ? -7 : 17),
          'text-anchor': level.end ? 'end' : 'start',
          text: level.text,
        }));
      }
    }

    for (const point of spec.marks ?? []) {
      if (point.x > spec.x.max) continue;
      const x = X(point.x);
      parts.push(
        svg('line', { x1: x, x2: x, y1: floor - 22, y2: floor, stroke: LINK }),
        mark('diamond', x, floor - 25, 2.8, { fill: PLATE, stroke: LINK }));
      if (!compact) parts.push(svg('text', { class: 'chart-label', x: x + 8, y: floor - 21, text: point.text }));
    }

    if (spec.cursor != null) {
      const x = X(spec.cursor);
      const nearEnd = spec.cursor > spec.x.max * 0.8;
      const besideMark = (spec.marks ?? []).some((point) => X(point.x) > x && X(point.x) - x < 40);
      parts.push(
        svg('line', { x1: x, x2: x, y1: frame.top, y2: floor, stroke: INK_2, 'stroke-dasharray': '1 4' }),
        svg('path', { d: `M${x} ${floor - 1}l-4-8h8z`, fill: INK_1 }));
      if (!compact) {
        parts.push(svg('text', {
          class: 'chart-value',
          x: x + (nearEnd ? -8 : 8),
          y: floor - (besideMark ? 40 : 5),
          'text-anchor': nearEnd ? 'end' : 'start',
          text: spec.x.format(spec.cursor),
        }));
      }
    }

    for (const series of spec.series) {
      const line = series.theory.filter(([, y]) => y != null);
      if (line.length > 1) {
        parts.push(svg('path', {
          d: line.map(([x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join(''),
          fill: 'none', stroke: INK_1, 'stroke-width': 1.3, 'stroke-dasharray': series.dash ?? null,
          opacity: series.quiet ? 0.5 : 1,
        }));
        if (series.labelAt != null) {
          const y = interpolate(line, series.labelAt);
          parts.push(svg('text', {
            class: 'chart-label', x: X(series.labelAt) + (series.labelBelow ? -6 : 6), y: Y(y) + (series.labelBelow ? 19 : -9),
            'text-anchor': series.labelBelow ? 'end' : 'start', text: series.name,
          }));
        }
      }
    }
    for (const series of spec.series) {
      for (const point of series.points ?? []) {
        const x = X(point.x);
        const y = Y(point.y);
        if (point.exact) {
          parts.push(mark(series.shape, x, y, 3.6, { fill: PLATE, stroke: INK_1, 'stroke-width': 1.2 }));
          continue;
        }
        parts.push(svg('circle', { cx: x, cy: y, r: 11, fill: 'url(#seam-point-glow)' }));
        if (point.lo != null) {
          parts.push(svg('path', {
            d: `M${x} ${Y(point.lo)}V${Y(point.hi)}M${x - 3} ${Y(point.lo)}h6M${x - 3} ${Y(point.hi)}h6`, fill: 'none', stroke: LINK,
          }));
        }
        parts.push(mark(series.shape, x, y, 3, { fill: '#FFE2A3' }));
      }
    }

    if (spec.loss && spec.loss.from < spec.x.max && !compact) {
      parts.push(svg('text', {
        class: 'chart-label', x: frame.left + plotWidth - 4, y: frame.top + 16, 'text-anchor': 'end', text: spec.loss.text,
      }));
    }
    return parts;
  });
}

/**
 * Horizontal bars on a 0 to 1 scale: an outline bar for theory, a filled bar
 * with a 95% whisker for a measured value.
 *
 * spec: { label, rows: [{ name, theory, value, lo, hi, exact }], table: { head, rows } }
 */
export function barChart(host) {
  return mount(host, (spec) => [spec.table.head, spec.table.rows], (spec, width, height) => {
    const frame = { left: 4, right: 44, top: 4, bottom: 24 };
    const plotWidth = width - frame.left - frame.right;
    const rowHeight = Math.min(64, (height - frame.top - frame.bottom) / spec.rows.length);
    const thickness = Math.min(14, rowHeight * 0.3);
    const X = (v) => frame.left + Math.max(0, Math.min(1, v)) * plotWidth;
    const floor = frame.top + rowHeight * spec.rows.length;
    const parts = [svg('line', { x1: frame.left, x2: frame.left + plotWidth, y1: floor, y2: floor, stroke: EDGE })];

    for (const tick of [0, 0.5, 1]) {
      parts.push(
        svg('line', { x1: X(tick), x2: X(tick), y1: floor, y2: floor + 4, stroke: EDGE }),
        svg('text', {
          class: 'chart-tick', x: X(tick), y: floor + 18,
          'text-anchor': tick === 0 ? 'start' : tick === 1 ? 'end' : 'middle', text: tick.toFixed(1),
        }));
    }
    spec.rows.forEach((row, index) => {
      const top = frame.top + index * rowHeight;
      const barY = top + rowHeight - thickness - 8;
      parts.push(svg('text', { class: 'chart-label', x: frame.left, y: barY - 7, text: row.name }));
      if (row.theory != null) {
        parts.push(svg('rect', {
          x: frame.left, y: barY, width: X(row.theory) - frame.left, height: thickness, fill: 'none', stroke: INK_1,
        }));
      }
      if (row.value != null && !row.exact) {
        parts.push(svg('rect', { x: frame.left, y: barY + 3, width: X(row.value) - frame.left, height: thickness - 6, fill: LINK }));
        if (row.lo != null) {
          const mid = barY + thickness / 2;
          parts.push(svg('path', {
            d: `M${X(row.lo)} ${mid}H${X(row.hi)}M${X(row.lo)} ${mid - 5}v10M${X(row.hi)} ${mid - 5}v10`, fill: 'none', stroke: INK_1,
          }));
        }
      }
      const shown = row.value ?? row.theory;
      if (shown != null) {
        parts.push(svg('text', {
          class: 'chart-value', x: frame.left + plotWidth + 8, y: barY + thickness / 2 + 5.5, text: shown.toFixed(2),
        }));
      }
    });
    return parts;
  });
}
