import { actions, choice, runButton, whileBusy } from './controls.js';
import { el, prefersReducedMotion, wait } from './dom.js';
import { count, fixed, interval } from './format.js';
import { errorNote, fillNumerals, note, resultParts } from './result.js';
import { sceneFromDistributed } from './scene.js';

/**
 * One teleported CNOT in the shape of the engine's `distributed` layout:
 * control c and link ion a in Trap A, link ion b and target t in Trap B.
 */
const TELEPORTED_CNOT = {
  wires: [
    { id: 0, kind: 'data', module: 0, label: 'c' },
    { id: 1, kind: 'data', module: 1, label: 't' },
    { id: 2, kind: 'comm', module: 0, label: 'a' },
    { id: 3, kind: 'comm', module: 1, label: 'b' },
  ],
  ops: [
    { name: 'h', wires: [2], role: 'pair', pair: 0 },
    { name: 'cx', wires: [2, 3], role: 'pair', pair: 0 },
    { name: 'cx', wires: [0, 2], role: 'cat', pair: 0 },
    { name: 'cx', wires: [2, 3], role: 'classical', pair: 0 },
    { name: 'cx', wires: [3, 1], role: 'remote', pair: 0 },
    { name: 'h', wires: [3], role: 'uncat', pair: 0 },
    { name: 'cz', wires: [3, 0], role: 'classical', pair: 0 },
  ],
};

const MOVES = [
  {
    name: 'All four',
    text: 'Walk through the four moves below, or press Run to measure all four inputs.',
    shows: () => true,
  },
  {
    name: 'Share a pair',
    text: 'The link delivers one entangled pair: one half to ion a in Trap A, the other to ion b in Trap B.',
    shows: (op) => op.role === 'pair',
  },
  {
    name: 'Fold the control in',
    text: 'A local CNOT folds the control c into the pair. One classical bit crosses, and b now carries a copy of c.',
    shows: (op) => op.role === 'cat' || (op.role === 'classical' && op.name === 'cx'),
  },
  {
    name: 'Act in B',
    text: 'Trap B applies the CNOT to its own target t, using b as the control. No quantum gate crosses the seam.',
    shows: (op) => op.role === 'remote',
  },
  {
    name: 'Unfold',
    text: 'A Hadamard and a second classical bit erase the copy. What is left is exactly a CNOT from c to t.',
    shows: (op) => op.role === 'uncat' || (op.role === 'classical' && op.name === 'cz'),
  },
];
const CLASSICAL_BITS = TELEPORTED_CNOT.ops.filter((op) => op.role === 'classical').length;
const WALK_MS = 520;

