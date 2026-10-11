import { afterPaint } from './dom.js';

const SHOTS = 2000;

function backendName(backend) {
  try {
    const name = backend.name ?? backend.backend_name;
    const text = typeof name === 'function' ? name.call(backend) : name;
    return text ? String(text) : 'the selected backend';
  } catch {
    return 'the selected backend';
  }
}

function plainCounts(counts) {
  const table = counts && typeof counts.toJs === 'function' ? counts.toJs() : counts;
  const entries = table instanceof Map ? [...table] : Object.entries(table ?? {});
  return Object.fromEntries(entries.map(([bits, n]) => [String(bits), Number(n)]));
}

function describeFailure(error) {
  const text = String(error?.message ?? error).trim().split('\n').pop();
  return text || 'The engine stopped without saying why.';
}

/**
 * Talks to the Python engine and to the quantum backend.
 *
 * Every engine call resolves to parsed JSON; failures come back as
 * `{ error }` so callers have one shape to handle. Once the backend turns a
 * job down, experiments are computed exactly for the rest of the run.
 */
export function createBridge(service, backend) {
  const listeners = [];
  const state = {
    backend: backend ? backendName(backend) : null,
    shots: SHOTS,
    sampling: Boolean(backend),
    jobsDone: 0,
  };

  async function call(name, ...args) {
    await afterPaint();
    try {
      return JSON.parse(String(await service[name].callPromising(...args)));
    } catch (error) {
      return { error: describeFailure(error) };
    }
  }

  const ask = (name) => (options) => call(name, JSON.stringify(options));

  async function sample(cid, shots) {
    const circuit = await service.circuit.callPromising(cid);
    const job = await backend.run(circuit, { shots });
    const result = await job.result();
    return plainCounts(result.get_counts());
  }

  function stopSampling() {
    state.sampling = false;
    for (const listener of listeners) listener(mode());
  }

  /** Runs an experiment on the backend, or exactly when the backend takes no more jobs. */
  async function measure(spec) {
    if (!state.sampling) return ask('exact')(spec);
    const setup = await ask('experiment')({ ...spec, shots: state.shots });
    if (setup.error) return setup;
    const counts = {};
    try {
      for (const { cid } of setup.circuits) {
        counts[cid] = await sample(cid, setup.shots);
        state.jobsDone += 1;
      }
    } catch {
      stopSampling();
      return ask('exact')(spec);
    }
    return call('ingest', setup.id, JSON.stringify(counts), setup.shots);
  }

  function mode() {
    return { ...state };
  }

  return {
    catalog: () => call('catalog'),
    plan: ask('plan'),
    proof: ask('proof'),
    exact: ask('exact'),
    exportQasm: ask('export_qasm'),
    measure,
    mode,
    onModeChange: (listener) => { listeners.push(listener); },
  };
}
