import { el, svg, tween } from './dom.js';
import { fixed } from './format.js';
import { INK_1, LINK } from './palette.js';

const SETTLE_MS = 520;

const MARKS = {
  ring: () => svg('circle', { cx: 6, cy: 6, r: 4.4, fill: 'none', stroke: INK_1, 'stroke-width': 1.2 }),
  diamond: () => svg('path', { d: 'M6 .8 11.2 6 6 11.2.8 6z', fill: LINK }),
  hollowDiamond: () => svg('path', { d: 'M6 1.2 10.8 6 6 10.8 1.2 6z', fill: 'none', stroke: LINK, 'stroke-width': 1.2 }),
};

function markIcon(kind) {
  return svg('svg', { width: 12, height: 12, viewBox: '0 0 12 12', 'aria-hidden': 'true' }, MARKS[kind]());
}

/**
 * The two large numerals of a result. A value that was computed rather than
 * measured is drawn in outline, like theory in the charts.
 *
 * items: [{ label, mark, value, digits, detail, measured, settle }]
 */
export function fillNumerals(slot, items) {
  slot.replaceChildren(...items.map((item) => {
    const digits = item.digits ?? 2;
    const value = el('span', {
      class: `numeral-value${item.measured === false && item.value != null ? ' is-theory' : ''}`,
      text: fixed(item.value, digits),
    });
    if (item.settle && item.value != null) {
      tween(SETTLE_MS, (t) => { value.textContent = fixed(item.value * (1 - (1 - t) ** 3), digits); });
    }
    return el('div', {},
      el('span', { class: 'numeral-label' }, item.mark ? markIcon(item.mark) : null, item.label),
      value,
      el('span', { class: 'numeral-detail', text: item.detail ?? '' }));
  }));
}

/**
 * The fixed parts of a result column. A step mounts them once and fills them
 * in place, so keyboard focus and the chart survive every redraw.
 */
export function resultParts() {
  return {
    heading: el('h3', { class: 'result-heading' }),
    numerals: el('div', { class: 'numerals' }),
    chart: el('div', { class: 'chart', 'data-demo': 'chart' }),
    message: el('div', { class: 'result-message' }),
  };
}

/** The diamond that stands for a pair, set inside a sentence. */
export function pairGlyph() {
  const icon = markIcon('diamond');
  icon.setAttribute('class', 'pair-glyph');
  return icon;
}

export function note(...content) {
  return el('p', { class: 'result-note' }, content);
}

export function errorNote(message) {
  return el('p', { class: 'result-error', role: 'alert', text: message });
}
