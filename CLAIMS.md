# Claims ledger

Every public claim made in the README or on the page, one row each, with the evidence behind it.

| Tier | Meaning |
|---|---|
| REPRODUCIBLE | A command anyone can run. The command is given. |
| EXACT | A statevector or density-matrix computation with no sampling. The function is given. |
| MODELED | True inside a stated model. The assumptions are given. |
| NOT CLAIMED | Something a reader might assume that we do not assert. |

The page's own ledger (step 5) uses MEASURED for values sampled in your session and PROVEN for the statevector proof; every MEASURED value has an EXACT counterpart here.

All commands run from the repository root after `pip install -r requirements-dev.txt`. Rows that say `svc` use this helper:

```bash
svc() { python -c 'import sys; from seam import service as s; print(getattr(s, sys.argv[1])(*sys.argv[2:]))' "$@"; }
```

Figures were produced on 11 October 2026 with Python 3.13, Qiskit 2.5.2 and NumPy 2.5.4. Link error is written q. "Default size" means the size each catalog circuit opens with.

## The teleported gate (step 1)

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| G1 | A CNOT between two traps is built from one Bell pair, two link ions and two classical bits. On a perfect link all four basis inputs give the expected output with probability 1.000, in one 16-qubit circuit. | EXACT | `seam.experiments.exact`: `svc exact '{"kind":"truth_table"}'` |
| G2 | On a perfect link the split circuit acts on the data qubits exactly like the original (fidelity > 1 − 10⁻⁹): 240 random circuits and every catalog circuit at every size, with and without pair reuse. | REPRODUCIBLE | `python -m pytest -q tests/test_equivalence.py` (708 passed) |
| G3 | "Prove it" on the page: minimum fidelity 1 over 16 random entangled inputs, and a negative control (one phase correction removed) that must fail. Negative-control mean fidelity at default size: GHZ 0.508, Bernstein–Vazirani 0.540, phase estimation 0.506, Grover 0.530, QAOA 0.545. | EXACT | `seam.verify.prove`: `svc proof '{"algorithm":"grover"}'` |
| G4 | Only pair generation and the two classical bits cross the link; every other operation is local to one trap. | REPRODUCIBLE | `python -m pytest -q tests/test_equivalence.py -k cross_the_link` (40 passed) |
| G5 | Both corrections are needed. For one teleported CNOT, mean fidelity over 16 random inputs is 0.703 without the bit-flip correction and 0.623 without the phase correction. | REPRODUCIBLE | Snippet C5; `python -m pytest -q tests/test_negative_controls.py` (9 passed) |
| G6 | With link error q the truth table reads 1 − q in every row (0.95 at q = 0.05): it sees bit flips only. | EXACT | `svc exact '{"kind":"truth_table","q":0.05}'` |

## Bursts and scheduling (steps 2 and 4)

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| B1 | A control fanning out to k targets rides one pair. At q = 0.05 and k = 4: one pair, 9 qubits, GHZ fidelity bound 0.900; one pair per gate, 4 pairs, 21 qubits, bound 0.643. For k = 2 and 3 the per-gate bound is 0.808 and 0.722. | EXACT | `svc exact '{"kind":"burst","k":4,"q":0.05}'` |
| B2 | With one shared pair the error does not grow with k: P(all equal) = 1 − q and X-parity = 1 − 2q for k = 1 to 4. With one pair per gate they are (1 − q)ᵏ and (1 − 2q)ᵏ. | REPRODUCIBLE | `python -m pytest -q tests/test_experiments.py -k burst` (20 passed) |
| B3 | A burst cannot span a gate on its control that is not diagonal in Z. Counter-example `cx(0,1); h(0); cx(0,1)`: with two pairs the fidelity is 1; forced onto one pair it is 0.468 on average (0.286 to 0.878). | REPRODUCIBLE | Snippet C2; `python -m pytest -q tests/test_negative_controls.py -k merging` (5 passed) |
| B4 | The schedule uses the fewest pairs the burst rule allows: equal to a brute force over every choice of driving end on 120 random circuits. | REPRODUCIBLE | `python -m pytest -q tests/test_schedule.py -k optimal` (120 passed) |
| B5 | "Auto cut" is the cheapest balanced cut, found by exhaustive search; best and worst costs equal brute force on 80 cases. | REPRODUCIBLE | `python -m pytest -q tests/test_partition.py -k optimal` (80 passed) |
| B6 | At default size: GHZ and Bernstein–Vazirani have 1 crossing gate and need 1 pair; phase estimation and Grover have 8 and need 2; QAOA has 4 and needs 2. Total qubits (clean / noisy / noisy and distilled): 8/10/14, 8/10/14, 8/12/20, 7/11/19, 8/12/20. | EXACT | `seam.plan.make_plan`: `svc plan '{"algorithm":"qft_phase"}'`, fields `cut` and `qubits` |

