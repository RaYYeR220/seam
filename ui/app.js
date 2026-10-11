import { announceBusyWith } from './controls.js';
import { el } from './dom.js';
import { count } from './format.js';
import { createStage } from './stage.js';
import { gateStep } from './step-gate.js';
import { burstStep } from './step-burst.js';
import { linkStep } from './step-link.js';
import { splitStep } from './step-split.js';
import { ledgerStep } from './step-ledger.js';

/** One entry per navigator item in index.html, in the same order. */
const STEPS = [
  { make: gateStep },
  { make: burstStep },
  { make: linkStep },
  { make: splitStep },
  { make: ledgerStep, isLedger: true },
];

function chipText(mode) {
  if (mode.sampling) return `measured on ${mode.backend} · ${count(mode.shots)} shots`;
  if (mode.jobsDone > 0) return 'this backend takes one job per run — later results are exact, not sampled';
  return 'no backend answered — results are exact, not sampled';
}

/**
 * The page around the steps: navigation, the rail, the plate and the regions
 * each step fills. The first step is drawn at once; the others open when the
 * engine has answered with its catalog.
 */
export function createApp(root, bridge) {
  const find = (name) => root.querySelector(`#seam-${name}`);
  const nodes = Object.fromEntries(
    ['steps', 'chip', 'back', 'next', 'sheet', 'title', 'prose', 'rail-action', 'readouts', 'caption', 'plate',
      'controls', 'result', 'ledger', 'live'].map((name) => [name, find(name)]),
  );
  const made = new Map();
  let current = -1;
  let ready = false;

  const view = {
    bridge,
    catalog: null,
    stage: createStage(nodes.plate),
    session: {},
    controls: nodes.controls,
    result: nodes.result,
    ledger: nodes.ledger,
    setProse: (...paragraphs) => nodes.prose.replaceChildren(...paragraphs),
    setRailAction: (node) => nodes['rail-action'].replaceChildren(node),
    setCaption: (text) => { nodes.caption.textContent = text; },
    setReadouts(items) {
      nodes.readouts.replaceChildren(...items.map((item) => el('div', {},
        el('dt', {}, item.label, item.note ? el('small', { text: item.note }) : null),
        el('dd', { class: item.over ? 'over' : null, text: item.value }))));
    },
    announce: (text) => { nodes.live.textContent = text; },
    isShowing: (step) => made.get(current) === step,
    goTo: (index) => go(index),
  };

  function stepAt(index) {
    if (!made.has(index)) made.set(index, STEPS[index].make(view));
    return made.get(index);
  }

  const links = [...nodes.steps.querySelectorAll('.step-link')];
  const titleOf = (index) => links[index].querySelector('.title').textContent;
  links.forEach((link, index) => link.addEventListener('click', () => go(index)));

  function showNavigation() {
    links.forEach((link, index) => {
      if (index === current) link.setAttribute('aria-current', 'step');
      else link.removeAttribute('aria-current');
      link.setAttribute('aria-disabled', String(!ready && index !== current));
    });
    nodes.back.setAttribute('aria-disabled', String(!ready || current === 0));
    nodes.next.setAttribute('aria-disabled', String(!ready || current === STEPS.length - 1));
  }

  function go(index) {
    if (index < 0 || index >= STEPS.length || index === current) return;
    if (!ready && index !== 0) return;
    const orphaned = nodes.sheet.contains(document.activeElement);
    current = index;
    showNavigation();
    const isLedger = Boolean(STEPS[index].isLedger);
    nodes.sheet.classList.toggle('is-ledger', isLedger);
    nodes.ledger.hidden = !isLedger;
    nodes.title.textContent = titleOf(index);
    nodes['rail-action'].replaceChildren();
    stepAt(index).enter();
    if (orphaned) nodes.title.focus();
    view.announce(`Step ${index + 1} of ${STEPS.length}: ${titleOf(index)}.`);
  }

  nodes.back.addEventListener('click', () => go(current - 1));
  nodes.next.addEventListener('click', () => go(current + 1));
  nodes.steps.addEventListener('keydown', (event) => {
    const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!delta) return;
    event.preventDefault();
    go(current + delta);
    links[current].focus();
  });

  announceBusyWith(view.announce);
  const showMode = (mode) => { nodes.chip.textContent = chipText(mode); };
  bridge.onModeChange((mode) => {
    showMode(mode);
    view.announce(chipText(mode));
  });

  go(0);

  return {
    /**
     * Takes the boot measurement, opens the other steps, then honours a
     * requested step and its link settings. Asking to run the ledger runs
     * every step before it.
     */
    async start(catalog, { step = 0, run = false, settings = {} } = {}) {
      view.catalog = catalog;
      await stepAt(0).run();
      showMode(bridge.mode());
      ready = true;
      showNavigation();
      if (step === 0) return;
      const target = stepAt(step);
      target.preset?.(settings);
      const before = run && STEPS[step].isLedger ? STEPS.map((_, index) => index).slice(1, step) : [];
      for (const index of before) {
        go(index);
        await stepAt(index).run();
        await stepAt(index).prove?.();
      }
      go(step);
      if (run) await target.run?.();
    },
  };
}