export function gateStep(view) {
  const { bridge, stage } = view;
  const scene = sceneFromDistributed(TELEPORTED_CNOT);
  const state = { move: 0, result: null, error: null, spent: false };

  const step = { enter, run };
  const showing = () => view.isShowing(step);

  const parts = resultParts();
  const table = el('table', { class: 'truth', 'data-demo': 'chart' });
  const runControl = runButton(() => whileBusy(runControl, 'Running', () => measure({ animate: true })));
  const moves = choice({
    label: 'Moves of the protocol',
    value: state.move,
    options: MOVES.map((move, index) => ({ value: index, label: move.name, numeral: index || null, demo: `scrub-${index}` })),
    onChange: showMove,
  });

  function drawRail() {
    view.setProse(
      el('p', {}, el('strong', {
        text: 'A CNOT between two computers that never touch costs one shared pair and two classical bits.',
      })),
      el('p', { text: MOVES[state.move].text }));
    view.setReadouts([
      { label: 'Pairs spent', value: state.result ? state.result.pairs : '—' },
      { label: 'Classical bits', value: CLASSICAL_BITS },
      { label: 'Shots', value: state.result?.shots ? count(state.result.shots) : '—' },
    ]);
  }

  function showMove(move) {
    state.move = move;
    stage.emphasise(MOVES[move].shows);
    drawRail();
  }

  function selectMove(move) {
    moves.select(move);
    showMove(move);
  }

  async function walk() {
    if (prefersReducedMotion()) return;
    for (let move = 1; move < MOVES.length; move += 1) {
      if (!showing()) return;
      selectMove(move);
      await wait(WALK_MS);
    }
    if (showing()) selectMove(0);
  }

  function truthRow(row, sampled, shots) {
    return el('tr', {},
      el('td', { class: 'ket', text: `|${row.input}⟩` }),
      el('td', { class: 'ket', text: `|${row.expected}⟩` }),
      el('td', { class: 'measured' }, el('span', { class: 'measured-cell' },
        el('span', { text: fixed(row.p_expected, 3) }),
        el('span', { class: `bar${sampled ? '' : ' is-theory'}` }, el('i', { style: `width:${row.p_expected * 100}%` })),
        el('small', { text: sampled ? interval(row, { digits: 3, shots, value: row.p_expected }) : 'exact' }))));
  }

  function drawResult({ settle = false } = {}) {
    const { result } = state;
    parts.heading.textContent = 'Teleported CNOT, all four inputs';
    if (!result) {
      fillNumerals(parts.numerals, []);
      table.replaceChildren();
      parts.message.replaceChildren(state.error ? errorNote(state.error) : note('Measuring the four inputs.'));
      return;
    }
    const sampled = result.source === 'measured';
    const lowest = result.rows.reduce((a, b) => (b.p_expected < a.p_expected ? b : a));
    fillNumerals(parts.numerals, [
      { label: 'Agreement', mark: 'diamond', value: result.agreement, digits: 3, measured: sampled, settle,
        detail: 'mean over the four rows' },
      { label: 'Lowest row', mark: 'ring', value: lowest.p_expected, digits: 3, measured: sampled, settle,
        detail: sampled ? interval(lowest, { digits: 3, shots: result.shots, value: lowest.p_expected }) : 'exact' },
    ]);
    table.replaceChildren(
      el('caption', { class: 'sr-only', text: 'Probability of the expected CNOT output for each input, control then target.' }),
      el('thead', {}, el('tr', {},
        el('th', { scope: 'col', text: 'Input c t' }),
        el('th', { scope: 'col', text: 'Expected' }),
        el('th', { scope: 'col', text: sampled ? 'Measured' : 'Computed' }))),
      el('tbody', {}, result.rows.map((row) => truthRow(row, sampled, result.shots))));
    const caveat = state.spent
      ? 'This backend takes one job per run and it is already spent, so the measured table stands.'
      : 'The two classical bits are drawn as gates (deferred measurement); on hardware they are a measured bit and a conditional flip. '
        + 'A truth table cannot see a missing phase correction: that is what Prove it in step 4 is for.';
    parts.message.replaceChildren(state.error ? errorNote(state.error) : note(caveat));
  }

  /** A measured table is never replaced by a computed one: on a one-job backend the first run is the only sample. */
  async function measure({ animate }) {
    const result = await bridge.measure({ kind: 'truth_table', q: 0 });
    state.error = result.error ?? null;
    if (!result.error) {
      state.spent = result.source === 'exact' && state.result?.source === 'measured';
      if (!state.spent) {
        state.result = result;
        view.session.truthTable = result;
      }
    }
    if (animate && showing() && !result.error) {
      await stage.play();
      await walk();
    }
    if (!showing()) return;
    drawRail();
    drawResult({ settle: !state.spent });
    if (state.spent) view.announce('This backend’s single job is already spent; the measured truth table stands.');
    else if (!result.error) {
      view.announce(`Truth table ${result.source === 'measured' ? 'measured' : 'computed'}: `
        + `agreement ${fixed(result.agreement, 3)} over four inputs.`);
    }
  }

  function enter() {
    stage.show(scene, { emphasis: MOVES[state.move].shows });
    view.setCaption('One teleported CNOT: the control c never leaves Trap A, the target t never leaves Trap B.');
    view.controls.replaceChildren(moves.node, actions(runControl));
    view.result.replaceChildren(parts.heading, parts.numerals, table, parts.message);
    drawRail();
    drawResult();
  }

  /** The first run of a session is the boot measurement and skips the animation. */
  function run() {
    return whileBusy(runControl, 'Running', () => measure({ animate: state.result != null }));
  }

  return step;
}
