import * as service from 'seam.service';
import { createApp } from './ui/app.js';
import { createBridge } from './ui/bridge.js';

function whenMounted(id) {
  return new Promise((resolve) => {
    const look = () => {
      const node = document.getElementById(id);
      if (node) resolve(node);
      else setTimeout(look, 50);
    };
    look();
  });
}

/**
 * Reads `#step=3&q=0.15&distill=1&run=1`, a development aid for opening the
 * page in a given state. Inside Qollab the hash is empty.
 */
function requestedState() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const step = Number.parseInt(params.get('step') ?? '1', 10);
  const q = Number.parseFloat(params.get('q'));
  return {
    step: Number.isInteger(step) && step >= 1 && step <= 5 ? step - 1 : 0,
    run: params.get('run') === '1',
    settings: {
      q: Number.isFinite(q) ? q : null,
      distill: params.has('distill') ? params.get('distill') === '1' : null,
    },
  };
}

const root = await whenMounted('seam');
const bridge = createBridge(service, typeof backend === 'undefined' ? null : backend);
const app = createApp(root, bridge);

const catalog = await bridge.catalog();
if (catalog.error) app.fail(catalog.error);
else await app.start(catalog, requestedState());

await new Promise(() => {});
