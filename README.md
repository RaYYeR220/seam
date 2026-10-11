# Seam

**[Run it on Qollab](https://qollab.xyz/u/rayyer/seam)** · **[Source on GitHub](https://github.com/RaYYeR220/seam)** · [Claims ledger](https://github.com/RaYYeR220/seam/blob/main/CLAIMS.md) · [Derivations](https://github.com/RaYYeR220/seam/blob/main/docs/HOW_IT_WORKS.md) · MIT

Seam splits a quantum circuit across two trapped-ion computers, Trap A and Trap B, joined by a photonic link. Every gate whose qubits sit on opposite sides of the cut is paid for with one shared Bell pair, as a teleported gate. Gates that share a control can ride one pair, and choosing them is solved exactly. The link can be noisy, and two raw pairs can be distilled into one better pair. You test five claims with real Qiskit circuits, and the page shows where the idea loses.

The question: on 9 October 2026, the day this hackathon started, IonQ [announced](https://ionq.com/news/ionq-demonstrates-world-first-quantum-memory-enhanced-interconnect-for-distributed-quantum-applications) a memory-enhanced photonic interconnect producing more than 1,000 entanglement events per second "for distributed quantum applications". What can such a link actually compute, and what does it cost in pairs, qubits and fidelity?

This effort is supported by Qollab & IonQ.

Theme: Quantum Unlocked (quantum networking)

<!-- VIDEO -->

## Try it in 60 seconds

1. Open the project on qollab.xyz, press **Run** and pick **Built-in simulator** (free, instant).
2. The page appears above the console, with its first experiment already measured.
3. Walk the five steps with **Next**.

| Step | Do this | You get |
|---|---|---|
| 1. One pair, one gate | Drag the four-stage scrubber, press Run | A CNOT between traps that never touch, and its measured truth table |
| 2. One pair, many gates | Set the fan-out, toggle "reuse the pair", Run | Pairs, qubits, fidelity: one shared pair against one per gate |
| 3. The weakest link | Move the link error, toggle Distill 2→1, Run or Sweep | Fidelity against link error; the region where distillation loses is shaded |
| 4. Split an algorithm | Pick an algorithm, move qubits across the seam or Auto cut, Run, then Sweep the link | One machine against the split one, the break-even link error, "Prove it", "Export QASM" |
| 5. Ledger | Read it | Each claim of your session tagged MEASURED, PROVEN, MODELED or NOT CLAIMED |

<!-- SCREENSHOT -->

Filled marks are measured (2,000 shots, 95% intervals); outlined marks are exact theory. The IonQ noise-model simulators (Aria, Forte) are also free but take one job per run: there the first job is measured and later results are exact statevector values, labeled as such. Everything runs in the browser (Pyodide, Qiskit 2.5).

## What you can check

Numbers are exact (statevector); the page measures the same quantities. Each command prints its number. Define once, in the repo root:

```bash
svc() { python -c 'import sys; from seam import service as s; print(getattr(s, sys.argv[1])(*sys.argv[2:]))' "$@"; }
```

**Where it works**

| Claim | Number | Step | Command |
|---|---|---|---|
| A CNOT across the link costs one pair and two classical bits | All four inputs give the right output with probability 1.000; data qubits match the original to 10⁻⁹ on 16 random entangled inputs | 1 | `svc exact '{"kind":"truth_table"}'`, `svc proof '{"algorithm":"grover"}'` |
| Gates sharing a control ride one pair | Fan-out to 4 targets, link error 0.05: 1 pair, 9 qubits, GHZ fidelity ≥ 0.900. One pair per gate: 4 pairs, 21 qubits, ≥ 0.643 | 2 | `svc exact '{"kind":"burst","k":4,"q":0.05}'` |
| The link's error lands on the gate | A Bell pair made by one teleported CNOT has fidelity (1−q)²: 0.9025 at q = 0.05 | 3 | `svc exact '{"kind":"remote_bell","qs":[0.05]}'` |
| Distillation buys fidelity with pairs | At q = 0.05: 0.9025 → 0.9837, keeping 82.8% of shots: 2.42 raw pairs per good pair | 3 | same |
| Bursts are scheduled exactly | Phase estimation, Grover: 8 crossing gates, 2 pairs. QAOA: 4 gates, 2 pairs | 4 | `svc plan '{"algorithm":"grover"}'` |

**Where it loses**

| Claim | Number | Step | Command |
|---|---|---|---|
| Distillation makes a bad link worse | The pair: beyond q = 0.2929 (raw fidelity 1/2). The answer, earlier: 0.2282 for GHZ, Bernstein–Vazirani and phase estimation; Grover 0.2973; QAOA 0.2958 | 3, 4 | `svc exact '{"kind":"algorithm_sweep","algorithm":"ghz","qs":[0.2,0.25]}'` |
| A noisy link sinks the algorithm | Split Grover succeeds under half the time beyond q = 0.1161 (0.1782 distilled). Phase estimation: 0.382, and distillation moves it the wrong way, to 0.327 | 4 | `svc exact '{"kind":"algorithm_sweep","algorithm":"grover","qs":[0.05]}'` |
| Some cuts are nearly free; reuse buys nothing | GHZ, Bernstein–Vazirani: 1 crossing gate, 1 pair, reuse on or off | 4 | `python -m seam ghz --q 0.05` |
| The split machine never beats one machine that fits the circuit | Equal at q = 0; lower at all 100 grid points in 0 < q ≤ 0.5, five circuits, raw and distilled. Grover, q = 0.05: 0.781 on 3 qubits; 0.644 on 11; 0.757 on 19 distilled, with 68.6% of shots kept | 4 | `python -m seam grover --q 0.05 --distill` |
| Step 1's truth table cannot prove the gate | Delete the phase correction: all four rows still read 1.000. Only the statevector proof catches it (mean fidelity 0.62) | 1 | [CLAIMS.md](https://github.com/RaYYeR220/seam/blob/main/CLAIMS.md), N1 |

The break-even bar is max(classical guess, 1/2). Against the bare classical guess no catalog circuit loses for any q ≤ 0.5 (Grover at q = 0.5: 0.219 against 0.125), because only the link is noisy.

**The announced link, in this model.** The preprint behind the announcement reports 1.03(1) kHz at 87.9(7)% fidelity between a ¹³⁸Ba⁺ ion and a silicon-vacancy memory. If that were our ion–ion pair fidelity (q = 0.0625), split Grover would succeed with probability 0.614 instead of 0.781, or 0.743 distilled at 157 kept shots per second. Modeled, not measured.

## How it works

**The teleported gate.** Control `c` and link ion `a` sit in Trap A; link ion `b` and target `t` in Trap B.

```
h a;  cx a,b    share a Bell pair over the link
cx c,a          fold the control into the pair               (local to A)
cx a,b          classical bit 1: measure a, flip b if 1      (drawn as a gate)
cx b,t          the gate itself, driven by b instead of c    (local to B)
h b             unfold                                       (local to B)
cz b,c          classical bit 2: measure b, phase-flip c if 1
```

After line 3, `b` is a Z-basis copy of `c`: $\alpha|0\rangle_c|0\rangle_b + \beta|1\rangle_c|1\rangle_b$. After line 6 the link ions factor out and the data qubits hold what a direct CNOT would have produced.

**Bursts.** Between lines 3 and 5 any number of gates can be driven from `b`, provided nothing acts on `c` that is not diagonal in Z. Phase gates, `cz`, and `cx` with `c` as control keep the copy faithful; `h`, `x`, `rx`, `ry` or a `cx` onto `c` change `c` but not its copy, and end the burst.

**Scheduling.** Cut each qubit's timeline at its non-diagonal gates. A crossing `cx` must be driven from its control's segment; a crossing `cz` can be driven from either end, so it is an edge between a segment in A and one in B. The fewest pairs is a minimum vertex cover of that bipartite graph, solved exactly through König's theorem. The cut itself is found by exhaustive search, minimizing pairs, not crossing gates.

**Link noise.** After a pair is made, `b` suffers an X flip with probability q and, independently, a Z flip with probability q, each driven by its own environment qubit: two per raw pair, never measured. The pair is Bell-diagonal with fidelity $(1-q)^2$.

**Distillation.** Two raw pairs are rotated (`rx(π/2)` in A, `rx(−π/2)` in B), a CNOT on each side copies bit flips onto the second pair, and that pair is measured at the end of the circuit. A shot is kept when its two bits agree. With $f = 2q(1-q)$ the kept fraction is $N = (1-f)^2 + f^2$ and the kept pair has fidelity $((1-q)^4 + q^4)/N \approx 1 - 6q^2$.

**One circuit.** All of this is unitary gates with measurements at the very end: no mid-circuit measurement, no feed-forward, no reset. Each circuit is one job in the basis `rx, ry, rz, h, x, cx` on at most 22 qubits, which also fits IonQ's one-job rule; the opening truth table packs all four inputs into one 16-qubit circuit.

| Circuit, default size | Qubits | Crossing gates | Pairs, no reuse | Pairs, reuse | Total qubits, clean | Noisy | Noisy + distilled |
|---|---|---|---|---|---|---|---|
| GHZ state | 6 | 1 | 1 | 1 | 8 | 10 | 14 |
| Bernstein–Vazirani, secret 10110 | 6 | 1 | 1 | 1 | 8 | 10 | 14 |
| Phase estimation, phase 5/8 | 4 | 8 | 8 | 2 | 8 | 12 | 20 |
| Grover, marked 101, one iteration | 3 | 8 | 8 | 2 | 7 | 11 | 19 |
| QAOA MaxCut on a ring | 4 | 4 | 4 | 2 | 8 | 12 | 20 |

Total = data + 2 link ions per raw pair + 2 environment qubits per raw pair on a noisy link; distillation doubles the raw pairs. Each row: `svc plan '{"algorithm":"<id>"}'`, ids `ghz`, `bv`, `qft_phase`, `grover`, `qaoa_ring`. Derivations: [docs/HOW_IT_WORKS.md](https://github.com/RaYYeR220/seam/blob/main/docs/HOW_IT_WORKS.md).

## Evidence

`python -m pytest -q` reports `1551 passed` in about 10 seconds on a laptop.

| File | Tests | What it proves |
|---|---|---|
| `test_equivalence.py` | 708 | On a perfect link the split circuit equals the original on the data qubits (fidelity > 1 − 10⁻⁹): 480 random cases, 146 catalog cases over every algorithm and size, 40 refereed by Qiskit's own simulator. 40 audits that only pair generation and the two classical bits cross the link |
| `test_schedule.py` | 258 | Schedules are legal (120 random circuits); pair counts equal a brute force over every choice of driving end (120) |
| `test_service.py` | 144 | Every catalog size plans and proves; 89 malformed requests return an error, never an exception |
| `test_experiments.py` | 119 | Interval coverage: 15 experiments, 40 seeded draws of 2,000 shots; each kind of 95% interval covers the exact value at least 90% of the time, none misses by five standard errors. Circuits on Qiskit's BasicSimulator match the exact prediction |
| `test_partition.py` | 98 | The cut search equals brute force on 80 cases |
| `test_algorithms.py` | 71 | Catalog circuits return their stated answers |
| `test_sim.py` | 58 | The statevector kernel agrees with Qiskit to 10⁻¹² |
| `test_link.py` | 45 | The raw pair is the stated Bell-diagonal state; distillation matches the DEJMPS map, derived independently |
| `test_lower.py` | 38 | Lowering to one-qubit gates, `cx` and `cz` preserves the unitary |
| `test_negative_controls.py` | 9 | Broken circuits must fail: drop either correction, or merge a burst across `h`, `rx`, `x` or a `cx` onto the control |
| `test_cli.py` | 3 | The command line |

**On the real runtime (11 October 2026).** On Qollab's built-in simulator the page boots, measures the step-1 truth table and runs every step; phase estimation at 5% link error measured 1.00 on one machine against 0.93 split (95% interval 0.92–0.94), the exact value being 0.926. On the IonQ Forte 1 noise-model simulator the opening job, one 16-qubit circuit with 2,000 shots, took 6 s of circuit time and returned the right output for all four inputs (lowest row: 95% interval 0.997–1.000); the next Run was refused, as IonQ's one-job rule says it must be, and the page switched to exact values and said so.

One thing looks odd there and is not: on an IonQ backend Qollab's **Probabilities** panel lists all 16 qubits, link ions included, so the distribution is spread almost evenly over 256 outcomes. Those extra bits are the two classical bits of each teleported gate. They are uniformly random by construction; if they were not, they would leak the control qubit. The page reads only the data qubits.

Every claim, with its tier and command, is in [CLAIMS.md](https://github.com/RaYYeR220/seam/blob/main/CLAIMS.md).

## Honest limits

- **The classical channel is not simulated.** The two classical bits are drawn as gates (deferred measurement). The statistics are the same; timing and the wire are not modeled.
- **Noise is on the link only**, and in one form: independent X and Z flips on one half of each pair. On the built-in simulator local gates are perfect; on a noisy backend device noise comes on top, and the split circuit is the larger one.
- **The pair-rate budget is a model built on a press-release figure.** It assumes 1,000 usable ion–ion pairs per second, one at a time; the published figure is ion–memory entanglement. Gate time and memory decoherence are ignored, and a shot rejected by distillation wastes all its pairs.
- **Two modules only**, 22 qubits per circuit, 12 data qubits for the cut search. Every pair uses fresh link ions.
- **Target-side sharing is not implemented.** Gates that share a target cost one pair each; "exact" means exact under the burst rule above.
- **No speed-up is claimed.** Splitting buys qubits one trap does not have. It never buys fidelity.

## Files

```
index.html         page fragment that Qollab mounts
main.css           styles
main.js            entry: starts the engine and the page
ui/
  app.js           step navigation, backend notice
  bridge.js        Python and backend calls, exact fallback
  stage.js         the two-trap figure
  scene.js         engine JSON to drawable wires and gates
  charts.js        charts with hidden data tables
  controls.js      sliders, steppers, toggles, run buttons
  result.js        result panels
  dom.js           DOM and SVG helpers
  format.js        number formatting
  link.js          the announced link's fidelity, as a link error
  palette.js       colors
  step-gate.js     step 1
  step-burst.js    step 2
  step-link.js     step 3
  step-split.js    step 4
  step-ledger.js   step 5
seam/
  service.py       JSON front door, all the page imports
  algorithms.py    five catalog circuits and their answers
  lower.py         lowering to one-qubit gates, cx, cz
  partition.py     exhaustive search for the cheapest cut
  schedule.py      crossing gates to bursts (vertex cover)
  link.py          Bell pairs, link noise, distillation
  build.py         the distributed circuit, drawing data
  verify.py        equivalence proof, negative control
  experiments.py   experiments, exact predictions, intervals
  plan.py          one request: circuit, cut, bursts, costs
  budget.py        the modeled pair-rate budget
  sim.py           statevector kernel
  __main__.py      command line
  __init__.py      package marker
tests/             the 11 files above, helpers.py, conftest.py
docs/
  HOW_IT_WORKS.md  derivations
CLAIMS.md          claims ledger
requirements.txt   runtime notes for Qollab
requirements-dev.txt   Qiskit and pytest for local runs
LICENSE            MIT
```

## Run it locally

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m seam grover --q 0.05
```

The last command plans the cut, runs both circuits on Qiskit's BasicSimulator and prints qubits, depth, measured success and the exact prediction, for one machine and for the split one. Options: `--distill`, `--n`, `--shots`, `--seed`. Tested with Python 3.13, Qiskit 2.5.2, NumPy 2.5.4.

## Extend it

1. **Split your own circuit.** Any unitary Qiskit circuit works from Python; see the ten-line example in [docs/HOW_IT_WORKS.md](https://github.com/RaYYeR220/seam/blob/main/docs/HOW_IT_WORKS.md), section 9. To put it on the page, add a builder and an `Algorithm` entry in `seam/algorithms.py`; the catalog-wide tests pick it up.
2. **Add target-side sharing.** Gates that share a target can ride one pair in the X basis. Extend `Gate.diagonal_on` and the scheduler; the brute-force test and the 708 equivalence cases tell you whether it is right.
3. **Use a real classical channel.** In `build.distribute`, replace the two `classical` operations with a measurement and a conditional gate, and run on a backend with mid-circuit measurement.

## References

- J. Eisert, K. Jacobs, P. Papadopoulos, M. B. Plenio, "Optimal local implementation of nonlocal quantum gates", Phys. Rev. A 62, 052317 (2000), doi:10.1103/PhysRevA.62.052317.
- C. H. Bennett et al., "Purification of noisy entanglement and faithful teleportation via noisy channels", Phys. Rev. Lett. 76, 722 (1996), doi:10.1103/PhysRevLett.76.722.
- D. Deutsch et al., "Quantum privacy amplification and the security of quantum cryptography over noisy channels", Phys. Rev. Lett. 77, 2818 (1996), doi:10.1103/PhysRevLett.77.2818. The DEJMPS protocol.
- A. Wu et al., "AutoComm: a framework for enabling efficient communication in distributed quantum programs", MICRO 2022, arXiv:2207.11674. Prior work on bursts.
- D. Main et al., "Distributed quantum computing across an optical network link", Nature 638, 383–388 (2025), doi:10.1038/s41586-024-08404-x.
- IonQ, "IonQ Demonstrates World-First Quantum Memory-Enhanced Interconnect for Distributed Quantum Applications", 9 October 2026 (linked above); preprint arXiv:2610.10705.

## Built during the hackathon window

Seam was written from scratch between 9 and 11 October 2026 for the Qollab x IonQ Global Quantum Hackathon. It contains no pre-existing code. Libraries: Qiskit and NumPy. Fonts: Old Standard TT, Alegreya Sans and Alegreya Sans SC (Google Fonts, SIL Open Font License). License: MIT.
