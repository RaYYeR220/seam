import { barChart } from './charts.js';
import { actions, checkbox, runButton, slider, stepper, whileBusy } from './controls.js';
import { clamp, el } from './dom.js';
import { fixed, interval, inWords, percent, plural } from './format.js';
import { errorNote, fillNumerals, note, resultParts } from './result.js';
import { sceneFromPlan } from './scene.js';

const MAX_TARGETS = 4;
const MAX_ERROR = 0.3;

/** The fan-out circuit of the engine's `burst` experiment, in the shape of a `plan` result. */
function fanOut(k, reuse) {
  const crossing = Array.from({ length: k }, (_, index) => ({
    i: index + 1, name: 'cx', qubits: [0, index + 1], cross: true, burst: reuse ? 0 : index,
  }));
  const bursts = reuse
    ? [{ id: 0, gate_indices: crossing.map((gate) => gate.i) }]
    : crossing.map((gate) => ({ id: gate.burst, gate_indices: [gate.i] }));
  return {
    assignment: [0, ...Array(k).fill(1)],
    gates: [{ i: 0, name: 'h', qubits: [0], cross: false, burst: null }, ...crossing],
    bursts,
    cut: { cross_gates: k, pairs: bursts.length },
  };
}

export function burstStep(view) {
  const { bridge, stage } = view;
  const state = { k: 3, reuse: true, q: 0.05, theory: null, measured: null, error: null };
  let request = 0;
  let settled = Promise.resolve();

  const step = { enter, run, preset };
  const showing = () => view.isShowing(step);
  const spec = () => ({ kind: 'burst', k: state.k, q: state.q, reuse: 'both' });
  const current = (result) => (result && result.k === state.k && Math.abs(result.q - state.q) < 1e-9 ? result : null);
  const variantOf = (result, reuse) => current(result)?.variants.find((v) => v.reuse === reuse);

  const parts = resultParts();
  parts.chart.classList.add('is-bars');
  const chart = barChart(parts.chart);
  const aside = el('details', { class: 'aside' },
    el('summary', { text: 'Why not always?' }),
    el('p', { text: 'A pair can be reused only while nothing rotates the control out of the Z basis. '
      + 'A Hadamard on c between two of these gates would spoil the copy held in Trap B, and the next gate would need a fresh pair.' }));
  const runControl = runButton(() => whileBusy(runControl, 'Running', measure));
  const targets = stepper({
    label: 'Targets',
    unit: 'target',
    min: 1,
    max: MAX_TARGETS,
    value: state.k,
    demo: { minus: 'k-minus', plus: 'k-plus' },
    onChange: (k) => {
      state.k = k;
      targets.update({ value: k });
      drawStage();
      settled = refreshTheory();
    },
  });

  async function refreshTheory() {
    const mine = ++request;
    Object.assign(state, { theory: null, error: null });
    if (showing()) {
      drawRail();
      drawResult();
    }
    const theory = await bridge.exact(spec());
    if (mine !== request) return;
    if (theory.error) state.error = theory.error;
    else state.theory = theory;
    if (showing()) {
      drawRail();
      drawResult();
    }
  }

  function drawStage() {
    const labels = ['c', ...Array.from({ length: state.k }, (_, i) => `t${i + 1}`)];
    stage.show(sceneFromPlan(fanOut(state.k, state.reuse), { labels }));
    view.setCaption(state.reuse
      ? `One control in Trap A drives ${inWords(state.k)} ${state.k === 1 ? 'target' : 'targets'} in Trap B through a single pair.`
      : `Without reuse ${state.k === 1 ? 'the gate spends one pair' : `each of the ${inWords(state.k)} gates spends a pair of its own`}.`);
  }

  function drawRail() {
    view.setProse(
      el('p', {},
        el('strong', { text: 'Gates that share a control ride the same pair' }),
        ' — and fewer pairs means fewer chances for the link to fail.'),
      el('p', { text: 'Add targets, then switch reuse off to see what each gate would cost alone.' }));
    const shown = variantOf(state.theory, state.reuse);
    view.setReadouts([
      { label: 'Gates across the seam', value: state.k },
      { label: 'Pairs used', value: shown ? shown.pairs : '—' },
      { label: 'Qubits used', value: shown ? shown.qubits : '—' },
    ]);
  }

  function mountControls() {
    view.controls.replaceChildren(
      targets.node,
      checkbox({
        label: 'Reuse the pair',
        demo: 'reuse',
        checked: state.reuse,
        onChange: (on) => {
          state.reuse = on;
          drawStage();
          drawRail();
        },
      }),
      slider({
        label: 'Link error',
        demo: 'link-error',
        min: 0,
        max: MAX_ERROR * 100,
        step: 1,
        value: Math.round(state.q * 100),
        format: (v) => `${v}%`,
        describe: (v) => `${v} percent`,
        onChange: (v) => {
          state.q = v / 100;
          settled = refreshTheory();
        },
      }),
      actions(runControl),
    );
  }

  async function measure() {
    const mine = request;
    const result = await bridge.measure(spec());
    if (mine !== request) return;
    if (result.error) {
      state.error = result.error;
      if (showing()) drawResult();
      return;
    }
    if (showing()) await stage.play();
    if (mine !== request) return;
    Object.assign(state, { measured: result, error: null });
    view.session.burst = result;
    if (showing()) drawResult({ settle: true });
    const [shared, separate] = [true, false].map((reuse) => variantOf(result, reuse));
    view.announce(`GHZ fidelity at ${percent(result.q)} link error: at least ${fixed(shared.fidelity.value)} with one pair, `
      + `at least ${fixed(separate.fidelity.value)} with ${plural(separate.pairs, 'pair')}.`);
  }

  function numeralItem(label, mark, reuse, settle) {
    const measured = variantOf(state.measured, reuse);
    if (measured) {
      const sampled = state.measured.source === 'measured';
      return { label, mark, value: measured.fidelity.value, measured: sampled, settle,
        detail: sampled ? interval(measured.fidelity) : 'exact' };
    }
    const theory = variantOf(state.theory, reuse);
    return { label, mark, value: theory ? theory.fidelity.value : null, measured: false, detail: theory ? 'predicted' : '' };
  }

  function chartRow(reuse) {
    const theory = variantOf(state.theory, reuse);
    const measured = variantOf(state.measured, reuse);
    const pairs = (measured ?? theory)?.pairs;
    const gates = state.k === 1 ? 'its one gate' : `all ${inWords(state.k)} gates`;
    return {
      name: pairs == null ? '' : reuse ? `${plural(pairs, 'pair')} for ${gates}` : `${plural(pairs, 'pair')}, one per gate`,
      theory: theory?.fidelity.value,
      value: measured?.fidelity.value,
      lo: measured?.fidelity.lo,
      hi: measured?.fidelity.hi,
      exact: state.measured?.source === 'exact',
    };
  }

  function drawResult({ settle = false } = {}) {
    const rows = [chartRow(true), chartRow(false)];
    const caveat = state.theory
      ? note('The fidelity is a lower bound from two settings: all outcomes equal in Z, and the X parity.')
      : note('Computing the prediction.');
    parts.heading.textContent = `Fidelity of the ${state.k + 1}-qubit GHZ state, at least`;
    fillNumerals(parts.numerals, [
      numeralItem('One shared pair', 'diamond', true, settle),
      numeralItem('One pair per gate', 'hollowDiamond', false, settle),
    ]);
    parts.message.replaceChildren(state.error ? errorNote(state.error) : caveat);
    chart.update({
      label: `GHZ fidelity lower bound at ${percent(state.q)} link error, one shared pair against one pair per gate.`,
      rows,
      table: {
        head: ['Variant', 'Theory', 'Measured'],
        rows: rows.map((row) => [
          row.name,
          row.theory == null ? 'pending' : fixed(row.theory, 3),
          row.value == null ? 'not measured' : fixed(row.value, 3),
        ]),
      },
    });
  }

  function preset({ q }) {
    if (q != null) state.q = clamp(Math.round(q * 100) / 100, 0, MAX_ERROR);
  }

  function enter() {
    mountControls();
    view.result.replaceChildren(parts.heading, parts.numerals, parts.chart, aside, parts.message);
    drawStage();
    drawRail();
    drawResult();
    if (!current(state.theory)) settled = refreshTheory();
  }

  async function run() {
    await settled;
    await whileBusy(runControl, 'Running', measure);
  }

  return step;
}
