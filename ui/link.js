/**
 * Entanglement fidelity IonQ reported for its memory-enhanced photonic link
 * (arXiv:2610.10705, 9 Oct 2026), read through this page's link model, where
 * a pair has fidelity (1 - q)^2. It is an assumption, not a measurement: the
 * figure was reported for ion-memory entanglement, not for a trap-to-trap pair.
 */
export const ANNOUNCED_LINK = { fidelity: 0.879, error: 0.0625 };

export const ANNOUNCED_LABEL = `announced link · ${(ANNOUNCED_LINK.fidelity * 100).toFixed(1)}% fidelity`;

export const ANNOUNCED_CAPTION = 'If a trap-to-trap pair had the fidelity IonQ reported for ion–memory entanglement.';

export const isAnnounced = (q) => Math.abs(q - ANNOUNCED_LINK.error) < 1e-9;

/** Link errors on a 1% grid up to `max`, plus the announced value. */
export function errorGrid(max) {
  const grid = Array.from({ length: Math.round(max * 100) + 1 }, (_, k) => k / 100);
  return [...grid, ANNOUNCED_LINK.error].sort((a, b) => a - b);
}
