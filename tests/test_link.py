"""Link model: raw pair fidelity and the 2->1 distillation map."""

import itertools
import math

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector, partial_trace

from seam import link, sim

QS = [0.0, 0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]

I2 = np.eye(2)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
PHI_PLUS = np.array([1, 0, 0, 1], dtype=complex) / math.sqrt(2)


def bell_state(x_flip, z_flip):
    """Phi+ with X^x Z^z applied to the second qubit."""
    op = np.linalg.matrix_power(X, x_flip) @ np.linalg.matrix_power(Z, z_flip)
    return np.kron(I2, op) @ PHI_PLUS


def raw_pair_density(q):
    """Density matrix of a raw pair, written down directly from the noise model."""
    rho = np.zeros((4, 4), dtype=complex)
    for x_flip, z_flip in itertools.product((0, 1), repeat=2):
        weight = (q if x_flip else 1 - q) * (q if z_flip else 1 - q)
        state = bell_state(x_flip, z_flip)
        rho += weight * np.outer(state, state.conj())
    return rho


def simulated_pair_density(q):
    """Density matrix of (a, b) from the package's own operations, environment traced out."""
    ops = link.bell_pair(0, 1, 0) + link.noise(1, 2, 3, q, 0)
    state = sim.run(ops, 4).reshape(4, 4)
    return state @ state.conj().T


@pytest.mark.parametrize("q", QS)
def test_pair_fidelity_is_one_minus_q_squared(q):
    rho = simulated_pair_density(q)
    fidelity = float(np.real(PHI_PLUS.conj() @ rho @ PHI_PLUS))
    assert abs(fidelity - (1 - q) ** 2) < 1e-9
    assert abs(link.pair_fidelity(q) - (1 - q) ** 2) < 1e-12


@pytest.mark.parametrize("q", QS)
def test_noise_ops_give_the_stated_bell_diagonal_state(q):
    assert np.allclose(simulated_pair_density(q), raw_pair_density(q), atol=1e-12)
    weights = [
        float(np.real(bell_state(x, z).conj() @ raw_pair_density(q) @ bell_state(x, z)))
        for x, z in [(0, 0), (1, 0), (0, 1), (1, 1)]
    ]
    assert np.allclose(weights, link.bell_weights(q), atol=1e-12)


@pytest.mark.parametrize("q", [0.05, 0.2])
def test_pair_fidelity_with_qiskit_as_referee(q):
    qc = QuantumCircuit(4)
    for op in link.bell_pair(0, 1, 0) + link.noise(1, 2, 3, q, 0):
        getattr(qc, op.name)(*op.params, *op.wires)
    rho = partial_trace(Statevector(qc), [2, 3]).data
    referee = np.array([1, 0, 0, 1]) / math.sqrt(2)
    assert abs(np.real(referee.conj() @ rho @ referee) - (1 - q) ** 2) < 1e-9


def rx(theta):
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return np.array([[c, -1j * s], [-1j * s, c]])


def cnot(control, target, n):
    """CNOT on an n-qubit register whose first tensor factor is qubit 0."""
    dim = 2**n
    out = np.zeros((dim, dim))
    for basis in range(dim):
        bits = [(basis >> (n - 1 - k)) & 1 for k in range(n)]
        if bits[control]:
            bits[target] ^= 1
        out[sum(b << (n - 1 - k) for k, b in enumerate(bits)), basis] = 1
    return out


def derived_distillation(q):
    """Fidelity and success probability from explicit density matrices.

    Register order is (a, b, a2, b2). Nothing here uses the package.
    """
    rho = np.kron(raw_pair_density(q), raw_pair_density(q))
    rotate = np.kron(np.kron(rx(math.pi / 2), rx(-math.pi / 2)), np.kron(rx(math.pi / 2), rx(-math.pi / 2)))
    unitary = cnot(1, 3, 4) @ cnot(0, 2, 4) @ rotate
    rho = unitary @ rho @ unitary.conj().T
    kept = np.zeros((4, 4), dtype=complex)
    for flag in (0, 1):
        projector = np.zeros((4, 1))
        projector[flag * 3, 0] = 1
        bra = np.kron(np.eye(4), projector.T)
        kept += bra @ rho @ bra.conj().T
    probability = float(np.real(np.trace(kept)))
    kept /= probability
    return float(np.real(PHI_PLUS.conj() @ kept @ PHI_PLUS)), probability, kept


def dejmps_map(a, b, c, d):
    """One DEJMPS round on Bell-diagonal weights (A, B, C, D) = (Phi+, Psi-, Psi+, Phi-)."""
    norm = (a + b) ** 2 + (c + d) ** 2
    return ((a * a + b * b) / norm, 2 * c * d / norm, (c * c + d * d) / norm, 2 * a * b / norm), norm


@pytest.mark.parametrize("q", QS)
def test_distillation_matches_the_dejmps_map(q):
    fidelity, probability, kept = derived_distillation(q)
    phi_plus, psi_plus, phi_minus, psi_minus = link.bell_weights(q)
    (a_out, b_out, c_out, d_out), norm = dejmps_map(phi_plus, psi_minus, psi_plus, phi_minus)
    assert abs(fidelity - a_out) < 1e-9
    assert abs(probability - norm) < 1e-9
    closed_fidelity, closed_kept = link.distilled(q)
    assert abs(closed_fidelity - fidelity) < 1e-9
    assert abs(closed_kept - probability) < 1e-9
    spectrum = sorted(np.linalg.eigvalsh(kept))
    assert np.allclose(spectrum, sorted([a_out, b_out, c_out, d_out]), atol=1e-9)


@pytest.mark.parametrize("q", QS)
def test_distillation_ops_reproduce_the_derivation(q):
    ops = link.bell_pair(0, 1, 0) + link.bell_pair(2, 3, 0) + link.distill(0, 1, 2, 3, 0)
    total = 4
    if q > 0:
        ops = (
            link.bell_pair(0, 1, 0)
            + link.noise(1, 4, 5, q, 0)
            + link.bell_pair(2, 3, 0)
            + link.noise(3, 6, 7, q, 0)
            + link.distill(0, 1, 2, 3, 0)
        )
        total = 8
    state = sim.run(ops, total).reshape(4, 4, -1)
    kept = sum(state[:, flag] @ state[:, flag].conj().T for flag in (0, 3))
    probability = float(np.real(np.trace(kept)))
    fidelity = float(np.real(PHI_PLUS.conj() @ kept @ PHI_PLUS)) / probability
    expected_fidelity, expected_probability, _ = derived_distillation(q)
    assert abs(fidelity - expected_fidelity) < 1e-9
    assert abs(probability - expected_probability) < 1e-9


def test_distillation_removes_first_order_errors():
    for q in (1e-3, 1e-2):
        fidelity, _ = link.distilled(q)
        assert 1 - fidelity < 7 * q * q
        assert 1 - link.pair_fidelity(q) > 1.9 * q


def test_distillation_helps_exactly_while_the_pair_is_entangled():
    limit = link.DISTILLATION_LIMIT
    assert limit < 0.5
    assert abs(link.pair_fidelity(limit) - 0.5) < 1e-12
    assert abs(link.distilled(limit)[0] - 0.5) < 1e-12
    for q in np.linspace(0.001, limit - 0.001, 60):
        assert link.distilled(q)[0] > link.pair_fidelity(q)
    for q in np.linspace(limit + 0.001, 0.499, 60):
        assert link.distilled(q)[0] < link.pair_fidelity(q)


def test_error_rate_is_validated():
    for bad in (-0.1, 0.6):
        with pytest.raises(ValueError):
            link.check_error_rate(bad)
