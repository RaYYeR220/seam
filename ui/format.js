const integer = new Intl.NumberFormat('en-US');

export const count = (value) => integer.format(Math.round(value));

const WHOLE = 1 - 1e-9;

/** A value between -1 and 1 to a fixed number of places; anything short of 1 never prints as 1. */
export function fixed(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return '—';
  const bounded = Math.min(1, Math.max(-1, value));
  const rounded = bounded.toFixed(digits);
  if (Math.abs(bounded) >= WHOLE || Math.abs(Number(rounded)) < 1) return rounded;
  const scale = 10 ** digits;
  return (Math.trunc(bounded * scale) / scale).toFixed(digits);
}

export const percent = (fraction) => `${Math.round(fraction * 100)}%`;

/** A link error as a percentage, keeping the quarter-percent of the announced link. */
export const errorRate = (q) => `${Number((q * 100).toFixed(2))}%`;

/**
 * A 95% interval as text. When every shot agreed, or the two ends print the
 * same, it says "all N shots" or nothing rather than "1.00–1.00".
 */
export function interval(entry, { digits = 2, shots = null, value = null } = {}) {
  if (entry == null || entry.lo == null || entry.hi == null) return '';
  const unanimous = shots ? `all ${count(shots)} shots` : '';
  if (value != null && value >= WHOLE) return unanimous;
  for (const places of [digits, digits + 1]) {
    const [lo, hi] = [fixed(entry.lo, places), fixed(entry.hi, places)];
    if (lo !== hi) return `95% interval ${lo}–${hi}`;
  }
  return entry.hi >= WHOLE ? unanimous : '';
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

export const inWords = (n) => WORDS[n] ?? String(n);

export function list(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

export const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);
