"""Lowering to the planning gate set: one-qubit gates, ``cx`` and ``cz``.

Everything downstream (scheduling, building, verification) works on the flat
list of :class:`Gate` produced here, and refers to gates by their index in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from qiskit import QuantumCircuit

ONE_QUBIT = frozenset(
    {"id", "h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg", "rx", "ry", "rz", "p", "u"}
)
Z_DIAGONAL = frozenset({"id", "z", "s", "sdg", "t", "tdg", "rz", "p"})
TWO_QUBIT = frozenset({"cx", "cz"})

Step = tuple  # (name, qubits) or (name, qubits, params)


@dataclass(frozen=True)
class Gate:
    """One gate of a lowered circuit; ``i`` is its position in the flat list."""

    i: int
    name: str
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()

    def diagonal_on(self, qubit: int) -> bool:
        """True when the gate is diagonal in the Z basis of ``qubit``.

        Such a gate cannot tell a qubit from a Z-basis copy of it, which is
        what lets a cat state stay open across it.
        """
        if self.name == "cz":
            return True
        if self.name == "cx":
            return qubit == self.qubits[0]
        return self.name in Z_DIAGONAL


def _cp(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    (theta,), (a, b) = params, q
    return [
        ("p", [a], [theta / 2]),
        ("cx", [a, b]),
        ("p", [b], [-theta / 2]),
        ("cx", [a, b]),
        ("p", [b], [theta / 2]),
    ]


def _crz(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    (theta,), (c, t) = params, q
    return [("rz", [t], [theta / 2]), ("cx", [c, t]), ("rz", [t], [-theta / 2]), ("cx", [c, t])]


def _rzz(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    (theta,), (a, b) = params, q
    return [("cx", [a, b]), ("rz", [b], [theta]), ("cx", [a, b])]


def _swap(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    a, b = q
    return [("cx", [a, b]), ("cx", [b, a]), ("cx", [a, b])]


def _cy(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    c, t = q
    return [("sdg", [t]), ("cx", [c, t]), ("s", [t])]


def _ccz(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    """Doubly-controlled Z from six CNOTs and T gates, with no Hadamards.

    The first qubit only ever acts as a CNOT control, so a cut that isolates
    it turns the whole gate into a single burst.
    """
    a, b, t = q
    return [
        ("cx", [b, t]),
        ("tdg", [t]),
        ("cx", [a, t]),
        ("t", [t]),
        ("cx", [b, t]),
        ("tdg", [t]),
        ("cx", [a, t]),
        ("t", [b]),
        ("t", [t]),
        ("cx", [a, b]),
        ("t", [a]),
        ("tdg", [b]),
        ("cx", [a, b]),
    ]


def _ccx(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    return [("h", [q[2]]), ("ccz", list(q)), ("h", [q[2]])]


def _u1(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    return [("p", list(q), list(params))]


def _u2(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    return [("u", list(q), [math.pi / 2, *params])]


def _u3(params: Sequence[float], q: Sequence[int]) -> list[Step]:
    return [("u", list(q), list(params))]


_RULES: dict[str, Callable[[Sequence[float], Sequence[int]], list[Step]]] = {
    "cp": _cp,
    "cu1": _cp,
    "crz": _crz,
    "rzz": _rzz,
    "swap": _swap,
    "cy": _cy,
    "ccz": _ccz,
    "ccx": _ccx,
    "u1": _u1,
    "u2": _u2,
    "u3": _u3,
}
_IGNORED = frozenset({"barrier", "delay"})


class _Emitter:
    def __init__(self) -> None:
        self.gates: list[Gate] = []

    def emit(self, name: str, qubits: Sequence[int], params: Sequence[float] = ()) -> None:
        qubits = tuple(int(q) for q in qubits)
        if name in ONE_QUBIT or name in TWO_QUBIT:
            if len(set(qubits)) != len(qubits):
                raise ValueError(f"gate {name} repeats a qubit: {qubits}")
            values = tuple(float(p) for p in params)
            self.gates.append(Gate(len(self.gates), name, qubits, values))
            return
        rule = _RULES.get(name)
        if rule is None:
            raise ValueError(f"cannot lower gate '{name}' to one-qubit gates, cx and cz")
        for step in rule([float(p) for p in params], qubits):
            self.emit(*step)


def from_steps(steps: Iterable[Step]) -> list[Gate]:
    """Lower a list of ``(name, qubits[, params])`` steps."""
    emitter = _Emitter()
    for step in steps:
        emitter.emit(*step)
    return emitter.gates


def _steps(circuit: QuantumCircuit, wires: Sequence[int]) -> Iterable[Step]:
    for inst in circuit.data:
        op = inst.operation
        qubits = [wires[circuit.find_bit(q).index] for q in inst.qubits]
        if op.name in _IGNORED:
            continue
        if inst.clbits or op.name in ("measure", "reset"):
            raise ValueError("only unitary circuits can be split; remove measurements and resets")
        if op.name in ONE_QUBIT or op.name in TWO_QUBIT or op.name in _RULES:
            yield (op.name, qubits, [float(p) for p in op.params])
        elif op.definition is not None:
            yield from _steps(op.definition, qubits)
        else:
            raise ValueError(f"cannot lower gate '{op.name}' to one-qubit gates, cx and cz")


def lower(circuit: QuantumCircuit) -> list[Gate]:
    """Lower a unitary circuit to one-qubit gates, ``cx`` and ``cz``.

    The result equals the input up to a global phase. Gates without a rule
    here are expanded through their own definitions.
    """
    return from_steps(_steps(circuit, list(range(circuit.num_qubits))))


def to_circuit(gates: Iterable[Gate], num_qubits: int) -> QuantumCircuit:
    """Rebuild a Qiskit circuit from lowered gates."""
    circuit = QuantumCircuit(num_qubits)
    for gate in gates:
        getattr(circuit, gate.name)(*gate.params, *gate.qubits)
    return circuit


def asap_layers(num_wires: int, wires_per_op: Iterable[Sequence[int]]) -> list[int]:
    """As-soon-as-possible layer index of each operation, for drawing."""
    free = [0] * num_wires
    layers = []
    for wires in wires_per_op:
        layer = max(free[w] for w in wires)
        for w in wires:
            free[w] = layer + 1
        layers.append(layer)
    return layers
