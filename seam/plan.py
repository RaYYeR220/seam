"""Resolve a plan request: circuit, cut, bursts and what they cost."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from . import algorithms, partition
from .algorithms import Instance
from .build import MAX_BACKEND_QUBITS, qubit_cost
from .lower import Gate, asap_layers, lower
from .schedule import Burst, Scheduler, is_cross


@dataclass(frozen=True)
class Plan:
    instance: Instance
    gates: tuple[Gate, ...]
    assignment: tuple[int, ...]
    auto: bool
    reuse: bool
    bursts: tuple[Burst, ...]
    cross: int
    best: int
    worst: int

    @property
    def n(self) -> int:
        return self.instance.n

    @property
    def pairs(self) -> int:
        return len(self.bursts)

    def qubits(self, q: float = 0.0, distill: bool = False) -> int:
        return qubit_cost(self.n, self.pairs, q, distill)

    def check_fits(self, q: float = 0.0, distill: bool = False) -> None:
        """Raise when the distributed circuit would exceed the backend limit."""
        needed = self.qubits(q, distill)
        if needed <= MAX_BACKEND_QUBITS:
            return
        extras = [name for name, on in (("link noise", q > 0), ("distillation", distill)) if on]
        detail = f" with {' and '.join(extras)}" if extras else ""
        advice = ["use a smaller circuit", "choose a cheaper cut"]
        if not self.reuse:
            advice.append("let one pair serve a whole burst")
        if extras:
            advice.append(f"switch off {' or '.join(extras)}")
        raise ValueError(
            f"This cut needs {self.pairs} Bell pair{'s' if self.pairs != 1 else ''}, "
            f"which makes {needed} qubits{detail}; the backend limit is {MAX_BACKEND_QUBITS}. "
            f"To fit: {', '.join(advice)}."
        )

    def to_dict(self) -> dict:
        owner = {i: b.id for b in self.bursts for i in b.gate_indices}
        layers = asap_layers(self.n, (g.qubits for g in self.gates))
        return {
            "algorithm": self.instance.algorithm,
            "n": self.n,
            "params": self.instance.params,
            "assignment": list(self.assignment),
            "auto": self.auto,
            "reuse": self.reuse,
            "gates": [
                {
                    "i": g.i,
                    "name": g.name,
                    "qubits": list(g.qubits),
                    "params": list(g.params),
                    "layer": layer,
                    "cross": is_cross(g, self.assignment),
                    "burst": owner.get(g.i),
                }
                for g, layer in zip(self.gates, layers)
            ],
            "layers": max(layers, default=-1) + 1,
            "cut": {
                "cross_gates": self.cross,
                "pairs": self.pairs,
                "pairs_without_reuse": self.cross,
            },
            "bursts": [
                {
                    "id": b.id,
                    "control": b.control,
                    "control_module": b.control_module,
                    "gate_indices": list(b.gate_indices),
                }
                for b in self.bursts
            ],
            "scores": {"this": self.pairs, "best": self.best, "worst": self.worst},
            "qubits": {
                "data": self.n,
                "comm": 2 * self.pairs,
                "total_clean": self.qubits(),
                "total_noisy": self.qubits(q=0.1),
                "total_distilled": self.qubits(distill=True),
                "total_noisy_distilled": self.qubits(q=0.1, distill=True),
            },
            "target": self.instance.targets,
        }


@lru_cache(maxsize=64)
def _cached(key: str) -> Plan:
    options = json.loads(key)
    instance = algorithms.build(options["algorithm"], options["n"], options["params"])
    gates = tuple(lower(instance.circuit))
    n = instance.n
    reuse = options["reuse"]
    capacity = partition.check_capacity(n, options["capacity"])
    found = partition.search(gates, n, capacity, reuse)
    if options["assignment"] is None:
        assignment, auto = found.assignment, True
    else:
        assignment, auto = partition.check_assignment(n, options["assignment"]), False
        if options["capacity"] is not None and not partition.within(assignment, capacity):
            raise ValueError(f"assignment does not fit the module capacities {capacity}")
    scheduler = Scheduler(gates)
    return Plan(
        instance=instance,
        gates=gates,
        assignment=tuple(assignment),
        auto=auto,
        reuse=reuse,
        bursts=tuple(scheduler.bursts(assignment, reuse)),
        cross=scheduler.count_cross(assignment),
        best=found.best,
        worst=found.worst,
    )


def make_plan(options: dict) -> Plan:
    """Plan from request options; keys other than the plan options are ignored.

    ``assignment: null`` asks for the best cut under the capacities (balanced
    modules by default), judged by Bell pairs with the requested ``reuse``.
    """
    if not isinstance(options, dict):
        raise ValueError("options must be a JSON object")
    algorithm = options.get("algorithm")
    if not isinstance(algorithm, str):
        raise ValueError("options need an 'algorithm' id")
    params = options.get("params")
    if params is not None and not isinstance(params, dict):
        raise ValueError("'params' must be an object")
    reuse = options.get("reuse", True)
    if not isinstance(reuse, bool):
        raise ValueError("'reuse' must be true or false")
    for name in ("assignment", "capacity"):
        if options.get(name) is not None and not isinstance(options[name], list):
            raise ValueError(f"'{name}' must be a list or null")
    key = {
        "algorithm": algorithm,
        "n": options.get("n"),
        "params": params,
        "assignment": options.get("assignment"),
        "capacity": options.get("capacity"),
        "reuse": reuse,
    }
    return _cached(json.dumps(key, sort_keys=True))
