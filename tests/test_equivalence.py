"""With a perfect link the distributed circuit equals the original on the data qubits."""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector, partial_trace, state_fidelity

from helpers import random_case
from seam import algorithms, build, lower, partition, schedule, verify

TOLERANCE = 1e-9
RANDOM_SEEDS = range(240)
SIMULABLE = 20


def worst_fidelity(gates, assignment, reuse, trials=4, seed=0):
    bursts = schedule.schedule(gates, assignment, reuse=reuse)
    schedule.validate(gates, assignment, bursts)
    dist = build.distribute(gates, assignment, bursts)
    assert dist.num_qubits == len(assignment) + 2 * len(bursts)
    inputs = verify.random_inputs(len(assignment), trials, np.random.default_rng(seed))
    return float(verify.fidelities(gates, dist, inputs).min())


@pytest.mark.parametrize("reuse", [True, False], ids=["reuse", "no-reuse"])
@pytest.mark.parametrize("seed", RANDOM_SEEDS)
def test_random_circuits(seed, reuse):
    gates, assignment = random_case(seed)
    assert worst_fidelity(gates, assignment, reuse, seed=seed) > 1 - TOLERANCE


def catalog_cases():
    """Every catalog algorithm at every size, on several cuts, wherever it can be simulated."""
    cases = []
    for spec in algorithms.CATALOG.values():
        for n in range(spec.n_min, spec.n_max + 1):
            instance = algorithms.build(spec.id, n)
            gates = lower.lower(instance.circuit)
            scheduler = schedule.Scheduler(gates)
            rng = np.random.default_rng(n)
            cuts = {
                "best": partition.search(gates, n).assignment,
                "contiguous": instance.default_assignment,
                "alternating": [k % 2 for k in range(n)],
                "random": [0] + [int(m) for m in rng.integers(0, 2, n - 2)] + [1],
            }
            for label, assignment in cuts.items():
                for reuse in (True, False):
                    if n + 2 * scheduler.pairs(assignment, reuse) <= SIMULABLE:
                        tag = f"{spec.id}-{n}-{label}-{'reuse' if reuse else 'no-reuse'}"
                        cases.append(pytest.param(spec.id, n, assignment, reuse, id=tag))
    return cases


CATALOG_CASES = catalog_cases()


@pytest.mark.parametrize("algorithm,n,assignment,reuse", CATALOG_CASES)
def test_catalog_algorithms(algorithm, n, assignment, reuse):
    gates = lower.lower(algorithms.build(algorithm, n).circuit)
    assert worst_fidelity(gates, assignment, reuse) > 1 - TOLERANCE


def test_every_catalog_size_is_covered_with_and_without_reuse():
    ids = [case.id for case in CATALOG_CASES]
    for spec in algorithms.CATALOG.values():
        for n in range(spec.n_min, spec.n_max + 1):
            assert any(i.startswith(f"{spec.id}-{n}-") and i.endswith("-reuse") for i in ids)
        assert any(i.startswith(f"{spec.id}-") and i.endswith("-no-reuse") for i in ids)


def qiskit_fidelity(original, gates, assignment, reuse, seed):
    """The same check done entirely with Qiskit's simulator on the un-lowered circuit."""
    n = original.num_qubits
    rng = np.random.default_rng(seed)
    prep = QuantumCircuit(n)
    for k in range(n):
        prep.u(*rng.uniform(0, 2 * np.pi, 3), k)
    for k in range(n - 1):
        prep.cx(k, k + 1)
    bursts = schedule.schedule(gates, assignment, reuse=reuse)
    dist = build.distribute(gates, assignment, bursts)
    wide = QuantumCircuit(dist.num_qubits)
    wide.compose(prep, range(n), inplace=True)
    wide.compose(dist.circuit(), inplace=True)
    reduced = partial_trace(Statevector(wide), list(range(n, dist.num_qubits)))
    return state_fidelity(reduced, Statevector(prep.compose(original)))


@pytest.mark.parametrize("algorithm", sorted(algorithms.CATALOG))
@pytest.mark.parametrize("reuse", [True, False], ids=["reuse", "no-reuse"])
def test_catalog_defaults_with_qiskit_as_referee(algorithm, reuse):
    instance = algorithms.build(algorithm)
    gates = lower.lower(instance.circuit)
    assignment = partition.search(gates, instance.n).assignment
    assert qiskit_fidelity(instance.circuit, gates, assignment, reuse, seed=1) > 1 - TOLERANCE


@pytest.mark.parametrize("seed", range(30))
def test_random_circuits_with_qiskit_as_referee(seed):
    gates, assignment = random_case(1000 + seed)
    original = lower.to_circuit(gates, len(assignment))
    assert qiskit_fidelity(original, gates, assignment, True, seed) > 1 - TOLERANCE


@pytest.mark.parametrize("seed", range(40))
def test_only_pair_generation_and_classical_bits_cross_the_link(seed):
    gates, assignment = random_case(seed)
    dist = build.distribute(gates, assignment, schedule.schedule(gates, assignment), q=0.1, distill=True)
    for op in dist.ops:
        if dist.crosses_link(op):
            assert op.role in ("pair", "classical")
        if op.role in ("local", "remote", "cat", "uncat", "distill"):
            assert len({dist.wires[w].module for w in op.wires}) == 1


def test_proof_reports_success_and_a_failing_negative_control():
    instance = algorithms.build("qft_phase")
    gates = lower.lower(instance.circuit)
    assignment = partition.search(gates, instance.n).assignment
    proof = verify.prove(gates, assignment, schedule.schedule(gates, assignment))
    assert proof.passed and proof.trials == 16
    assert proof.fidelity_min > 1 - TOLERANCE
    assert proof.negative_control < 0.999
    assert proof.qubits == instance.n + 4