## The link (step 3)

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| K1 | A raw pair is Bell-diagonal with weights (1−q)², q(1−q), q(1−q), q² on Φ⁺, Ψ⁺, Φ⁻, Ψ⁻. Its fidelity is (1−q)². | REPRODUCIBLE | `python -m pytest -q tests/test_link.py` (45 passed) |
| K2 | A Bell pair made across the link by one teleported CNOT has fidelity exactly (1−q)²: 0.9025 at q = 0.05. | EXACT | `svc exact '{"kind":"remote_bell","qs":[0.05]}'` |
| K3 | One round of 2→1 distillation keeps a fraction N = (1−f)² + f² of shots, f = 2q(1−q), and yields fidelity ((1−q)⁴ + q⁴)/N. At q = 0.05: 0.9837, 82.8% kept, 2.42 raw pairs per good pair. | EXACT | `seam.link.distilled`; the statevector circuits agree with the formulas to 5 × 10⁻¹³ on a 101-point grid (snippet C3) |
| K4 | Distillation lowers the pair fidelity beyond q = 1 − 1/√2 = 0.2929, where the raw fidelity is 1/2. | EXACT | `svc exact '{"kind":"remote_bell","qs":[0.29,0.3]}'`, field `thresholds` |
| K5 | Exact curves for any q come from one statevector run with the environment qubits in superposition; this equals an explicit average over Pauli errors to 10⁻¹². | REPRODUCIBLE | `python -m pytest -q tests/test_experiments.py -k explicit_mixture` (10 passed) |

## Algorithms (step 4)

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| A1 | On a perfect link the split machine reproduces the one-machine output distribution (Hellinger fidelity 1 to 10⁻⁹), with or without distillation. | REPRODUCIBLE | `python -m pytest -q tests/test_experiments.py -k perfect_link` (5 passed) |
| A2 | At q = 0.05, success raw / distilled (shots kept): GHZ 0.950 / 0.989 (82.8%), Bernstein–Vazirani 0.950 / 0.989 (82.8%), phase estimation 0.926 / 0.984 (68.6%), Grover 0.644 / 0.757 (68.6%) against 0.781 on one machine. QAOA, Hellinger fidelity: 0.990 / 0.9996 (68.6%). | EXACT | `svc exact '{"kind":"algorithm","algorithm":"grover","q":0.05,"distill":true}'` |
| A3 | Measured on Qiskit's BasicSimulator, 2,000 shots, seed 7: split Grover at q = 0.05 succeeds 0.6530 (exact 0.6443); one machine 0.7860 (exact 0.7812). | REPRODUCIBLE | `python -m seam grover --q 0.05` |
| A4 | Splitting costs qubits and depth. Grover: 3 qubits, depth 25 on one machine; 11 qubits, depth 32 on a noisy link; 19 qubits, depth 34 with distillation. | REPRODUCIBLE | `python -m seam grover --q 0.05 --distill` |
| A5 | Reported 95% intervals do their job: over 40 seeded draws of 2,000 shots for each of 15 experiments, every kind of interval covers the exact value at least 90% of the time and none misses by five standard errors. | REPRODUCIBLE | `python -m pytest -q tests/test_experiments.py -k sampled_counts` (15 passed) |
| A6 | Every circuit sent to a backend has at most 22 qubits, uses only `rx, ry, rz, h, x, cx`, and ends with measurements only. | REPRODUCIBLE | `python -m pytest -q tests/test_experiments.py -k backend_circuits` (15 passed) |
| A7 | "Export QASM" gives OpenQASM 2 of the split circuit with every wire named; Qiskit parses it back. | REPRODUCIBLE | `svc export_qasm '{"algorithm":"grover","q":0.05,"distill":true}'` |

## Where it loses

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| L1 | The split machine never beats one machine that fits the circuit. Equal at q = 0. At each of 100 grid points in 0 < q ≤ 0.5, for all five circuits, raw and distilled, the split result is strictly lower. | EXACT | Snippet C4 |
| L2 | A noisy link sinks the algorithm. Split Grover succeeds less than half the time beyond q = 0.1161 (0.1782 with distillation); phase estimation beyond q = 0.382 (0.327 with distillation). | EXACT | `svc exact '{"kind":"algorithm_sweep","algorithm":"grover","qs":[0.05]}'`, field `break_even_q` |
| L3 | Distillation stops helping the answer at q = 0.2282 for GHZ, Bernstein–Vazirani and phase estimation, 0.2973 for Grover, 0.2958 for QAOA. | EXACT | Same command, field `distill_stops_helping_q`; all five in snippet C4 |
| L4 | Where distillation helps it still costs. Grover at q = 0.05: 11 → 19 qubits, 2 → 4 raw pairs per shot, 68.6% of shots kept. | EXACT | `svc exact '{"kind":"algorithm","algorithm":"grover","q":0.05,"distill":true}'` |
| L5 | Some cuts are nearly free, so pair reuse buys nothing: GHZ and Bernstein–Vazirani need 1 pair with reuse on or off. | EXACT | `python -m seam ghz --q 0.05`, `python -m seam bv --q 0.05` |

