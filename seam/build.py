"""Build the distributed circuit from a gate list, a cut and a burst schedule.

For a burst with control ``c`` in module M and pair ``(a, b)`` (``a`` in M,
``b`` in the other module) the gates are kept in their original order and

* just before the first gate of the burst: ``cx(c, a); cx(a, b)``. Qubit
  ``b`` is now a Z-basis copy of ``c``;
* each gate of the burst acts from ``b`` instead of ``c``, which makes it a
  local gate of the other module;
* just after the last gate of the burst: ``h(b); cz(b, c)``, which erases
  the copy.

``cx(a, b)`` and ``cz(b, c)`` are the two classical bits of the protocol in
deferred-measurement form: on hardware with mid-circuit measurement ``a`` and
``b`` are measured and the gates become conditional Paulis. They and the pair
generation itself are the only operations that cross the link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile

from . import link
from .link import Op
from .lower import Gate, asap_layers
from .schedule import Burst

BASIS = ["rx", "ry", "rz", "h", "x", "cx"]
MAX_BACKEND_QUBITS = 22


@dataclass(frozen=True)
class Wire:
    id: int
    kind: str
    module: int | None
    label: str
    pair: int | None = None
    data_index: int | None = None


@dataclass
class Distributed:
    """A distributed circuit: wires, tagged operations and what to measure."""

    wires: list[Wire]
    ops: list[Op]
    num_data: int
    pairs: int
    raw_pairs: int
    flags: list[tuple[int, int]] = field(default_factory=list)

    @property
    def num_qubits(self) -> int:
        return len(self.wires)

    @property
    def env(self) -> list[int]:
        return [w.id for w in self.wires if w.kind == "env"]

    def count(self, kind: str) -> int:
        return sum(1 for w in self.wires if w.kind == kind)

    def crosses_link(self, op: Op) -> bool:
        modules = {self.wires[w].module for w in op.wires}
        return len(op.wires) == 2 and None not in modules and len(modules) == 2

    def measurements(self) -> list[Op]:
        """Final measurements: every data qubit, then the distillation flags."""
        ops = [Op("measure", (w,), role="measure") for w in range(self.num_data)]
        for k, (a2, b2) in enumerate(self.flags):
            ops.append(Op("measure", (a2,), role="measure", pair=k))
            ops.append(Op("measure", (b2,), role="measure", pair=k))
        return ops

    def layout(self) -> dict:
        """Drawing data: wires, operations with layers, and qubit counts."""
        ops = self.ops + self.measurements()
        layers = asap_layers(self.num_qubits, (op.wires for op in ops))
        final = max((l for l, op in zip(layers, ops) if op.role != "measure"), default=-1) + 1
        drawn = []
        for op, layer in zip(ops, layers):
            drawn.append(
                {
                    "name": op.name,
                    "wires": list(op.wires),
                    "params": list(op.params),
                    "role": op.role,
                    "pair": op.pair,
                    "gate": op.gate,
                    "layer": final if op.role == "measure" else layer,
                    "crosses_link": self.crosses_link(op),
                }
            )
        return {
            "wires": [
                {
                    "id": w.id,
                    "kind": w.kind,
                    "module": w.module,
                    "label": w.label,
                    "pair": w.pair,
                    "data_index": w.data_index,
                }
                for w in self.wires
            ],
            "ops": drawn,
            "layers": final + 1,
            "qubits": self.qubit_counts(),
            "pairs": self.pairs,
            "raw_pairs": self.raw_pairs,
        }

    def qubit_counts(self) -> dict:
        return {
            "data": self.num_data,
            "comm": self.count("comm"),
            "env": self.count("env"),
            "sacrifice": self.count("sacrifice"),
            "total": self.num_qubits,
        }

    def circuit(self) -> QuantumCircuit:
        """The unitary part as a Qiskit circuit, one qubit per wire."""
        circuit = QuantumCircuit(QuantumRegister(self.num_qubits, "q"))
        for op in self.ops:
            getattr(circuit, op.name)(*op.params, *op.wires)
        return circuit

    def backend_circuit(self) -> QuantumCircuit:
        """Basis-gate circuit that ends with measurements only.

        Data bits go to register ``c`` and distillation flags to ``f``, two
        bits per distilled pair; a shot is kept when each pair of flag bits
        agrees.
        """
        if self.num_qubits > MAX_BACKEND_QUBITS:
            raise ValueError(
                f"circuit needs {self.num_qubits} qubits, the backend limit is {MAX_BACKEND_QUBITS}"
            )
        circuit = transpile(self.circuit(), basis_gates=BASIS, optimization_level=1)
        circuit.add_register(ClassicalRegister(self.num_data, "c"))
        circuit.measure(range(self.num_data), range(self.num_data))
        if self.flags:
            circuit.add_register(ClassicalRegister(2 * len(self.flags), "f"))
            for k, (a2, b2) in enumerate(self.flags):
                circuit.measure(a2, self.num_data + 2 * k)
                circuit.measure(b2, self.num_data + 2 * k + 1)
        return circuit


def qubit_cost(num_data: int, pairs: int, q: float = 0.0, distill: bool = False) -> int:
    """Total qubits of a distributed circuit: data, comm, environment, sacrifice."""
    raw = pairs * (2 if distill else 1)
    return num_data + 2 * raw + (2 * raw if q > 0 else 0)


def distribute(
    gates: Sequence[Gate],
    assignment: Sequence[int],
    bursts: Sequence[Burst],
    q: float = 0.0,
    distill: bool = False,
    drop: tuple[str, int] | None = None,
) -> Distributed:
    """Replace every cross gate by its teleported version.

    ``q`` is the link error of every raw pair and ``distill`` spends two raw
    pairs per burst. ``drop=("x", k)`` or ``("z", k)`` leaves out one
    correction of burst ``k``; it exists to build deliberately broken circuits
    for negative controls.
    """
    q = link.check_error_rate(q)
    n = len(assignment)
    wires = [Wire(i, "data", assignment[i], f"q{i}", data_index=i) for i in range(n)]
    flags: list[tuple[int, int]] = []
    prepare: dict[int, list[Op]] = {}
    comm: dict[int, tuple[int, int]] = {}

    def add(kind: str, module: int | None, label: str, pair: int) -> int:
        wires.append(Wire(len(wires), kind, module, label, pair=pair))
        return wires[-1].id

    for burst in bursts:
        k, here, there = burst.id, burst.control_module, 1 - burst.control_module
        a, b = add("comm", here, f"a{k}", k), add("comm", there, f"b{k}", k)
        ops = link.bell_pair(a, b, k)
        if q > 0:
            ops += link.noise(b, add("env", None, f"e{k}x", k), add("env", None, f"e{k}z", k), q, k)
        if distill:
            a2, b2 = add("sacrifice", here, f"a{k}'", k), add("sacrifice", there, f"b{k}'", k)
            ops += link.bell_pair(a2, b2, k)
            if q > 0:
                env = add("env", None, f"e{k}x'", k), add("env", None, f"e{k}z'", k)
                ops += link.noise(b2, env[0], env[1], q, k)
            ops += link.distill(a, b, a2, b2, k)
            flags.append((a2, b2))
        prepare[k] = ops
        comm[k] = (a, b)

    owner = {i: burst for burst in bursts for i in burst.gate_indices}
    ops: list[Op] = []
    for gate in gates:
        burst = owner.get(gate.i)
        if burst is None:
            ops.append(Op(gate.name, gate.qubits, gate.params, role="local", gate=gate.i))
            continue
        k, c = burst.id, burst.control
        a, b = comm[k]
        if gate.i == min(burst.gate_indices):
            ops += prepare[k]
            ops.append(Op("cx", (c, a), role="cat", pair=k))
            if drop != ("x", k):
                ops.append(Op("cx", (a, b), role="classical", pair=k))
        other = gate.qubits[1] if gate.qubits[0] == c else gate.qubits[0]
        ops.append(Op(gate.name, (b, other), role="remote", pair=k, gate=gate.i))
        if gate.i == max(burst.gate_indices):
            ops.append(Op("h", (b,), role="uncat", pair=k))
            if drop != ("z", k):
                ops.append(Op("cz", (b, c), role="classical", pair=k))

    return Distributed(
        wires=wires,
        ops=ops,
        num_data=n,
        pairs=len(bursts),
        raw_pairs=len(bursts) * (2 if distill else 1),
        flags=flags,
    )


def monolithic(gates: Sequence[Gate], num_qubits: int) -> Distributed:
    """The original circuit in the same container, with no link at all."""
    wires = [Wire(i, "data", 0, f"q{i}", data_index=i) for i in range(num_qubits)]
    ops = [Op(g.name, g.qubits, g.params, role="local", gate=g.i) for g in gates]
    return Distributed(wires=wires, ops=ops, num_data=num_qubits, pairs=0, raw_pairs=0)

