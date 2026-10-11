"""Lowering must preserve the unitary (up to a global phase)."""

import math

import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from seam import algorithms, lower


def lowered_equals(circuit):
    gates = lower.lower(circuit)
    assert all(g.name in lower.ONE_QUBIT | lower.TWO_QUBIT for g in gates)
    assert [g.i for g in gates] == list(range(len(gates)))
    return Operator(lower.to_circuit(gates, circuit.num_qubits)).equiv(Operator(circuit))


def build(fn, n):
    qc = QuantumCircuit(n)
    fn(qc)
    return qc


RULES = {
    "cp": (2, lambda qc: qc.cp(0.7, 0, 1)),
    "cp_reversed": (2, lambda qc: qc.cp(-1.3, 1, 0)),
    "crz": (2, lambda qc: qc.crz(0.9, 0, 1)),
    "rzz": (2, lambda qc: qc.rzz(0.4, 1, 0)),
    "swap": (2, lambda qc: qc.swap(0, 1)),
    "cy": (2, lambda qc: qc.cy(0, 1)),
    "ccz": (3, lambda qc: qc.ccz(0, 1, 2)),
    "ccz_permuted": (3, lambda qc: qc.ccz(2, 0, 1)),
    "ccx": (3, lambda qc: qc.ccx(0, 1, 2)),
    "ccx_permuted": (3, lambda qc: qc.ccx(1, 2, 0)),
    "u": (1, lambda qc: qc.u(0.3, 0.5, 0.7, 0)),
    "ch_by_definition": (2, lambda qc: qc.ch(0, 1)),
    "cswap_by_definition": (3, lambda qc: qc.cswap(0, 1, 2)),
    "ryy_by_definition": (2, lambda qc: qc.ryy(0.6, 0, 1)),
}


@pytest.mark.parametrize("name", sorted(RULES))
def test_rule_preserves_unitary(name):
    n, fn = RULES[name]
    assert lowered_equals(build(fn, n))


CATALOG_CASES = [
    (a.id, n) for a in algorithms.CATALOG.values() for n in range(a.n_min, min(a.n_max, 7) + 1)
]


@pytest.mark.parametrize("algorithm,n", CATALOG_CASES)
def test_catalog_lowering_preserves_unitary(algorithm, n):
    assert lowered_equals(algorithms.build(algorithm, n).circuit)


def test_ccz_never_uses_first_qubit_as_target():
    gates = lower.lower(build(lambda qc: qc.ccz(0, 1, 2), 3))
    assert all(g.diagonal_on(0) for g in gates if 0 in g.qubits)


def test_measurement_is_rejected():
    qc = QuantumCircuit(1, 1)
    qc.measure(0, 0)
    with pytest.raises(ValueError):
        lower.lower(qc)


def test_barriers_are_dropped():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.barrier()
    qc.cx(0, 1)
    assert [g.name for g in lower.lower(qc)] == ["h", "cx"]


def test_diagonal_classification():
    gates = lower.from_steps(
        [("rz", [0], [0.1]), ("h", [0]), ("cx", [0, 1]), ("cz", [0, 1]), ("rx", [1], [math.pi])]
    )
    assert gates[0].diagonal_on(0) and not gates[1].diagonal_on(0)
    assert gates[2].diagonal_on(0) and not gates[2].diagonal_on(1)
    assert gates[3].diagonal_on(0) and gates[3].diagonal_on(1)
    assert not gates[4].diagonal_on(1)


def test_asap_layers():
    assert lower.asap_layers(3, [(0,), (1,), (0, 1), (2,), (1, 2)]) == [0, 0, 1, 0, 2]
