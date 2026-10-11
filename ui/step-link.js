import { lineChart } from './charts.js';
import { actions, checkbox, runButton, slider, textButton, whileBusy } from './controls.js';
import { clamp, el } from './dom.js';
import { errorRate, fixed, interval, percent } from './format.js';
import { ANNOUNCED_CAPTION, ANNOUNCED_LABEL, ANNOUNCED_LINK, errorGrid, isAnnounced } from './link.js';
import { errorNote, fillNumerals, note, resultParts } from './result.js';
import { sceneFromPlan } from './scene.js';

const MAX_ERROR = 0.4;
const SWEEP_POINTS = [0, 0.1, 0.2, 0.3, 0.4];

/** The remote Bell pair circuit of the engine's `remote_bell` experiment, in the shape of a `plan` result. */
const REMOTE_BELL = {
  assignment: [0, 1],
  gates: [
    { i: 0, name: 'h', qubits: [0], cross: false, burst: null },
    { i: 1, name: 'cx', qubits: [0, 1], cross: true, burst: 0 },
  ],
  bursts: [{ id: 0, gate_indices: [1] }],
  cut: { cross_gates: 1, pairs: 1 },
};

const sameError = (a, b) => Math.abs(a - b) < 1e-9;
const keyOf = (q) => Math.round(q * 1e4);

