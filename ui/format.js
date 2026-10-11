const integer = new Intl.NumberFormat('en-US');

export const count = (value) => integer.format(Math.round(value));

export function fixed(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return '—';
  return Math.min(1, Math.max(-1, value)).toFixed(digits);
}

export const percent = (fraction) => `${Math.round(fraction * 100)}%`;

/** A link error as a percentage, keeping the quarter-percent of the announced link. */
export const errorRate = (q) => `${Number((q * 100).toFixed(2))}%`;

/** A 95% interval as text; a value that every shot agreed on says so instead of "1.00–1.00". */
export function interval(entry, { digits = 2, shots = null, value = null } = {}) {
  if (entry == null || entry.lo == null || entry.hi == null) return '';
  if (shots && value === 1) return `all ${count(shots)} shots`;
  const places = fixed(entry.lo, digits) === fixed(entry.hi, digits) ? digits + 1 : digits;
  return `95% interval ${fixed(entry.lo, places)}–${fixed(entry.hi, places)}`;
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

export const inWords = (n) => WORDS[n] ?? String(n);

export function list(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

export const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);
