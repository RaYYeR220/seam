"""Equivalence proof by statevector, with a negative control.

With a perfect link the distributed circuit must act on the data qubits
exactly like the original and leave the comm qubits in a product state. For
an input state ``|psi>`` the check is the fidelity

    F = <phi| tr_comm(|Psi><Psi|) |phi>

between the original output ``|phi>`` and the data-qubit marginal of the
distributed output ``|Psi>``.

The inputs are random product states pushed through a CNOT chain. Projectors
onto product states span all operators, so two channels that agree on every
such input are the same channel; and ``F`` is analytic in the input, so a
wrong circuit gives ``F < 1`` on a randomly drawn input with probability one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from . import sim
from .build import Distributed, distribute
from .lower import Gate
from .schedule import Burst

TOLERANCE = 1e-9
BROKEN_BELOW = 0.999


@dataclass(frozen=True)
class Proof:
    trials: int
    fidelity_min: float
    fidelity_mean: float
    negative_control: float | None
    passed: bool
    qubits: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Cx:
    qubits: tuple[int, int]
    name: str = "cx"
    params: tuple = ()


def random_inputs(num_qubits: int, trials: int, rng: np.random.Generator) -> np.ndarray:
    """Random product states pushed through a CNOT chain, stacked on the last axis."""
    shape = (trials, num_qubits, 2)
    single = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    single /= np.linalg.norm(single, axis=-1, keepdims=True)
    batch = np.empty((2,) * num_qubits + (trials,), dtype=complex)
    for t in range(trials):
        state = single[t, 0]
        for k in range(1, num_qubits):
            state = np.multiply.outer(state, single[t, k])
        batch[..., t] = state
    chain = [_Cx((k, k + 1)) for k in range(num_qubits - 1)]
    return sim.run(chain, num_qubits, batch)


def fidelities(gates: Sequence[Gate], dist: Distributed, inputs: np.ndarray) -> np.ndarray:
    """Per-input fidelity between original and distributed outputs on the data qubits."""
    n, total = dist.num_data, dist.num_qubits
    if dist.env or dist.flags:
        raise ValueError("the equivalence check is defined for a perfect, undistilled link")
    trials = inputs.shape[-1]
    reference = sim.run(gates, n, inputs.copy())
    wide = np.zeros((2,) * total + (trials,), dtype=complex)
    wide[(slice(None),) * n + (0,) * (total - n)] = inputs
    wide = sim.run(dist.ops, total, wide)
    overlap = np.einsum(
        "dt,dct->ct",
        reference.reshape(2**n, trials).conj(),
        wide.reshape(2**n, 2 ** (total - n), trials),
    )
    return (overlap.real**2 + overlap.imag**2).sum(axis=0)


def prove(
    gates: Sequence[Gate],
    assignment: Sequence[int],
    bursts: Sequence[Burst],
    trials: int = 16,
    seed: int = 0,
) -> Proof:
    """Check the distributed circuit against the original on random inputs.

    The negative control is the same circuit with the Z correction of the
    first burst left out; its mean fidelity must be visibly below one.
    """
    rng = np.random.default_rng(seed)
    inputs = random_inputs(len(assignment), trials, rng)
    dist = distribute(gates, assignment, bursts)
    good = fidelities(gates, dist, inputs)
    control = None
    if bursts:
        broken = distribute(gates, assignment, bursts, drop=("z", bursts[0].id))
        control = float(fidelities(gates, broken, inputs).mean())
    passed = bool(good.min() > 1 - TOLERANCE) and (control is None or control < BROKEN_BELOW)
    return Proof(
        trials=trials,
        fidelity_min=min(1.0, float(good.min())),
        fidelity_mean=min(1.0, float(good.mean())),
        negative_control=control,
        passed=passed,
        qubits=dist.num_qubits,
    )