## Negative results we volunteer

| ID | Claim | Tier | Evidence |
|---|---|---|---|
| N1 | Step 1's truth table cannot prove the gate. Remove the phase correction `cz(b, c)` and all four rows still read 1.000, although the gate is wrong on superpositions (G5). The proof button exists for this reason. | REPRODUCIBLE | Snippet C1 |
| N2 | Distillation hurts the answer before it hurts the pair (0.2282 against 0.2929). Its rotation turns phase errors, which the success probability of GHZ, Bernstein–Vazirani and phase estimation does not see, into bit flips, which it does. | EXACT | L3 and K4 |
| N3 | For phase estimation distillation moves the break-even the wrong way, from q = 0.382 to 0.327. | EXACT | `svc exact '{"kind":"algorithm_sweep","algorithm":"qft_phase","qs":[0.3,0.35]}'` |
| N4 | The fidelity shown in step 2 is a lower bound, max(0, P(all equal) − (1 − ⟨X…X⟩)/2), not the fidelity. For one shared pair at q = 0.05 it reads 0.900; the state fidelity is 0.9025. | EXACT | `svc exact '{"kind":"burst","k":3,"q":0.05}'`, field `fidelity_kind` |
| N5 | The break-even bar is max(classical guess, 1/2), not the classical guess. Against the bare classical guess no catalog circuit loses for any q ≤ 0.5: at q = 0.5 Grover still succeeds 0.219 against 0.125. That reflects a mild noise model (link only), not a strong machine. | EXACT | Snippet C4, columns `worst split` and `guess` |
| N6 | The burst idea is not ours (X7), and target-side sharing, which would save more pairs, is not implemented: two CNOTs onto one target cost two pairs. | REPRODUCIBLE | `python -m pytest -q tests/test_schedule.py -k shared_target` (1 passed) |
| N7 | "Best balanced cut" is not the cheapest cut. Auto cut searches balanced cuts only (B5). For phase estimation on four qubits the best balanced cut costs 2 pairs; an uneven one, `q3` alone in Trap B, costs 1. The page allows that cut and then shows "Pairs 1 · best balanced cut 2". Until v1.1 the label read "best cut", which was wrong. | REPRODUCIBLE | `svc plan '{"algorithm":"qft_phase","assignment":[0,0,0,1]}'` against `svc plan '{"algorithm":"qft_phase"}'` |

## Modeled

| ID | Claim | Tier | Assumptions |
|---|---|---|---|
| M1 | Link noise. | MODELED | After each raw pair is made, one half suffers an X flip with probability q and, independently, a Z flip with probability q. Same q for every pair. Local gates, measurements and idle time are perfect unless the chosen backend adds its own noise. |
| M2 | Pair-rate budget, for example "2 pairs per shot, about 500 shots per second at 1,000 pairs/s"; Grover with distillation at q = 0.05: 4 raw pairs, 250 shots per second, 171 kept. | MODELED | `seam.budget.link_budget`. The link delivers usable ion–ion Bell pairs at 1,000 per second, one at a time; a shot waits for all its raw pairs; gate time, classical latency and memory decoherence are ignored; a shot rejected by distillation wastes all its pairs. The 1,000 per second is IonQ's announced rate of ion–memory entanglement, not a measured ion–ion rate. |
| M3 | "The announced link, in this model": at q = 0.0625 split Grover succeeds 0.614 raw and 0.743 distilled (62.9% of shots kept, 157 kept shots per second); phase estimation 0.908 and 0.974. | MODELED | Takes the 87.9(7)% ion–memory Bell-pair fidelity of arXiv:2610.10705 as if it were the fidelity (1−q)² of an ion–ion pair with our Pauli noise. Then M1 and M2. `svc exact '{"kind":"algorithm","algorithm":"grover","q":0.0625,"distill":true}'` |
| M4 | The two classical bits of each teleported gate. | MODELED | Drawn and simulated as two-qubit gates (deferred measurement). Outcome statistics are identical to measure-and-correct; the classical wire and its delay are not represented. |
| M5 | Distillation. | MODELED | One 2→1 round, post-selected on two flag bits read at the end of the circuit. Hardware would herald and retry a pair before using it. |

## Not claimed

