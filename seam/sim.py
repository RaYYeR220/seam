"""A small statevector kernel for lowered gate lists.

The state is a tensor with one axis of length two per qubit (axis ``k`` is
qubit ``k``). Any trailing axes are left alone, so a batch of states can be
evolved in one pass. Gates are applied in place.
"""

from __future__ import annotations

import cmath
import math
from typing import Iterable, Sequence

import numpy as np

_SQRT_HALF = math.sqrt(0.5)


def _phases(name: str, params: Sequence[float]) -> tuple[complex, complex] | None:
    if name == "id":
        return (1, 1)
    if name == "z":
        return (1, -1)
    if name == "s":
        return (1, 1j)
    if name == "sdg":
        return (1, -1j)
    if name == "t":
        return (1, cmath.exp(0.25j * math.pi))
    if name == "tdg":
        return (1, cmath.exp(-0.25j * math.pi))
    if name == "rz":
        return (cmath.exp(-0.5j * params[0]), cmath.exp(0.5j * params[0]))
    if name == "p":
        return (1, cmath.exp(1j * params[0]))
    return None


def matrix(name: str, params: Sequence[float] = ()) -> np.ndarray:
    """2x2 matrix of a one-qubit gate."""
    phases = _phases(name, params)
    if phases is not None:
        return np.diag(np.array(phases, dtype=complex))
    if name == "h":
        return np.array([[1, 1], [1, -1]], dtype=complex) * _SQRT_HALF
    if name == "x":
        return np.array([[0, 1], [1, 0]], dtype=complex)
    if name == "y":
        return np.array([[0, -1j], [1j, 0]], dtype=complex)
    if name == "sx":
        return 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]])
    if name == "sxdg":
        return 0.5 * np.array([[1 - 1j, 1 + 1j], [1 + 1j, 1 - 1j]])
    if name in ("rx", "ry"):
        c, s = math.cos(params[0] / 2), math.sin(params[0] / 2)
        if name == "rx":
            return np.array([[c, -1j * s], [-1j * s, c]])
        return np.array([[c, -s], [s, c]], dtype=complex)
    if name == "u":
        theta, phi, lam = params
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return np.array(
            [
                [c, -cmath.exp(1j * lam) * s],
                [cmath.exp(1j * phi) * s, cmath.exp(1j * (phi + lam)) * c],
            ]
        )
    raise ValueError(f"unknown one-qubit gate '{name}'")


def _sel(axis: int, value: int) -> tuple:
    return (slice(None),) * axis + (value,)


def _sel2(first: int, first_value: int, second: int, second_value: int) -> tuple:
    index: list = [slice(None)] * (max(first, second) + 1)
    index[first], index[second] = first_value, second_value
    return tuple(index)


def zero_state(num_qubits: int) -> np.ndarray:
    state = np.zeros((2,) * num_qubits, dtype=complex)
    state[(0,) * num_qubits] = 1.0
    return state


def _swap(state: np.ndarray, first: tuple, second: tuple) -> None:
    kept = np.copy(state[first])
    state[first] = state[second]
    state[second] = kept


def apply(state: np.ndarray, name: str, qubits: Sequence[int], params: Sequence[float] = ()) -> None:
    """Apply one gate of the lowered set to ``state`` in place."""
    if name == "cx":
        c, t = qubits
        _swap(state, _sel2(c, 1, t, 0), _sel2(c, 1, t, 1))
        return
    if name == "cz":
        a, b = qubits
        state[_sel2(a, 1, b, 1)] *= -1
        return
    (k,) = qubits
    zero, one = _sel(k, 0), _sel(k, 1)
    phases = _phases(name, params)
    if phases is not None:
        if phases[0] != 1:
            state[zero] *= phases[0]
        if phases[1] != 1:
            state[one] *= phases[1]
        return
    if name == "x":
        _swap(state, zero, one)
        return
    m = matrix(name, params)
    lower_half = np.copy(state[zero])
    upper_half = state[one]
    state[zero] = m[0, 0] * lower_half + m[0, 1] * upper_half
    state[one] = m[1, 0] * lower_half + m[1, 1] * upper_half


def run(ops: Iterable, num_qubits: int, state: np.ndarray | None = None) -> np.ndarray:
    """Evolve ``state`` (default all zeros) through ``ops``.

    Each op needs ``name``, ``qubits`` and ``params`` attributes. The state
    passed in is modified and returned.
    """
    if state is None:
        state = zero_state(num_qubits)
    for op in ops:
        apply(state, op.name, op.qubits, op.params)
    return state


def probabilities(state: np.ndarray, qubits: Sequence[int], num_qubits: int) -> np.ndarray:
    """Joint outcome probabilities of ``qubits``, one axis each, in the order given.

    Trailing batch axes of ``state`` are kept at the end.
    """
    weights = state.real**2 + state.imag**2
    wanted = set(qubits)
    drop = tuple(k for k in range(num_qubits) if k not in wanted)
    weights = weights.sum(axis=drop) if drop else weights
    remaining = sorted(qubits)
    order = [remaining.index(k) for k in qubits]
    extra = list(range(len(qubits), weights.ndim))
    return weights.transpose(order + extra)


def to_vector(state: np.ndarray) -> np.ndarray:
    """Flatten to Qiskit's little-endian amplitude ordering."""
    n = state.ndim
    return state.transpose(tuple(range(n - 1, -1, -1))).reshape(-1)
