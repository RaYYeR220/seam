import { list, plural } from './format.js';

/**
 * A scene is what the stage draws: wires from top to bottom (Trap A first),
 * operations placed in columns, and the Bell pairs that sit on the seam.
 */

function assignColumns(ops) {
  const free = [];
  for (const op of ops) {
    const low = Math.min(...op.rows);
    const high = Math.max(...op.rows);
    let column = 0;
    for (let row = low; row <= high; row += 1) column = Math.max(column, free[row] ?? 0);
    for (let row = low; row <= high; row += 1) free[row] = column + 1;
    op.column = column;
  }
  return Math.max(0, ...free.filter((value) => value != null));
}

function appendMeasurements(ops, wires, column) {
  wires.forEach((wire, row) => {
    if (wire.kind === 'data') ops.push({ glyph: 'measure', name: 'measure', rows: [row], column });
  });
}

function describeCut(wires, crossings, pairs) {
  const names = (module) => list(wires.filter((w) => w.module === module && w.kind === 'data').map((w) => w.label));
  const cut = crossings === 0
    ? 'No gate crosses the seam.'
    : `${plural(crossings, 'gate')} cross${crossings === 1 ? 'es' : ''} the seam using ${plural(pairs, 'pair')}.`;
  return `Trap A holds ${names(0)}. Trap B holds ${names(1)}. ${cut}`;
}

/** Scene of an original circuit with its cut, from the engine's `plan` result. */
export function sceneFromPlan(plan, { labels = null, pairStyle = {} } = {}) {
  const order = [0, 1].flatMap((module) =>
    plan.assignment.map((side, qubit) => (side === module ? qubit : -1)).filter((qubit) => qubit >= 0));
  const rowOf = new Map(order.map((qubit, row) => [qubit, row]));
  const wires = order.map((qubit) => ({
    label: labels ? labels[qubit] : `q${qubit}`,
    module: plan.assignment[qubit],
    kind: 'data',
    qubit,
  }));

  const ops = plan.gates.map((gate) => ({
    glyph: gate.qubits.length === 2 ? 'link' : 'box',
    name: gate.name,
    rows: gate.qubits.map((qubit) => rowOf.get(qubit)),
    cross: gate.cross,
    pair: gate.burst,
  }));
  const columns = assignColumns(ops);
  appendMeasurements(ops, wires, columns);

  const pairs = plan.bursts.map((burst) => ({
    id: burst.id,
    ops: ops.flatMap((op, index) => (op.pair === burst.id ? [index] : [])),
    ...pairStyle,
  }));

  return {
    wires,
    ops,
    pairs,
    columns: columns + 1,
    summary: describeCut(wires, plan.cut.cross_gates, plan.cut.pairs),
  };
}

const DRAWN_KINDS = new Set(['data', 'comm']);

/**
 * Scene of a teleported circuit, from data shaped like the engine's
 * `distributed` result. Link ions sit next to the seam; the environment and
 * sacrifice qubits of the noise model are left out of the picture.
 */
export function sceneFromDistributed(layout) {
  const rank = (wire) => (wire.module === 0 ? (wire.kind === 'data' ? 0 : 1) : (wire.kind === 'comm' ? 2 : 3));
  const kept = layout.wires
    .filter((wire) => DRAWN_KINDS.has(wire.kind))
    .sort((a, b) => rank(a) - rank(b) || a.id - b.id);
  const rowOf = new Map(kept.map((wire, row) => [wire.id, row]));
  const wires = kept.map((wire) => ({
    label: wire.label,
    module: wire.module,
    kind: wire.kind === 'comm' ? 'link' : 'data',
    qubit: null,
  }));

  const ops = [];
  for (const op of layout.ops) {
    if (op.role === 'measure' || op.role === 'noise' || op.role === 'distill') continue;
    if (!op.wires.every((wire) => rowOf.has(wire))) continue;
    if (op.role === 'pair' && op.wires.length === 1) continue;
    ops.push({
      glyph: op.role === 'pair' ? 'pair' : op.wires.length === 2 ? 'link' : 'box',
      name: op.name,
      rows: op.wires.map((wire) => rowOf.get(wire)),
      cross: op.role === 'pair',
      classical: op.role === 'classical',
      note: op.role === 'classical' ? 'classical bit' : null,
      pair: op.role === 'pair' ? op.pair : null,
      role: op.role,
    });
  }
  const columns = assignColumns(ops);
  appendMeasurements(ops, wires, columns);

  const pairIds = [...new Set(ops.filter((op) => op.glyph === 'pair').map((op) => op.pair))];
  const pairs = pairIds.map((id) => ({
    id,
    ops: ops.flatMap((op, index) => (op.glyph === 'pair' && op.pair === id ? [index] : [])),
  }));
  const teleported = ops.filter((op) => op.role === 'remote').length;

  return {
    wires,
    ops,
    pairs,
    columns: columns + 1,
    summary: `${describeCut(wires, teleported, pairs.length)} Each trap also holds one link ion per pair.`,
  };
}
