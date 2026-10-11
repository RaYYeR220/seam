import { lineChart } from './charts.js';
import { actions, checkbox, field, runButton, select, slider, stepper, textButton, whileBusy } from './controls.js';
import { clamp, el, wait } from './dom.js';
import { capital, count, errorRate, fixed, interval, inWords, percent, plural } from './format.js';
import { ANNOUNCED_CAPTION, ANNOUNCED_LABEL, ANNOUNCED_LINK, errorGrid, isAnnounced } from './link.js';
import { errorNote, fillNumerals, note, pairGlyph, resultParts, showNotes } from './result.js';
import { sceneFromPlan } from './scene.js';

const MAX_ERROR = 0.5;
const SWEEP_POINTS = [0, 0.1, 0.2, 0.3, 0.4, 0.5];
const PREFERRED_ALGORITHM = 'qft_phase';
const PROOF_TRIALS = 16;
const PAUSE_MS = 150;

const sameError = (a, b) => Math.abs(a - b) < 1e-9;
const headline = (entry, metric) => (metric === 'success' ? entry.success : entry.hellinger);
const metricName = (metric) => (metric === 'hellinger' ? 'Hellinger fidelity' : 'Success probability');

export function splitStep(view) {
  const { bridge, catalog, stage } = view;
  const algorithms = catalog.algorithms;
  const first = algorithms.find((a) => a.id === PREFERRED_ALGORITHM) ?? algorithms[0];
  const state = {
    algorithm: first,
    n: first.n_default,
    assignment: null,
    q: 0.05,
    distill: false,
    plan: null,
    theory: null,
    measured: null,
    sweep: null,
    message: null,
    error: null,
    gap: null,
  };
  const limit = catalog.limits.max_backend_qubits;
  let request = 0;
  let settled = Promise.resolve();

  const step = { enter, run, preset, prove: () => prove(proveButton) };
  const showing = () => view.isShowing(step);
  const variant = () => (state.distill ? 'distilled' : 'raw');
  const planOptions = () => ({ algorithm: state.algorithm.id, n: state.n, assignment: state.assignment, reuse: true });
  const cutOptions = () => ({ ...planOptions(), assignment: state.plan.assignment });
  const clearResults = () => Object.assign(state, {
    theory: null, measured: null, sweep: null, message: null, error: null, gap: null,
  });

  const parts = resultParts();
  const chart = lineChart(parts.chart);
  const runControl = runButton(() => whileBusy(runControl, 'Running', measure));
  const sweepButton = textButton('Sweep the link', () => sweep(), 'sweep');
  const proveButton = textButton('Prove it', () => prove(proveButton), 'prove');
  const exportButton = textButton('Export QASM', () => exportQasm(), 'export');
  const announcedButton = textButton('Set to the announced link', () => {
    state.q = ANNOUNCED_LINK.error;
    state.error = null;
    mountControls();
    if (state.plan) draw();
  }, 'announced');
  const sizeControl = stepper({
    label: 'Qubits',
    unit: 'qubit',
    min: first.n_min,
    max: first.n_max,
    value: first.n_default,
    onChange: (n) => {
      state.n = n;
      sizeControl.update({ value: n });
      replan(null);
    },
  });

  /** Starts the latest of a burst of requests after a short pause; earlier ones are dropped. */
  function schedule(task) {
    const mine = ++request;
    settled = wait(PAUSE_MS).then(() => (mine === request ? task(mine) : undefined));
  }

  async function loadPlan(mine) {
    const plan = await bridge.plan(planOptions());
    if (mine !== request) return;
    if (plan.error) {
      state.assignment = state.plan && !state.plan.auto ? state.plan.assignment : null;
      state.error = plan.error;
      if (showing()) drawResult();
      return;
    }
    const replanned = Boolean(state.plan);
    clearResults();
    Object.assign(state, { plan, assignment: plan.auto ? null : plan.assignment });
    if (showing()) {
      draw();
      if (replanned) view.announce(sceneFromPlan(plan).summary);
    }
    await loadTheory(mine);
  }

  /** The curve needs link noise on every pair, which can outgrow the backend when the circuit at 0% still fits. */
  async function loadTheory(mine) {
    const totals = state.plan.qubits;
    const needed = state.distill ? totals.total_noisy_distilled : totals.total_noisy;
    if (needed > limit) {
      state.gap = `No prediction curve: with link noise${state.distill ? ' and distillation' : ''} this cut needs `
        + `${needed} qubits and the backend holds ${limit}. `
        + (state.distill && totals.total_noisy <= limit ? 'Switch Distill off to see it.' : 'A smaller circuit or a cheaper cut brings it back.');
    } else {
      const theory = await bridge.exact({ kind: 'algorithm_sweep', ...cutOptions(), qs: errorGrid(MAX_ERROR), distill: state.distill });
      if (mine !== request) return;
      if (theory.error) state.gap = theory.error;
      else state.theory = theory;
    }
    if (showing()) drawResult();
  }

  function replan(assignment) {
    state.assignment = assignment;
    schedule(loadPlan);
  }

  function moveQubit(qubit) {
    const next = [...(state.assignment ?? state.plan.assignment)];
    if (next.filter((side) => side === next[qubit]).length <= 1) return;
    next[qubit] = 1 - next[qubit];
    replan(next);
  }

  const canMove = (qubit) =>
    state.plan.assignment.filter((side) => side === state.plan.assignment[qubit]).length > 1;

  function qubitsNeeded() {
    const totals = state.plan.qubits;
    if (state.q > 0) return state.distill ? totals.total_noisy_distilled : totals.total_noisy;
    return state.distill ? totals.total_distilled : totals.total_clean;
  }

  function drawCaption() {
    view.setCaption(isAnnounced(state.q)
      ? ANNOUNCED_CAPTION
      : `${state.algorithm.name} on ${inWords(state.plan.n)} ions. Press a qubit’s name to move it across the seam.`);
  }

  function drawStage() {
    stage.show(sceneFromPlan(state.plan), { onMove: moveQubit, canMove });
    drawCaption();
  }

  function drawRail() {
    const { cut, scores } = state.plan;
    const claim = cut.pairs < cut.cross_gates
      ? [el('strong', { text: `${capital(inWords(cut.cross_gates))} gates cross the seam, but ` }),
        el('span', { class: 'pair-word' }, pairGlyph(), `${inWords(cut.pairs)} ${cut.pairs === 1 ? 'pair' : 'pairs'}`),
        el('strong', { text: ` ${cut.pairs === 1 ? 'is' : 'are'} enough` }), ': gates that share a control ride the same pair.']
      : [el('strong', { text: 'Every gate that crosses the seam costs one shared pair.' }),
        cut.cross_gates ? ` Here that is ${plural(cut.pairs, 'pair')}.` : ' This cut is free: no gate crosses it.'];
    view.setProse(
      el('p', {}, claim),
      el('p', { text: 'Move the cut, set the link error, then run the split against one whole machine.' }));

    const needed = qubitsNeeded();
    view.setReadouts([
      { label: 'Crossing gates', value: cut.cross_gates },
      { label: 'Pairs', note: `${cut.pairs_without_reuse} without reuse · best cut ${scores.best}`, value: cut.pairs },
      { label: 'Qubits used', note: needed > limit ? `the backend holds ${limit}` : null, value: needed, over: needed > limit },
    ]);
  }

  function mountControls() {
    view.controls.replaceChildren(
      select({
        label: 'Algorithm',
        demo: 'algorithm',
        value: state.algorithm.id,
        options: algorithms.map((a) => ({ value: a.id, label: a.name })),
        onChange: (id) => {
          state.algorithm = algorithms.find((a) => a.id === id);
          state.n = state.algorithm.n_default;
          sizeControl.update({ min: state.algorithm.n_min, max: state.algorithm.n_max, value: state.n });
          replan(null);
        },
      }),
      sizeControl.node,
      field('Cut', textButton('Auto cut', () => replan(null), 'autocut')),
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
          state.error = null;
          if (!state.plan) return;
          drawCaption();
          drawRail();
          drawResult();
        },
      }),
      checkbox({
        label: 'Distill 2 → 1',
        demo: 'distill',
        checked: state.distill,
        onChange: (on) => {
          state.distill = on;
          if (!state.plan) return;
          clearResults();
          draw();
          schedule(loadTheory);
        },
      }),
      actions(runControl),
    );
  }

  async function measure() {
    if (!state.plan) return;
    const mine = request;
    const ran = { name: state.algorithm.name, n: state.plan.n };
    const result = await bridge.measure({ kind: 'algorithm', ...cutOptions(), q: state.q, distill: state.distill });
    if (mine !== request) return;
    if (result.error) {
      state.error = result.error;
      if (showing()) drawResult();
      return;
    }
    if (showing()) await stage.play();
    if (mine !== request) return;
    Object.assign(state, { measured: result, message: null, error: null });
    view.session.algorithm = { result, ...ran };
    if (showing()) drawResult({ settle: true });
    view.announce(`${ran.name}, ${metricName(result.metric).toLowerCase()}: `
      + `one machine ${fixed(headline(result.mono, result.metric))}, `
      + `split in two ${fixed(headline(result.dist, result.metric))} at ${errorRate(result.q)} link error.`);
  }

  /**
   * Runs a secondary action and shows its note, or its error, under the chart.
   * What it adds to the session ledger is kept only if the cut is still the same.
   */
  function act(button, workingLabel, task) {
    if (!state.plan) return Promise.resolve();
    return whileBusy(button, workingLabel, async () => {
      const mine = request;
      const { record, ...outcome } = await task();
      if (mine !== request) return;
      if (outcome.error) state.error = outcome.error;
      else {
        Object.assign(view.session, record);
        Object.assign(state, { error: null, ...outcome });
        view.announce(outcome.message?.textContent
          ?? `Sweep finished: ${outcome.sweep.points.length} link errors ${outcome.sweep.source === 'exact' ? 'computed' : 'measured'}.`);
      }
      if (showing()) drawResult();
    });
  }

  function sweep() {
    return act(sweepButton, 'Sweeping', async () => {
      const result = await bridge.measure({ kind: 'algorithm_sweep', ...cutOptions(), qs: SWEEP_POINTS, distill: state.distill });
      return result.error ? result : { sweep: result };
    });
  }

  function prove(button) {
    return act(button, 'Proving', async () => {
      const proved = { name: state.algorithm.name, n: state.plan.n };
      const proof = await bridge.proof({ ...cutOptions(), trials: PROOF_TRIALS });
      if (proof.error) return proof;
      return {
        record: { proof: { proof, ...proved } },
        message: note(
          el('strong', { text: proof.passed ? 'Proven on a perfect link. ' : 'The proof failed. ' }),
          `Lowest fidelity with the original over ${proof.trials} random inputs: ${proof.fidelity_min.toFixed(6)}. `,
          proof.negative_control == null
            ? 'This cut spends no pair, so there is no correction to remove.'
            : `With one correction removed it drops to ${fixed(proof.negative_control)}, as it must.`),
      };
    });
  }

  function exportQasm() {
    return act(exportButton, 'Exporting', async () => {
      const file = await bridge.exportQasm({ ...cutOptions(), q: state.q, distill: state.distill });
      if (file.error) return file;
      return {
        message: note(el('strong', { text: `${file.filename} ` }), file.sent
          ? `saved, ${count(file.bytes)} bytes of OpenQASM 2.`
          : `is ${count(file.bytes)} bytes, but this page could not hand it over as a file.`),
      };
    });
  }

  function theoryAt(q) {
    const point = state.theory?.points?.find((p) => sameError(p.q, q));
    return point ? point[variant()].value : null;
  }

  function numeralItems(settle) {
    const { measured, theory } = state;
    if (measured && sameError(measured.q, state.q)) {
      const sampled = measured.source === 'measured';
      const mono = headline(measured.mono, measured.metric);
      const split = headline(measured.dist, measured.metric);
      const kept = measured.distill ? `, kept ${percent(measured.dist.kept)} of shots` : '';
      const allShots = measured.distill ? {} : { shots: measured.shots, value: split };
      return [
        { label: 'One machine', mark: 'ring', value: mono, measured: sampled, settle,
          detail: sampled ? interval(measured.mono, { shots: measured.shots, value: mono }) : 'exact' },
        { label: 'Split in two', mark: 'diamond', value: split, measured: sampled, settle,
          detail: sampled ? `${interval(measured.dist, allShots)}${kept}` : `exact${kept}` },
      ];
    }
    const predicted = Boolean(theory);
    return [
      { label: 'One machine', mark: 'ring', value: predicted ? theory.mono : null, measured: false,
        detail: predicted ? 'predicted' : '' },
      { label: 'Split in two', mark: 'hollowDiamond', value: predicted ? theoryAt(state.q) : null, measured: false,
        detail: predicted ? 'predicted — press Run' : '' },
    ];
  }

  function measuredPoints(key) {
    const { measured, sweep: swept } = state;
    const points = (swept?.points ?? []).map((row) => ({
      x: row.q, y: row[key].value, lo: row[key].lo, hi: row[key].hi, exact: swept.source === 'exact',
    }));
    if (measured) {
      points.push({
        x: measured.q,
        y: headline(measured.dist, measured.metric),
        lo: measured.dist.lo,
        hi: measured.dist.hi,
        exact: measured.source === 'exact',
      });
    }
    return points;
  }

  function chartSpec() {
    const { theory } = state;
    const key = variant();
    const breakEven = theory.break_even_q[key];
    const succeeds = theory.metric === 'success';
    const reach = breakEven == null ? 0.4 : Math.ceil((breakEven + 0.08) * 20) / 20;
    const xMax = Math.min(MAX_ERROR, Math.max(0.3, reach, Math.ceil(state.q * 10) / 10));
    const within = (q) => q <= xMax + 1e-9;
    const points = measuredPoints(key).filter((point) => within(point.x));
    const labelAt = Math.round(xMax * 30) / 100;
    const computed = points.some((point) => point.exact);
    return {
      label: `${metricName(theory.metric)} of the split circuit against link error, from 0 to ${percent(xMax)}. `
        + (!succeeds ? '' : breakEven == null ? 'It stays above one half over the whole range.' : `It falls below one half at ${percent(breakEven)}.`),
      x: {
        min: 0,
        max: xMax,
        ticks: Array.from({ length: Math.floor(xMax * 10 + 1e-9) + 1 }, (_, k) => k / 10),
        title: 'link error',
        format: errorRate,
      },
      y: { min: 0, max: 1, ticks: [0, 0.2, 0.4, 0.6, 0.8, 1] },
      series: [{
        name: 'theory',
        shape: 'circle',
        theory: theory.points.filter((p) => within(p.q)).map((p) => [p.q, p[key].value]),
        points,
        labelAt,
        labelBelow: theoryAt(labelAt) > 0.85,
      }],
      levels: [
        { y: theory.mono, text: 'one machine', dash: '1 4', end: true },
        succeeds
          ? { y: 0.5, text: 'below ½: wrong more often than right' }
          : { y: theory.classical_guess, text: `uniform outcomes score ${fixed(theory.classical_guess)}` },
      ],
      loss: succeeds && breakEven != null ? { from: breakEven, text: 'split loses here' } : null,
      marks: [{ x: ANNOUNCED_LINK.error, text: ANNOUNCED_LABEL }],
      cursor: state.q,
      table: {
        head: ['Link error', 'Theory', computed ? 'Computed' : 'Measured'],
        rows: theory.points.filter((p) => within(p.q) && (Math.round(p.q * 1e4) % 500 === 0 || isAnnounced(p.q))).map((p) => {
          const hit = points.find((point) => sameError(point.x, p.q));
          return [errorRate(p.q), fixed(p[key].value, 3), hit ? fixed(hit.y, 3) : 'not run'];
        }),
      },
    };
  }

  /** The link budget of the last run, shown while the slider still sits where it was measured. */
  function budgetNote() {
    const { measured } = state;
    if (!measured || !sameError(measured.q, state.q)) return null;
    const { budget } = measured;
    if (budget.shots_per_second == null) return null;
    const pairs = budget.raw_pairs_per_shot === budget.pairs_per_shot
      ? plural(budget.pairs_per_shot, 'pair')
      : `${budget.raw_pairs_per_shot} raw pairs`;
    return note(`${pairs} per shot → about ${count(budget.kept_shots_per_second)} shots per second at `
      + `${count(catalog.link.pair_rate_hz)} pairs/s. `, el('strong', { text: 'A model, not a measurement.' }));
  }

  function drawResult({ settle = false } = {}) {
    const { theory } = state;
    const pending = !theory && !state.gap;
    const notes = state.error
      ? [errorNote(state.error)]
      : [
        state.gap ? errorNote(state.gap) : null,
        state.message ?? budgetNote() ?? (pending ? note('Computing the prediction.') : null),
      ].filter(Boolean);
    parts.heading.textContent = metricName((state.measured ?? theory)?.metric);
    fillNumerals(parts.numerals, numeralItems(settle));
    parts.chart.hidden = Boolean(state.gap);
    showNotes(parts.message, ...notes);
    if (theory) chart.update(chartSpec());
    else chart.clear();
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
    view.result.replaceChildren(
      parts.heading, parts.numerals, parts.chart, parts.message,
      el('div', { class: 'result-actions' }, sweepButton, proveButton, exportButton));
    view.setRailAction(announcedButton);
    if (state.plan) draw();
    else {
      view.setProse(el('p', { text: 'Planning the cut.' }));
      view.setReadouts([]);
      drawResult();
      replan(null);
    }
  }

  async function run() {
    await settled;
    if (state.plan) await whileBusy(runControl, 'Running', measure);
  }

  return step;
}