| ID | What a reader might assume | Why we do not assert it |
|---|---|---|
| X1 | A speed-up, or any advantage over one machine that fits the circuit. | L1. Splitting buys qubits one trap does not have; it never buys fidelity. |
| X2 | A real classical channel, mid-circuit measurement or feed-forward. | M4. |
| X3 | Memory decoherence, gate time, or the latency of heralded pair generation. | Ignored by M1 and M2. |
| X4 | Hardware results. | We report simulator results only. On an ideal backend the only noise is the link model. |
| X5 | That results after the first job on a one-job backend are sampled. | They are exact statevector values, and the page labels them so. |
| X6 | That 1,000 events per second is a rate of Bell pairs between two processors. | The announcement and its preprint report entanglement between one ion and one memory. |
| X7 | That the primitives are new. | Teleported gates: Eisert et al. 2000. Cat-entangler: Yimsiriwattana and Lomonaco 2004. Distillation: Bennett et al. 1996, Deutsch et al. 1996. Burst communication: Wu et al. 2022. Ours are this implementation, its tests and the explorable. |
| X8 | That the compilation is globally optimal. | B4 and B5 are optimal under the burst rule and for balanced cuts. Target-side sharing, commuting gates past each other and moving qubits by state teleportation are not explored. |
| X9 | More than two modules, more than 22 qubits per circuit, or a cut search beyond 12 data qubits. | Not built. |
| X10 | That q describes a specific device. | q is a model parameter. M3 is the only place a published number is plugged in, with its caveats. |

## Snippets

C1. The truth table with the phase correction removed (N1):

```bash
python -c '
from seam import build, lower, schedule, sim
gates = lower.from_steps([("cx", [0, 1])])
bursts = schedule.schedule(gates, [0, 1])
broken = build.distribute(gates, [0, 1], bursts, drop=("z", 0))
for c in (0, 1):
    for t in (0, 1):
        state = sim.zero_state(4)
        for wire, bit in ((0, c), (1, t)):
            if bit:
                sim.apply(state, "x", [wire])
        table = sim.probabilities(sim.run(broken.ops, 4, state), [0, 1], 4)
        print(f"input {c}{t}: P(expected) = {table[c, c ^ t]:.3f}")
'
```

C2. A burst forced across a Hadamard (B3). Prints minimum, mean and maximum fidelity:

```bash
python -c '
import numpy as np
from seam import build, lower, schedule, verify
gates = lower.from_steps([("cx", [0, 1]), ("h", [0]), ("cx", [0, 1])])
inputs = verify.random_inputs(2, 16, np.random.default_rng(0))
legal = schedule.schedule(gates, [0, 1])
merged = [schedule.Burst(0, 0, 0, (0, 2))]
for name, bursts in (("two pairs", legal), ("one pair", merged)):
    f = verify.fidelities(gates, build.distribute(gates, [0, 1], bursts), inputs)
    print(name, round(f.min(), 3), round(f.mean(), 3), round(f.max(), 3))
'
```

C3. Distillation formulas against the engine's circuits (K3):

```bash
python -c '
import json
from seam import service as s
qs = [k / 200 for k in range(101)]
points = json.loads(s.exact(json.dumps(dict(kind="remote_bell", qs=qs))))["points"]
worst = 0.0
for q, p in zip(qs, points):
    f = 2 * q * (1 - q)
    kept = (1 - f) ** 2 + f ** 2
    fidelity = ((1 - q) ** 4 + q ** 4) / kept
    worst = max(worst, abs(p["raw"]["f"] - (1 - q) ** 2), abs(p["distilled"]["f"] - fidelity), abs(p["distilled"]["kept"] - kept))
print("largest difference:", worst)
'
```

C4. One machine against the split machine on a 101-point grid (L1, L2, L3, N5):

```bash
python -c '
import json
from seam import service as s
qs = [k / 200 for k in range(101)]
for a in ("ghz", "bv", "qft_phase", "grover", "qaoa_ring"):
    r = json.loads(s.exact(json.dumps(dict(kind="algorithm_sweep", algorithm=a, qs=qs))))
    split = [p[v]["value"] for p in r["points"][1:] for v in ("raw", "distilled")]
    print(a, "one machine", r["mono"], "best split", round(max(split), 6), "worst split", round(min(split), 6),
          "guess", round(r["classical_guess"], 4), r["break_even_q"], r["distill_stops_helping_q"])
'
```

The best split value for QAOA prints as 1.0 after rounding; unrounded it is 0.99999997, at q = 0.005 with distillation.

C5. One teleported CNOT with a correction removed (G5). Prints the mean fidelity:

```bash
python -c '
import numpy as np
from seam import build, lower, schedule, verify
gates = lower.from_steps([("cx", [0, 1])])
bursts = schedule.schedule(gates, [0, 1])
inputs = verify.random_inputs(2, 16, np.random.default_rng(0))
for drop in (None, ("x", 0), ("z", 0)):
    f = verify.fidelities(gates, build.distribute(gates, [0, 1], bursts, drop=drop), inputs)
    print(drop, round(f.mean(), 3))
'
```
