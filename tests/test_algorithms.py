"""Catalog circuits return their stated answers."""

import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from seam import algorithms

SIZES = [(a.id, n) for a in algorithms.CATALOG.values() for n in range(a.n_min, a.n_max + 1)]


def target_probability(instance):
    probabilities = Statevector(instance.circuit).probabilities_dict()
    return sum(probabilities.get(t, 0.0) for t in instance.targets)


@pytest.mark.parametrize("n", range(3, 9))
def test_ghz(n):
    instance = algorithms.build("ghz", n)
    probabilities = Statevector(instance.circuit).probabilities_dict()
    assert abs(probabilities["0" * n] - 0.5) < 1e-12 and abs(probabilities["1" * n] - 0.5) < 1e-12
    assert instance.classical_guess == 2 / 2**n


@pytest.mark.parametrize("secret", ["00000", "10110", "11111", "00001", "10000"])
def test_bernstein_vazirani_returns_the_secret(secret):
    instance = algorithms.build("bv", 6, {"secret": secret})
    assert instance.targets == ["0" + secret]
    assert abs(target_probability(instance) - 1) < 1e-12
    assert instance.classical_guess == 1 / 32


@pytest.mark.parametrize("n", range(4, 8))
def test_phase_estimation_reads_every_phase_exactly(n):
    for value in range(2 ** (n - 1)):
        bits = format(value, f"0{n - 1}b")
        instance = algorithms.build("qft_phase", n, {"phase": bits})
        assert instance.targets == ["1" + bits]
        assert abs(target_probability(instance) - 1) < 1e-9


@pytest.mark.parametrize("marked", [format(v, "03b") for v in range(8)])
@pytest.mark.parametrize("iterations,expected", [(1, 25 / 32), (2, 121 / 128)])
def test_grover_success_probability(marked, iterations, expected):
    instance = algorithms.build("grover", 3, {"marked": marked, "iterations": iterations})
    assert instance.targets == [marked]
    assert abs(target_probability(instance) - expected) < 1e-12


def test_four_qubit_controlled_z_is_correct():
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Operator

    qc = QuantumCircuit(4)
    algorithms._mcz(qc, [0, 1, 2, 3])
    expected = np.eye(16)
    expected[15, 15] = -1
    assert Operator(qc).equiv(Operator(expected))


def cut_value(bits):
    return sum(bits[k] != bits[(k + 1) % len(bits)] for k in range(len(bits)))


@pytest.mark.parametrize("n", range(4, 9))
def test_qaoa_ring_beats_random_guessing(n):
    instance = algorithms.build("qaoa_ring", n)
    assert instance.targets is None
    probabilities = Statevector(instance.circuit).probabilities_dict()
    expected_cut = sum(p * cut_value(bits) for bits, p in probabilities.items())
    assert expected_cut > 0.5 * n + 1e-6
    if n >= 5:
        assert abs(expected_cut - 0.75 * n) < 1e-9


@pytest.mark.parametrize("algorithm,n", SIZES)
def test_defaults_build_at_every_size(algorithm, n):
    instance = algorithms.build(algorithm, n)
    assert instance.circuit.num_qubits == n
    assert len(instance.default_assignment) == n
    assert 0 < sum(instance.default_assignment) < n
    if instance.targets is not None:
        assert all(len(t) == n for t in instance.targets)
        assert 0 < instance.classical_guess < 1


@pytest.mark.parametrize(
    "algorithm,n,params",
    [
        ("nope", None, None),
        ("ghz", 2, None),
        ("ghz", 9, None),
        ("ghz", 4.5, None),
        ("ghz", True, None),
        ("bv", 6, {"secret": "101"}),
        ("bv", 6, {"secret": "1011x"}),
        ("bv", 6, {"secret": 10110}),
        ("bv", 6, {"hidden": "10110"}),
        ("grover", 3, {"iterations": 5}),
        ("grover", 3, {"iterations": "2"}),
        ("grover", 4, None),
    ],
)
def test_bad_requests_raise_value_error(algorithm, n, params):
    with pytest.raises(ValueError):
        algorithms.build(algorithm, n, params)


def test_catalog_descriptions_are_complete():
    for spec in algorithms.CATALOG.values():
        described = spec.describe()
        assert spec.n_min <= described["n_default"] <= spec.n_max
        assert described["blurb"] and described["name"]
        for param in described["params"]:
            assert param["type"] in ("bits", "int")
            if param["type"] == "bits":
                assert len(param["default"]) == spec.n_default + param["length_offset"]
