"""The statevector kernel must agree with Qiskit's own simulator."""

import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from seam import lower, sim

ONE_QUBIT = [
    ("id", 0), ("h", 0), ("x", 0), ("y", 0), ("z", 0), ("s", 0), ("sdg", 0), ("t", 0),
    ("tdg", 0), ("sx", 0), ("sxdg", 0), ("rx", 1), ("ry", 1), ("rz", 1), ("p", 1), ("u", 3),
]


def random_steps(rng, n, length):
    steps = []
    for _ in range(length):
        if rng.random() < 0.35 and n > 1:
            a, b = (int(q) for q in rng.choice(n, 2, replace=False))
            steps.append((("cx", "cz")[int(rng.integers(2))], [a, b]))
        else:
            name, arity = ONE_QUBIT[int(rng.integers(len(ONE_QUBIT)))]
            steps.append((name, [int(rng.integers(n))], list(rng.uniform(-np.pi, np.pi, arity))))
    return steps


@pytest.mark.parametrize("seed", range(40))
def test_kernel_matches_qiskit_statevector(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 7))
    gates = lower.from_steps(random_steps(rng, n, 30))
    ours = sim.to_vector(sim.run(gates, n))
    theirs = Statevector(lower.to_circuit(gates, n)).data
    assert np.allclose(ours, theirs, atol=1e-12)


@pytest.mark.parametrize("name,arity", ONE_QUBIT)
def test_one_qubit_matrices_match_qiskit(name, arity):
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Operator

    params = [0.37, -1.1, 2.3][:arity]
    qc = QuantumCircuit(1)
    getattr(qc, name)(*params, 0)
    assert np.allclose(sim.matrix(name, params), Operator(qc).data, atol=1e-12)


def test_probabilities_follow_requested_order():
    gates = lower.from_steps([("x", [0]), ("h", [2]), ("cx", [2, 1])])
    state = sim.run(gates, 3)
    table = sim.probabilities(state, [2, 0], 3)
    assert table.shape == (2, 2)
    assert np.allclose(table, [[0, 0.5], [0, 0.5]])
    assert np.allclose(sim.probabilities(state, [0, 1, 2], 3).sum(), 1.0)


def test_batched_states_evolve_independently():
    rng = np.random.default_rng(5)
    gates = lower.from_steps(random_steps(rng, 3, 25))
    batch = rng.normal(size=(2, 2, 2, 4)) + 1j * rng.normal(size=(2, 2, 2, 4))
    together = sim.run(gates, 3, batch.copy())
    for t in range(4):
        alone = sim.run(gates, 3, batch[..., t].copy())
        assert np.allclose(together[..., t], alone, atol=1e-12)