export function linkStep(view) {
  const { bridge, stage } = view;
  const state = { q: 0.05, distill: false, theory: null, measured: new Map(), source: 'measured', error: null };
  let settled = null;

  const step = { enter, run, preset };
  const showing = () => view.isShowing(step);
  const theoryAt = (q) => state.theory?.points.find((point) => sameError(point.q, q));

  const parts = resultParts();
  const chart = lineChart(parts.chart);
  const runControl = runButton(() => whileBusy(runControl, 'Running', () => measure([state.q], true)));
  const sweepButton = textButton('Sweep', () => whileBusy(sweepButton, 'Sweeping', () => measure(SWEEP_POINTS, false)), 'sweep');
  const announcedButton = textButton('Set to the announced link', () => {
    state.q = ANNOUNCED_LINK.error;
    if (state.theory) state.error = null;
    mountControls();
    draw();
  }, 'announced');

  async function loadTheory() {
    const theory = await bridge.exact({ kind: 'remote_bell', qs: errorGrid(MAX_ERROR), distill: 'both' });
    if (theory.error) state.error = theory.error;
    else state.theory = theory;
    if (showing()) draw();
  }

  function drawStage() {
    const point = theoryAt(state.q);
    const fidelity = point ? (state.distill ? point.pair_fidelity_distilled : point.pair_fidelity) : 1;
    const pairStyle = {
      strength: 0.12 + 0.88 * Math.max(0, (fidelity - 0.3) / 0.7),
      raw: state.distill ? 2 : 1,
      label: state.distill ? 'two raw pairs, one kept' : 'one pair',
    };
    stage.show(sceneFromPlan(REMOTE_BELL, { labels: ['c', 't'], pairStyle }));
    view.setCaption(isAnnounced(state.q)
      ? ANNOUNCED_CAPTION
      : state.distill
        ? 'Two noisy pairs are spent to keep one better pair, and only when their check bits agree.'
        : 'One teleported CNOT entangles c with t. The pair it rides on is only as good as the link.');
  }

  function drawRail() {
    view.setProse(
      el('p', {},
        el('strong', { text: 'The link’s error lands almost one-for-one on the gate.' }),
        ' Distillation buys fidelity with pairs — until it doesn’t.'),
      el('p', { text: 'Raise the link error and watch the pair dim. Distilling spends two raw pairs for each one it keeps.' }));
    const point = theoryAt(state.q);
    const kept = point && state.distill ? point.distilled.kept : 1;
    view.setReadouts([
      { label: 'Pair fidelity', note: state.distill ? 'after distilling' : '(1 − q)²',
        value: point ? fixed(state.distill ? point.pair_fidelity_distilled : point.pair_fidelity, 3) : '—' },
      { label: 'Shots kept', value: point ? percent(kept) : '—' },
      { label: 'Raw pairs per good pair', value: point ? ((state.distill ? 2 : 1) / kept).toFixed(1) : '—' },
    ]);
  }

  function mountControls() {
    view.controls.replaceChildren(
      slider({
        label: 'Link error',
        demo: 'link-error',
        min: 0,
        max: MAX_ERROR * 100,
        step: 1,
        value: state.q * 100,
        mark: { value: ANNOUNCED_LINK.error * 100, title: ANNOUNCED_LABEL },
        format: (v) => `${v}%`,
        describe: (v) => `${v} percent`,
        onInput: (v) => {
          state.q = v / 100;
          if (state.theory) state.error = null;
          draw();
        },
      }),
      checkbox({
        label: 'Distill 2 → 1',
        demo: 'distill',
        checked: state.distill,
        onChange: (on) => {
          state.distill = on;
          draw();
        },
      }),
      actions(sweepButton, runControl),
    );
  }

  async function measure(qs, animate) {
    const result = await bridge.measure({ kind: 'remote_bell', qs, distill: 'both' });
    if (result.error) {
      state.error = result.error;
      if (showing()) drawResult();
      return;
    }
    if (animate && showing()) await stage.play();
    if (result.source !== state.source) state.measured.clear();
    Object.assign(state, { source: result.source, error: null });
    for (const point of result.points) state.measured.set(keyOf(point.q), point);
    const last = result.points[result.points.length - 1];
    view.session.bell = { point: last, source: result.source, thresholds: result.thresholds };
    if (showing()) drawResult({ settle: animate });
    view.announce(`Remote Bell pair at ${errorRate(last.q)} link error: raw fidelity ${fixed(last.raw.f)}, distilled ${fixed(last.distilled.f)}.`);
  }

  function numeralItem(label, mark, key, settle) {
    const measured = state.measured.get(keyOf(state.q));
    if (measured) {
      const sampled = state.source === 'measured';
      return { label, mark, value: measured[key].f, measured: sampled, settle, detail: sampled ? interval(measured[key]) : 'exact' };
    }
    const point = theoryAt(state.q);
    return { label, mark, value: point ? point[key].f : null, measured: false, detail: point ? 'predicted' : '' };
  }

  function chartSpec() {
    const { theory } = state;
    const stops = theory.thresholds.distill_stops_helping_q;
    const line = (key) => theory.points.map((point) => [point.q, point[key].f]);
    const points = (key) => [...state.measured.values()].map((point) => ({
      x: point.q, y: point[key].f, lo: point[key].lo, hi: point[key].hi, exact: state.source === 'exact',
    }));
    return {
      label: 'Fidelity of the remote Bell pair against link error, raw and distilled.'
        + (stops == null ? '' : ` Distilling stops helping at ${percent(stops)} link error.`),
      x: { min: 0, max: MAX_ERROR, ticks: [0, 0.1, 0.2, 0.3, 0.4], title: 'link error', format: errorRate },
      y: { min: 0.3, max: 1, ticks: [0.4, 0.6, 0.8, 1] },
      series: [
        { name: 'raw', shape: 'circle', theory: line('raw'), points: points('raw'), labelAt: 0.12, labelBelow: true, quiet: state.distill },
        { name: 'distilled', shape: 'diamond', dash: '7 4', theory: line('distilled'), points: points('distilled'), labelAt: 0.14, quiet: !state.distill },
      ],
      levels: [{ y: theory.thresholds.entanglement, text: 'no entanglement below this' }],
      loss: stops == null ? null : { from: stops, text: 'distilling loses here' },
      marks: [{ x: ANNOUNCED_LINK.error, text: ANNOUNCED_LABEL }],
      cursor: state.q,
      table: {
        head: ['Link error', 'Raw, theory', 'Distilled, theory', 'Raw, measured', 'Distilled, measured'],
        rows: theory.points.filter((point) => keyOf(point.q) % 500 === 0 || isAnnounced(point.q)).map((point) => {
          const hit = state.measured.get(keyOf(point.q));
          return [errorRate(point.q), fixed(point.raw.f, 3), fixed(point.distilled.f, 3),
            hit ? fixed(hit.raw.f, 3) : 'not measured', hit ? fixed(hit.distilled.f, 3) : 'not measured'];
        }),
      },
    };
  }

  function drawResult({ settle = false } = {}) {
    parts.heading.textContent = 'Fidelity of the remote Bell pair';
    fillNumerals(parts.numerals, [
      numeralItem('Raw', 'ring', 'raw', settle),
      numeralItem('Distilled', 'diamond', 'distilled', settle),
    ]);
    parts.message.replaceChildren(state.error
      ? errorNote(state.error)
      : note('Link noise is a model: independent X and Z flips on one half of each pair. '
        + 'Distilled results keep only the shots whose check bits agree.'));
    if (state.theory) chart.update(chartSpec());
  }

  function draw() {
    drawStage();
    drawRail();
    drawResult();
  }

  function preset({ q, distill }) {
    if (q != null) state.q = isAnnounced(q) ? q : clamp(Math.round(q * 100) / 100, 0, MAX_ERROR);
    if (distill != null) state.distill = distill;
  }

  function enter() {
    mountControls();
    view.result.replaceChildren(parts.heading, parts.numerals, parts.chart, parts.message);
    view.setRailAction(announcedButton);
    draw();
    settled ??= loadTheory();
  }

  async function run() {
    await settled;
    await whileBusy(runControl, 'Running', () => measure([state.q], true));
  }

  return step;
}
