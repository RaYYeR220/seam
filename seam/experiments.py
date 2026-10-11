"""Experiment specs -> backend circuits, decoding of counts and exact predictions.

Every experiment is a list of runs. A run is one distributed (or monolithic)
circuit, and the same analysis turns either measured counts or the exact
outcome distribution of each run into the result that is reported, so theory
and measurement cannot drift apart.

Exact predictions use the fact that the environment qubits of the noise model
only ever act as controls: their computational-basis value ``e`` is conserved
and the measured distribution is the mixture ``sum_e P_q(e) p_e(x)`` over
error patterns. One statevector run with the environment in uniform
superposition yields every ``p_e`` at once, after which any link error ``q``
is a reweighting.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from qiskit import QuantumCircuit

from . import budget, build, link, lower, sim
from .build import Distributed
from .plan import Plan, make_plan
from .schedule import schedule

Z95 = 1.959963984540054
DEFAULT_SHOTS = 2000
MAX_SHOTS = 1_000_000
MAX_POINTS = 201
KINDS = ("truth_table", "remote_bell", "burst", "algorithm", "algorithm_sweep")
GHZ_BOUND = "lower bound: max(0, P(all equal) - (1 - <X...X>)/2)"
_GRID_STEP = 0.005


@dataclass(frozen=True)
class Part:
    """A group of data bits of one run that is analysed together."""

    key: tuple
    bits: tuple[int, ...]


@dataclass
class Run:
    label: str
    dist: Distributed
    q: float
    parts: list[Part]
    cid: str = ""
    _transpiled: QuantumCircuit | None = None
    _model: "Model | None" = None

    def model(self) -> "Model":
        if self._model is None:
            self._model = model_for(self.dist)
        return self._model

    def transpiled(self) -> QuantumCircuit:
        if self._transpiled is None:
            self._transpiled = self.dist.backend_circuit()
        return self._transpiled

    def describe(self) -> dict:
        circuit = self.transpiled()
        return {
            "cid": self.cid,
            "label": self.label,
            "qubits": circuit.num_qubits,
            "depth": circuit.depth(),
        }


@dataclass(frozen=True)
class Outcome:
    """Distribution of one part over kept shots.

    ``weights`` are counts (``sampled``) or probabilities; ``total`` is their
    sum and ``kept`` the fraction of all shots that passed post-selection.
    """

    weights: dict[str, float]
    total: float
    kept: float
    sampled: bool

    def p(self, strings: Sequence[str]) -> float:
        return sum(self.weights.get(s, 0.0) for s in strings) / self.total

    def normalised(self) -> dict[str, float]:
        return {s: w / self.total for s, w in self.weights.items()}


@dataclass
class Setup:
    id: str
    kind: str
    spec: dict
    runs: list[Run]
    analyse: Callable[[dict, bool], dict]


class Model:
    """Outcome distributions of one circuit for every link error at once."""

    def __init__(self, dist: Distributed) -> None:
        total = dist.num_qubits
        state = sim.run(_neutral_ops(dist), total)
        self.env = dist.env
        measured = list(range(dist.num_data)) + [w for pair in dist.flags for w in pair]
        table = sim.probabilities(state, self.env + measured, total)
        self.table = table * 2.0 ** len(self.env)
        self.num_data = dist.num_data
        self.num_flags = len(dist.flags)

    def kept(self, q: float) -> np.ndarray:
        """Joint probability of the data bits and of every flag pair agreeing."""
        table = self.table
        for _ in self.env:
            table = (1.0 - q) * table[0] + q * table[1]
        for _ in range(self.num_flags):
            table = table[..., 0, 0] + table[..., 1, 1]
        return table


def _neutral_ops(dist: Distributed) -> tuple[link.Op, ...]:
    """The circuit with every environment qubit rotated to an even superposition."""
    half = math.pi / 2
    return tuple(
        link.Op("ry", op.wires, (half,), "noise", op.pair) if op.role == "noise" and op.name == "ry" else op
        for op in dist.ops
    )


_MODELS: dict[tuple, Model] = {}
_MODEL_CACHE = 48


def model_for(dist: Distributed) -> Model:
    key = (_neutral_ops(dist), dist.num_qubits, tuple(dist.flags))
    model = _MODELS.get(key)
    if model is None:
        if len(_MODELS) >= _MODEL_CACHE:
            _MODELS.pop(next(iter(_MODELS)))
        model = _MODELS[key] = Model(dist)
    return model


def _marginal(table: np.ndarray, bits: Sequence[int]) -> dict[str, float]:
    """Distribution of ``bits`` as bitstrings with the highest bit on the left."""
    wanted = set(bits)
    drop = tuple(k for k in range(table.ndim) if k not in wanted)
    reduced = table.sum(axis=drop) if drop else table
    ascending = sorted(bits)
    order = [ascending.index(b) for b in sorted(bits, reverse=True)]
    flat = reduced.transpose(order).reshape(-1)
    width = len(bits)
    return {format(int(i), f"0{width}b"): float(flat[i]) for i in np.flatnonzero(flat > 1e-15)}


def exact_outcomes(run: Run, q: float | None = None) -> dict[tuple, Outcome]:
    table = run.model().kept(run.q if q is None else q)
    kept = float(table.sum())
    return {
        part.key: Outcome(_marginal(table, part.bits), kept, min(1.0, kept), sampled=False)
        for part in run.parts
    }


def measured_outcomes(run: Run, counts: dict) -> dict[tuple, Outcome]:
    """Decode backend counts: drop shots whose flag bits disagree, split into parts."""
    n, flags = run.dist.num_data, len(run.dist.flags)
    if not isinstance(counts, dict) or not counts:
        raise ValueError(f"no counts for circuit {run.cid}")
    shots = 0
    kept = 0
    weights: dict[tuple, dict[str, float]] = {part.key: {} for part in run.parts}
    for key, count in counts.items():
        bits = str(key).replace(" ", "")
        if len(bits) != n + 2 * flags or set(bits) - {"0", "1"}:
            raise ValueError(f"circuit {run.cid}: outcome '{key}' should have {n + 2 * flags} bits")
        if isinstance(count, bool) or not isinstance(count, (int, float)) or count < 0:
            raise ValueError(f"circuit {run.cid}: count for '{key}' must be a non-negative number")
        shots += count
        reversed_bits = bits[::-1]
        flag_bits = reversed_bits[n:]
        if any(flag_bits[2 * k] != flag_bits[2 * k + 1] for k in range(flags)):
            continue
        kept += count
        for part in run.parts:
            sub = "".join(reversed_bits[b] for b in sorted(part.bits, reverse=True))
            weights[part.key][sub] = weights[part.key].get(sub, 0) + count
    if shots <= 0:
        raise ValueError(f"circuit {run.cid} has no shots")
    if kept <= 0:
        raise ValueError(f"circuit {run.cid}: no shot survived post-selection")
    return {
        part.key: Outcome(weights[part.key], float(kept), kept / shots, sampled=True)
        for part in run.parts
    }


def wilson(p: float, n: float) -> tuple[float, float]:
    """Wilson 95% score interval for a binomial proportion."""
    z2 = Z95 * Z95
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return min(p, max(0.0, centre - half)), max(p, min(1.0, centre + half))


def _normal(value: float, variance: float, lower_limit: float = 0.0) -> tuple[float, float]:
    half = Z95 * math.sqrt(max(variance, 0.0))
    return max(lower_limit, value - half), min(1.0, value + half)


def hellinger(p: dict[str, float], q: dict[str, float]) -> float:
    """Hellinger fidelity ``(sum_x sqrt(p_x q_x))^2`` of two distributions."""
    return min(1.0, sum(math.sqrt(w * q.get(s, 0.0)) for s, w in p.items()) ** 2)


def hellinger_interval(
    outcome: Outcome, ideal: dict[str, float], resamples: int = 300
) -> tuple[float, float]:
    """Basic-bootstrap 95% interval for the Hellinger fidelity with ``ideal``.

    The plug-in estimate is biased low by roughly (outcomes - 1) / (4 shots);
    reflecting the bootstrap percentiles about the estimate removes that bias
    to first order. The interval is widened where needed so that it always
    contains the plug-in estimate that is reported next to it.
    """
    strings = sorted(outcome.weights)
    n = int(round(outcome.total))
    observed = np.array([outcome.weights[s] for s in strings], dtype=float) / outcome.total
    reference = np.array([ideal.get(s, 0.0) for s in strings])
    estimate = float(np.sqrt(observed * reference).sum() ** 2)
    rng = np.random.default_rng(12345)
    samples = rng.multinomial(n, observed, size=resamples) / n
    replicas = np.sqrt(samples * reference).sum(axis=1) ** 2
    low, high = np.percentile(replicas, [2.5, 97.5])
    reflected = max(0.0, 2 * estimate - float(high)), min(1.0, 2 * estimate - float(low))
    return min(reflected[0], estimate), max(reflected[1], estimate)


def _first_crossing(f: Callable[[float], float], start: float, stop: float = 0.5) -> float | None:
    """Smallest grid point in [start, stop] where ``f`` is not positive, refined by bisection."""
    previous = None
    steps = int(round((stop - start) / _GRID_STEP))
    for k in range(steps + 1):
        q = start + k * _GRID_STEP
        if f(q) <= 0:
            if previous is None:
                return round(q, 4)
            low, high = previous, q
            for _ in range(30):
                middle = 0.5 * (low + high)
                if f(middle) <= 0:
                    high = middle
                else:
                    low = middle
            return round(high, 4)
        previous = q
    return None


def _number(spec: dict, name: str, default: float | None, low: float, high: float) -> float:
    value = spec.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"'{name}' must be a number between {low} and {high}")
    return float(value)


def _q(spec: dict) -> float:
    return _number(spec, "q", 0.0, 0.0, 0.5)


def _qs(spec: dict) -> list[float]:
    qs = spec.get("qs")
    if not isinstance(qs, list) or not qs or len(qs) > MAX_POINTS:
        raise ValueError(f"'qs' must be a list of 1 to {MAX_POINTS} link error values")
    if any(isinstance(q, bool) or not isinstance(q, (int, float)) or not 0 <= q <= 0.5 for q in qs):
        raise ValueError("every value in 'qs' must be a number between 0 and 0.5")
    return [float(q) for q in qs]


def _variants(spec: dict) -> list[str]:
    choice = spec.get("distill", "both")
    if isinstance(choice, bool):
        return ["distilled"] if choice else ["raw"]
    if choice == "both":
        return ["raw", "distilled"]
    raise ValueError("'distill' must be true, false or \"both\"")


def _bool(spec: dict, name: str, default: bool) -> bool:
    value = spec.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"'{name}' must be true or false")
    return value


def _distribute(
    steps: Sequence, assignment: Sequence[int], q: float, distill: bool, reuse: bool = True
) -> Distributed:
    gates = lower.from_steps(steps)
    dist = build.distribute(gates, assignment, schedule(gates, assignment, reuse), q, distill)
    _check_size(dist.num_qubits)
    return dist


def _check_size(qubits: int) -> None:
    if qubits > build.MAX_BACKEND_QUBITS:
        raise ValueError(
            f"this experiment needs {qubits} qubits; the backend limit is {build.MAX_BACKEND_QUBITS}"
        )


def _truth_table(spec: dict) -> tuple[dict, list[Run], Callable]:
    q = _q(spec)
    inputs = ["00", "01", "10", "11"]

    def block(row: str, control: int, target: int) -> list:
        prepare = [("x", [w]) for w, bit in ((control, row[0]), (target, row[1])) if bit == "1"]
        return prepare + [("cx", [control, target])]

    if q == 0:
        steps = [step for j, row in enumerate(inputs) for step in block(row, 2 * j, 2 * j + 1)]
        dist = _distribute(steps, [0, 1] * 4, 0.0, False)
        parts = [Part(("row", row), (2 * j, 2 * j + 1)) for j, row in enumerate(inputs)]
        runs = [Run("teleported CNOT, all four inputs side by side", dist, 0.0, parts)]
    else:
        runs = [
            Run(
                f"teleported CNOT, input {row}, q={q:g}",
                _distribute(block(row, 0, 1), [0, 1], q, False),
                q,
                [Part(("row", row), (0, 1))],
            )
            for row in inputs
        ]

    def analyse(outcomes: dict, sampled: bool) -> dict:
        rows = []
        for row in inputs:
            outcome = outcomes[("row", row)]
            expected = row[0] + str(int(row[0]) ^ int(row[1]))
            p = outcome.p([expected[::-1]])
            entry = {"input": row, "expected": expected, "p_expected": p}
            if sampled:
                entry["lo"], entry["hi"] = wilson(p, outcome.total)
            shown = outcome.weights if sampled else outcome.normalised()
            entry["counts"] = {s[::-1]: w for s, w in sorted(shown.items())}
            rows.append(entry)
        return {
            "rows": rows,
            "agreement": sum(r["p_expected"] for r in rows) / len(rows),
            "pairs": 1,
            "q": q,
            "bit_order": "control then target",
        }

    return {"q": q}, runs, analyse


_BASIS_CHANGE = {"zz": [], "xx": ["h"], "yy": ["sdg", "h"]}


def _correlator(outcome: Outcome) -> float:
    """Expectation of the parity (+1 for an even number of ones)."""
    even = [s for s in outcome.weights if s.count("1") % 2 == 0]
    return 2 * outcome.p(even) - 1


def _remote_bell(spec: dict) -> tuple[dict, list[Run], Callable]:
    qs, variants = _qs(spec), _variants(spec)

    def dist_for(q: float, variant: str, setting: str) -> Distributed:
        steps = [("h", [0]), ("cx", [0, 1])]
        steps += [(name, [w]) for w in (0, 1) for name in _BASIS_CHANGE[setting]]
        return _distribute(steps, [0, 1], q, variant == "distilled")

    runs = [
        Run(
            f"{variant}, q={q:g}, {setting.upper()}",
            dist_for(q, variant, setting),
            q,
            [Part((k, variant, setting), (0, 1))],
        )
        for k, q in enumerate(qs)
        for variant in variants
        for setting in _BASIS_CHANGE
    ]
    reference = {
        variant: [
            Run("", dist_for(0.25, variant, setting), 0.25, [Part((setting,), (0, 1))])
            for setting in _BASIS_CHANGE
        ]
        for variant in ("raw", "distilled")
    }

    def fidelity(by_setting: dict[str, Outcome]) -> float:
        zz, xx, yy = (_correlator(by_setting[s]) for s in ("zz", "xx", "yy"))
        return (1 + zz + xx - yy) / 4

    def exact_fidelity(variant: str, q: float) -> float:
        settings = zip(_BASIS_CHANGE, reference[variant])
        return fidelity({s: exact_outcomes(run, q)[(s,)] for s, run in settings})

    def analyse(outcomes: dict, sampled: bool) -> dict:
        points = []
        for k, q in enumerate(qs):
            point = {"q": q, "pair_fidelity": link.pair_fidelity(q)}
            for variant in variants:
                by_setting = {s: outcomes[(k, variant, s)] for s in _BASIS_CHANGE}
                f = fidelity(by_setting)
                entry = {"f": f}
                if sampled:
                    spread = sum((1 - _correlator(o) ** 2) / o.total for o in by_setting.values())
                    entry["lo"], entry["hi"] = _normal(f, spread / 16)
                if variant == "distilled":
                    entry["kept"] = sum(o.kept for o in by_setting.values()) / 3
                    point["pair_fidelity_distilled"] = link.distilled(q)[0]
                point[variant] = entry
            points.append(point)
        stops = _first_crossing(
            lambda q: exact_fidelity("distilled", q) - exact_fidelity("raw", q), _GRID_STEP
        )
        return {
            "points": points,
            "thresholds": {"entanglement": 0.5, "distill_stops_helping_q": stops},
            "formula": "F = (1 + <ZZ> + <XX> - <YY>) / 4",
        }

    return {"qs": qs, "distill": spec.get("distill", "both")}, runs, analyse


def _burst(spec: dict) -> tuple[dict, list[Run], Callable]:
    q = _q(spec)
    k = spec.get("k", 3)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 4:
        raise ValueError("'k' must be an integer from 1 to 4")
    choice = spec.get("reuse", "both")
    if not isinstance(choice, bool) and choice != "both":
        raise ValueError("'reuse' must be true, false or \"both\"")
    modes = [True, False] if choice == "both" else [choice]
    width = k + 1
    fan_out = [("h", [0])] + [("cx", [0, t]) for t in range(1, width)]
    settings = {"z": fan_out, "x": fan_out + [("h", [w]) for w in range(width)]}
    assignment = [0] + [1] * k
    runs = [
        Run(
            f"{'one pair' if reuse else 'one pair per gate'}, {setting.upper()} basis",
            _distribute(steps, assignment, q, False, reuse),
            q,
            [Part((reuse, setting), tuple(range(width)))],
        )
        for reuse in modes
        for setting, steps in settings.items()
    ]
    sizes = {reuse: next(r.dist for r in runs if r.parts[0].key[0] == reuse) for reuse in modes}

    def analyse(outcomes: dict, sampled: bool) -> dict:
        variants = []
        for reuse in modes:
            in_z, in_x = outcomes[(reuse, "z")], outcomes[(reuse, "x")]
            equal = in_z.p(["0" * width, "1" * width])
            parity = _correlator(in_x)
            bound = max(0.0, equal - (1 - parity) / 2)
            entry = {
                "reuse": reuse,
                "pairs": sizes[reuse].pairs,
                "qubits": sizes[reuse].num_qubits,
                "p_equal": {"value": equal},
                "x_parity": {"value": parity},
                "fidelity": {"value": bound},
            }
            if sampled:
                parity_variance = (1 - parity**2) / in_x.total
                entry["p_equal"]["lo"], entry["p_equal"]["hi"] = wilson(equal, in_z.total)
                low, high = _normal(parity, parity_variance, lower_limit=-1.0)
                entry["x_parity"]["lo"], entry["x_parity"]["hi"] = low, high
                variance = equal * (1 - equal) / in_z.total + parity_variance / 4
                entry["fidelity"]["lo"], entry["fidelity"]["hi"] = _normal(bound, variance)
            variants.append(entry)
        return {"k": k, "q": q, "variants": variants, "fidelity_kind": GHZ_BOUND}

    return {"k": k, "q": q, "reuse": choice}, runs, analyse


def _plan_spec(spec: dict) -> dict:
    names = ("algorithm", "n", "params", "assignment", "capacity")
    return {name: spec.get(name) for name in names} | {"reuse": spec.get("reuse", True)}


def _algorithm_runs(
    spec: dict, points: Sequence[tuple[float, bool]]
) -> tuple[Plan, list[Run], dict[str, float], float]:
    """Monolithic run plus one distributed run per (q, distill) point.

    Also returns the ideal output distribution and the classical baseline:
    the chance of guessing a target, or, for circuits without a single
    answer, the Hellinger fidelity of the uniform distribution with the ideal.
    """
    plan = make_plan(spec)
    n = plan.n
    everything = tuple(range(n))
    mono = Run("monolithic", build.monolithic(plan.gates, n), 0.0, [Part(("mono",), everything)])
    runs = [mono]
    for q, distill in points:
        plan.check_fits(q, distill)
        dist = build.distribute(plan.gates, plan.assignment, plan.bursts, q, distill)
        label = f"distributed{', distilled' if distill else ''}, q={q:g}"
        runs.append(Run(label, dist, q, [Part(("dist", q, distill), everything)]))
    ideal = exact_outcomes(mono)[("mono",)].normalised()
    targets = plan.instance.targets
    if targets:
        guess = plan.instance.classical_guess
    else:
        uniform = {format(i, f"0{n}b"): 1 / 2**n for i in range(2**n)}
        guess = hellinger(uniform, ideal)
    return plan, runs, ideal, guess


def _headline(outcome: Outcome, targets: list[str] | None, ideal: dict[str, float]) -> float:
    return outcome.p(targets) if targets else hellinger(outcome.normalised(), ideal)


def _headline_interval(
    outcome: Outcome, targets: list[str] | None, ideal: dict[str, float]
) -> tuple[float, float]:
    if targets:
        return wilson(outcome.p(targets), outcome.total)
    return hellinger_interval(outcome, ideal)


def _algorithm(spec: dict) -> tuple[dict, list[Run], Callable]:
    q, distill = _q(spec), _bool(spec, "distill", False)
    plan, runs, ideal, guess = _algorithm_runs(spec, [(q, distill)])
    targets = plan.instance.targets
    mono_run, dist_run = runs

    def summarise(outcome: Outcome, run: Run, sampled: bool) -> dict:
        entry = {"success": outcome.p(targets) if targets else None}
        if sampled:
            entry["lo"], entry["hi"] = _headline_interval(outcome, targets, ideal)
        entry["hellinger"] = hellinger(outcome.normalised(), ideal)
        shown = outcome.weights if sampled else outcome.normalised()
        ranked = sorted(shown.items(), key=lambda item: (-item[1], item[0]))
        entry["top"] = [[s, w] for s, w in ranked[:5]]
        entry.update({k: v for k, v in run.describe().items() if k in ("qubits", "depth")})
        return entry

    def analyse(outcomes: dict, sampled: bool) -> dict:
        dist_outcome = outcomes[("dist", q, distill)]
        dist = summarise(dist_outcome, dist_run, sampled)
        dist["kept"] = dist_outcome.kept
        return {
            "target": targets,
            "metric": "success" if targets else "hellinger",
            "mono": summarise(outcomes[("mono",)], mono_run, sampled),
            "dist": dist,
            "pairs": plan.pairs,
            "pairs_without_reuse": plan.cross,
            "classical_guess": guess,
            "budget": budget.link_budget(plan.pairs, dist_run.dist.raw_pairs, dist_outcome.kept),
            "q": q,
            "distill": distill,
        }

    return _plan_spec(spec) | {"q": q, "distill": distill}, runs, analyse


def _algorithm_sweep(spec: dict) -> tuple[dict, list[Run], Callable]:
    qs, variants = _qs(spec), _variants(spec)
    points = [(q, variant == "distilled") for q in qs for variant in variants]
    plan, runs, ideal, guess = _algorithm_runs(spec, points)
    targets = plan.instance.targets
    for variant in variants:
        plan.check_fits(0.25, variant == "distilled")
    reference = {
        variant: Run(
            "",
            build.distribute(plan.gates, plan.assignment, plan.bursts, 0.25, variant == "distilled"),
            0.25,
            [Part(("ref",), tuple(range(plan.n)))],
        )
        for variant in variants
    }
    floor = max(guess, 0.5)

    def exact_value(variant: str, q: float) -> float:
        return _headline(exact_outcomes(reference[variant], q)[("ref",)], targets, ideal)

    def analyse(outcomes: dict, sampled: bool) -> dict:
        rows = []
        for q in qs:
            row = {"q": q}
            for variant in variants:
                outcome = outcomes[("dist", q, variant == "distilled")]
                entry = {"value": _headline(outcome, targets, ideal)}
                if sampled:
                    entry["lo"], entry["hi"] = _headline_interval(outcome, targets, ideal)
                if variant == "distilled":
                    entry["kept"] = outcome.kept
                row[variant] = entry
            rows.append(row)
        result = {
            "points": rows,
            "metric": "success" if targets else "hellinger",
            "mono": _headline(outcomes[("mono",)], targets, ideal),
            "classical_guess": guess,
            "break_even_q": {
                variant: _first_crossing(lambda q: exact_value(variant, q) - floor + 1e-12, 0.0)
                for variant in variants
            },
            "pairs": plan.pairs,
            "target": targets,
        }
        if len(variants) == 2:
            result["distill_stops_helping_q"] = _first_crossing(
                lambda q: exact_value("distilled", q) - exact_value("raw", q), _GRID_STEP
            )
        return result

    return _plan_spec(spec) | {"qs": qs, "distill": spec.get("distill", "both")}, runs, analyse


_BUILDERS: dict[str, Callable[[dict], tuple[dict, list[Run], Callable]]] = {
    "truth_table": _truth_table,
    "remote_bell": _remote_bell,
    "burst": _burst,
    "algorithm": _algorithm,
    "algorithm_sweep": _algorithm_sweep,
}
_SETUPS: dict[str, Setup] = {}
_SUBMITTED: dict[str, Setup] = {}
_SETUP_CACHE = 64
_SUBMITTED_CACHE = 256
_counter = 0


def _remember(cache: dict, key: str, value: Setup, limit: int) -> None:
    if key not in cache and len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = value


def setup(spec: dict) -> Setup:
    """Build (or fetch from cache) the runs and analysis for an experiment spec."""
    global _counter
    if not isinstance(spec, dict):
        raise ValueError("an experiment spec must be a JSON object")
    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in _BUILDERS:
        raise ValueError(f"unknown experiment kind; choose one of {', '.join(KINDS)}")
    key = json.dumps({k: v for k, v in spec.items() if k != "shots"}, sort_keys=True)
    cached = _SETUPS.get(key)
    if cached is not None:
        return cached
    normal, runs, analyse = _BUILDERS[kind](spec)
    _counter += 1
    made = Setup(f"x{_counter}", kind, {"kind": kind, **normal}, runs, analyse)
    for k, run in enumerate(runs):
        run.cid = f"{made.id}-{k}"
    _remember(_SETUPS, key, made, _SETUP_CACHE)
    return made


def shots_of(spec: dict) -> int:
    shots = spec.get("shots", DEFAULT_SHOTS)
    if isinstance(shots, bool) or not isinstance(shots, int) or not 1 <= shots <= MAX_SHOTS:
        raise ValueError(f"'shots' must be an integer between 1 and {MAX_SHOTS}")
    return shots


def describe(spec: dict) -> dict:
    """What to submit: one entry per backend circuit.

    Experiments described here stay addressable by id while their counts are
    awaited, independently of how many exact predictions are requested since.
    """
    made = setup(spec)
    shots = shots_of(spec)
    _remember(_SUBMITTED, made.id, made, _SUBMITTED_CACHE)
    return {
        "id": made.id,
        "kind": made.kind,
        "circuits": [run.describe() for run in made.runs],
        "shots": shots,
    }


def find(experiment_id: str) -> Setup:
    made = _SUBMITTED.get(experiment_id)
    if made is None:
        raise ValueError(f"unknown experiment '{experiment_id}'; call experiment() first")
    return made


def circuit(cid: str) -> QuantumCircuit:
    """The transpiled, measured circuit behind a circuit id."""
    experiment_id = str(cid).rsplit("-", 1)[0]
    for run in find(experiment_id).runs:
        if run.cid == cid:
            return run.transpiled()
    raise ValueError(f"unknown circuit '{cid}'")


def _rounded(value: object) -> object:
    """Drop floating-point dust so that an exact 1 reads as 1."""
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def _result(made: Setup, outcomes: dict, sampled: bool, shots: int | None) -> dict:
    body = _rounded(made.analyse(outcomes, sampled))
    return {"kind": made.kind, "source": "measured" if sampled else "exact", **body, "shots": shots}


def ingest(experiment_id: str, counts_by_cid: dict, shots: int | None = None) -> dict:
    """Turn backend counts into the result of an experiment."""
    made = find(experiment_id)
    if not isinstance(counts_by_cid, dict):
        raise ValueError("counts must be an object keyed by circuit id")
    outcomes: dict = {}
    for run in made.runs:
        if run.cid not in counts_by_cid:
            raise ValueError(f"counts for circuit {run.cid} are missing")
        outcomes.update(measured_outcomes(run, counts_by_cid[run.cid]))
    return _result(made, outcomes, True, shots)


def exact(spec: dict) -> dict:
    """The same result computed from statevectors, with no sampling noise."""
    made = setup(spec)
    outcomes: dict = {}
    for run in made.runs:
        outcomes.update(exact_outcomes(run))
    return _result(made, outcomes, False, None)


def sample(spec: dict, shots: int, seed: int = 0) -> dict[str, dict[str, int]]:
    """Counts drawn from the exact distribution of every circuit of an experiment.

    Stands in for a backend: keys look like Qiskit's, flag register first.
    """
    made = setup(spec)
    rng = np.random.default_rng(seed)
    counts_by_cid = {}
    for run in made.runs:
        model = run.model()
        table = model.table
        for _ in model.env:
            table = (1.0 - run.q) * table[0] + run.q * table[1]
        width = table.ndim
        flat = table.transpose(tuple(range(width - 1, -1, -1))).reshape(-1)
        drawn = rng.multinomial(shots, flat / flat.sum())
        n = run.dist.num_data
        counts = {}
        for index in np.flatnonzero(drawn):
            bits = format(int(index), f"0{width}b")
            key = bits[-n:] if width == n else f"{bits[:-n]} {bits[-n:]}"
            counts[key] = int(drawn[index])
        counts_by_cid[run.cid] = counts
    return counts_by_cid
