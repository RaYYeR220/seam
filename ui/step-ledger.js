import { textButton } from './controls.js';
import { el, svg } from './dom.js';
import { count, errorRate, fixed, percent, plural } from './format.js';
import { INK_1, INK_3, LINK } from './palette.js';

const TIER_MARKS = {
  Measured: () => svg('path', { d: 'M6 .8 11.2 6 6 11.2.8 6z', fill: LINK }),
  Exact: () => svg('path', { d: 'M6 1.2 10.8 6 6 10.8 1.2 6z', fill: 'none', stroke: INK_1, 'stroke-width': 1.2 }),
  Proven: () => svg('rect', { x: 1.5, y: 1.5, width: 9, height: 9, fill: INK_1 }),
  Modeled: () => svg('circle', { cx: 6, cy: 6, r: 4.4, fill: 'none', stroke: INK_1, 'stroke-width': 1.2, 'stroke-dasharray': '2 2' }),
  'Not claimed': () => svg('path', { d: 'M1.5 6h9', fill: 'none', stroke: INK_3, 'stroke-width': 1.4 }),
};

function tierCell(tier) {
  return el('td', { class: 'tier' },
    svg('svg', { width: 12, height: 12, viewBox: '0 0 12 12', 'aria-hidden': 'true' }, TIER_MARKS[tier]()),
    tier);
}

const NOT_CLAIMED = 'A speed-up over one machine. A real classical channel: the two bits per pair are deferred gates. '
  + 'Memory decoherence, gate errors inside the traps, or loss in the fibre.';

export function ledgerStep(view) {
  const { bridge, catalog, session } = view;

  const tierOf = (source) => (source === 'measured' ? 'Measured' : 'Exact');
  const tierToCome = () => (bridge.mode().sampling ? 'Measured' : 'Exact');
  const provenance = (source) => (source === 'measured'
    ? `${bridge.mode().backend}`
    : 'computed exactly, not sampled');

  function pending(stepIndex) {
    return el('span', { class: 'pending' },
      `not run yet — step ${stepIndex + 1}`,
      textButton(`Go to step ${stepIndex + 1}`, () => view.goTo(stepIndex)));
  }

  function evidence(text, source) {
    return el('span', {}, text, source ? el('small', { text: ` · ${provenance(source)}` }) : null);
  }

  function rows() {
    const { truthTable, burst, bell, algorithm, proof } = session;
    const shared = burst?.variants.find((v) => v.reuse);
    const separate = burst?.variants.find((v) => !v.reuse);
    const metric = algorithm?.result.metric === 'hellinger' ? 'hellinger' : 'success';
    const budget = algorithm?.result.budget;
    const stops = bell?.thresholds.distill_stops_helping_q;
    return [
      [truthTable ? tierOf(truthTable.source) : tierToCome(),
        'A teleported CNOT reproduces the CNOT truth table with one pair.',
        truthTable ? evidence(`agreement ${fixed(truthTable.agreement, 3)} over four inputs`, truthTable.source) : pending(0)],
      [burst ? tierOf(burst.source) : tierToCome(),
        'One pair serves every gate that shares a control.',
        burst
          ? evidence(`GHZ fidelity ≥ ${fixed(shared.fidelity.value)} on ${plural(shared.pairs, 'pair')}, ≥ ${fixed(separate.fidelity.value)} on ${plural(separate.pairs, 'pair')}, at ${percent(burst.q)} error`, burst.source)
          : pending(1)],
      [bell ? tierOf(bell.source) : tierToCome(),
        'Link error lands on the gate; distilling helps only below a threshold.',
        bell
          ? evidence(`at ${errorRate(bell.point.q)}: raw ${fixed(bell.point.raw.f)}, distilled ${fixed(bell.point.distilled.f)}${stops == null ? '' : `; stops helping at ${percent(stops)}`}`, bell.source)
          : pending(2)],
      [algorithm ? tierOf(algorithm.result.source) : tierToCome(),
        'A split algorithm still returns its answer, at a price set by the link.',
        algorithm
          ? evidence(`${algorithm.name}, ${algorithm.n} qubits: one machine ${fixed(algorithm.result.mono[metric])}, split ${fixed(algorithm.result.dist[metric])} at ${errorRate(algorithm.result.q)} on ${plural(algorithm.result.pairs, 'pair')}`, algorithm.result.source)
          : pending(3)],
      ['Proven',
        'On a perfect link the split circuit equals the original.',
        proof
          ? evidence(`${proof.name}: lowest fidelity ${proof.proof.fidelity_min.toFixed(6)} over ${proof.proof.trials} random inputs`
            + (proof.proof.negative_control == null ? '' : `; ${fixed(proof.proof.negative_control)} with one correction removed`))
          : el('span', { class: 'pending' }, 'not run yet — step 4, Prove it', textButton('Go to step 4', () => view.goTo(3)))],
      ['Modeled',
        'Link noise: independent X and Z flips on one half of each pair, pair fidelity (1 − q)².',
        evidence('a model of the link, not of a device')],
      ['Modeled',
        `Pair budget: ${count(catalog.link.pair_rate_hz)} pairs per second, one at a time, gate time ignored.`,
        evidence(budget?.shots_per_second != null
          ? `about ${count(budget.kept_shots_per_second)} shots per second at ${plural(budget.raw_pairs_per_shot, 'raw pair')} per shot`
          : `rate from the ${catalog.link.source}`)],
      ['Not claimed', NOT_CLAIMED, evidence('outside what this page tests')],
    ];
  }

  function enter() {
    view.setProse(
      el('p', {}, el('strong', { text: 'Every claim on this page, with the kind of evidence behind it.' })),
      el('p', { text: 'Measured rows come from this session’s runs. Anything not run yet says so.' }));
    view.setReadouts([]);
    view.ledger.replaceChildren(
      el('table', {},
        el('caption', { class: 'sr-only', text: 'Claims, their evidence tier and the numbers from this session.' }),
        el('thead', {}, el('tr', {},
          el('th', { scope: 'col', text: 'Evidence' }),
          el('th', { scope: 'col', text: 'Claim' }),
          el('th', { scope: 'col', text: 'This session' }))),
        el('tbody', {}, rows().map(([tier, claim, proofCell]) => el('tr', {},
          tierCell(tier),
          el('td', { class: 'claim', text: claim }),
          el('td', { class: 'evidence' }, proofCell))))),
      el('p', { class: 'ledger-foot' },
        'Sources: teleported gates, Eisert et al. 2000; distillation, Deutsch et al. 1996; distributed trapped-ion computing, '
        + 'Main et al. 2025; IonQ interconnect announcement, 9 Oct 2026. ',
        el('strong', { text: 'This effort is supported by Qollab & IonQ.' })),
    );
  }

  return { enter };
}
