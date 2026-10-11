import { el } from './dom.js';

let nextId = 0;
const uniqueId = (stem) => `seam-${stem}-${(nextId += 1)}`;

/** A labelled slot of the control row. */
export function field(label, body, readout = null) {
  return el('div', { class: 'control' },
    el('div', { class: 'control-label' }, typeof label === 'string' ? el('span', { text: label }) : label, readout),
    el('div', { class: 'control-body' }, body));
}

/**
 * A range input with its current value shown next to the label. `mark` puts
 * a small diamond on the track at a value worth pointing out.
 */
export function slider({ label, min, max, step, value, format, describe = format, onInput, onChange, demo, mark }) {
  const id = uniqueId('range');
  const readout = el('output', { for: id, text: format(value) });
  const input = el('input', {
    id,
    type: 'range',
    min,
    max,
    step,
    value,
    'data-demo': demo,
    'aria-valuetext': describe(value),
    oninput: () => {
      const current = Number(input.value);
      readout.textContent = format(current);
      input.setAttribute('aria-valuetext', describe(current));
      onInput?.(current);
    },
    onchange: () => onChange?.(Number(input.value)),
  });
  const track = el('span', { class: 'range' }, input, mark ? el('i', {
    class: 'range-mark',
    title: mark.title,
    'aria-hidden': 'true',
    style: `--at:${(mark.value - min) / (max - min)}`,
  }) : null);
  return field(el('label', { for: id, text: label }), track, readout);
}

export function checkbox({ label, checked, onChange, demo }) {
  const input = el('input', { type: 'checkbox', 'data-demo': demo, onchange: () => onChange(input.checked) });
  input.checked = checked;
  return el('div', { class: 'control' },
    el('div', { class: 'control-body' }, el('label', { class: 'check' }, input, label)));
}

export function select({ label, options, value, onChange, demo }) {
  const id = uniqueId('select');
  const input = el('select', { id, 'data-demo': demo, onchange: () => onChange(input.value) },
    options.map((option) => el('option', { value: option.value, text: option.label })));
  input.value = value;
  return field(el('label', { for: id, text: label }), input);
}

/**
 * A whole number moved one step at a time with two buttons. `update` changes
 * the value or its limits without rebuilding the control, which keeps focus.
 */
export function stepper({ label, unit, onChange, demo = {}, ...initial }) {
  const range = { min: initial.min, max: initial.max, value: initial.value };
  const readout = el('output');
  const button = (delta, name, text, demoName) => el('button', {
    type: 'button',
    'aria-label': `One ${unit} ${name}`,
    'data-demo': demoName,
    onclick: () => {
      const next = range.value + delta;
      if (next >= range.min && next <= range.max) onChange(next);
    },
    text,
  });
  const fewer = button(-1, 'fewer', '−', demo.minus);
  const more = button(1, 'more', '+', demo.plus);
  const group = el('div', { class: 'stepper', role: 'group' }, fewer, readout, more);

  function update(next) {
    Object.assign(range, next);
    readout.textContent = range.value;
    group.setAttribute('aria-label', `${label}: ${range.value}`);
    fewer.setAttribute('aria-disabled', String(range.value <= range.min));
    more.setAttribute('aria-disabled', String(range.value >= range.max));
  }
  update({});
  return { node: field(label, group), update };
}

/** One of a few named options, as a row of radio buttons; `select(value)` changes it from code. */
export function choice({ label, options, value, onChange }) {
  const name = uniqueId('choice');
  const inputs = options.map((option) => {
    const input = el('input', { type: 'radio', name, value: option.value, onchange: () => onChange(option.value) });
    input.checked = option.value === value;
    return input;
  });
  const node = el('div', { class: 'control' },
    el('div', { class: 'control-label', id: name }, el('span', { text: label })),
    el('div', { class: 'control-body choice', role: 'radiogroup', 'aria-labelledby': name },
      options.map((option, index) => el('label', { 'data-demo': option.demo },
        inputs[index],
        option.numeral ? el('span', { class: 'numeral', text: option.numeral }) : null,
        option.label))));
  return {
    node,
    select(next) {
      inputs.forEach((input, index) => { input.checked = options[index].value === next; });
    },
  };
}

export function actions(...buttons) {
  return el('div', { class: 'actions' }, buttons);
}

export function textButton(label, onClick, demo) {
  return el('button', { type: 'button', class: 'link-button', 'data-demo': demo, onclick: onClick, text: label });
}

export function runButton(onClick, label = 'Run') {
  return el('button', { type: 'button', class: 'run', 'data-demo': 'run', onclick: onClick, text: label });
}

/** Shows a working label on the button while the task runs and ignores repeat presses. */
export async function whileBusy(button, workingLabel, task) {
  if (button.getAttribute('aria-busy') === 'true') return undefined;
  const label = button.textContent;
  button.setAttribute('aria-busy', 'true');
  button.textContent = workingLabel;
  try {
    return await task();
  } finally {
    button.removeAttribute('aria-busy');
    button.textContent = label;
  }
}
