"""The photonic link: Bell pairs, a Pauli noise model and 2->1 distillation.

Noise model. After a pair ``(a, b)`` is made, half ``b`` suffers an X flip
with probability ``q`` and, independently, a Z flip with probability ``q``.
Each flip is driven coherently by its own environment qubit that is never
measured, which is the same thing as the classical mixture. The pair is then
Bell-diagonal with weights

    Phi+ : (1-q)^2    Psi+ : q(1-q)    Phi- : q(1-q)    Psi- : q^2

so its fidelity is ``(1-q)^2``.

Distillation. Two raw pairs are rotated by ``rx(pi/2)`` on the ``a`` side and
``rx(-pi/2)`` on the ``b`` side (this keeps Phi+ and swaps Phi- with Psi-),
then a bilateral CNOT copies bit-flip errors onto the second pair, whose two
halves are measured. The first pair is kept when the two outcomes agree.
Single X and single Z errors are both caught, so the kept pair has infidelity
of order ``q^2``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ROLES = ("local", "pair", "noise", "distill", "cat", "remote", "uncat", "classical", "measure")


@dataclass(frozen=True)
class Op:
    """One operation of a distributed circuit, tagged with what it is for."""

    name: str
    wires: tuple[int, ...]
    params: tuple[float, ...] = ()
    role: str = "local"
    pair: int | None = None
    gate: int | None = None

    @property
    def qubits(self) -> tuple[int, ...]:
        return self.wires


def check_error_rate(q: float) -> float:
    q = float(q)
    if not 0.0 <= q <= 0.5:
        raise ValueError("link error q must be between 0 and 0.5")
    return q


def flip_angle(q: float) -> float:
    """Rotation that leaves an environment qubit in |1> with probability ``q``."""
    return 2.0 * math.asin(math.sqrt(q))


def bell_pair(a: int, b: int, pair: int) -> list[Op]:
    """Prepare (|00> + |11>)/sqrt(2) on ``(a, b)``."""
    return [Op("h", (a,), role="pair", pair=pair), Op("cx", (a, b), role="pair", pair=pair)]


def noise(b: int, env_x: int, env_z: int, q: float, pair: int) -> list[Op]:
    """Independent X and Z flips on ``b``, each with probability ``q``."""
    theta = flip_angle(q)
    return [
        Op("ry", (env_x,), (theta,), role="noise", pair=pair),
        Op("cx", (env_x, b), role="noise", pair=pair),
        Op("ry", (env_z,), (theta,), role="noise", pair=pair),
        Op("cz", (env_z, b), role="noise", pair=pair),
    ]


def distill(a: int, b: int, a2: int, b2: int, pair: int) -> list[Op]:
    """Unitary part of the 2->1 protocol; ``a2`` and ``b2`` are measured later."""
    quarter = math.pi / 2
    return [
        Op("rx", (a,), (quarter,), role="distill", pair=pair),
        Op("rx", (b,), (-quarter,), role="distill", pair=pair),
        Op("rx", (a2,), (quarter,), role="distill", pair=pair),
        Op("rx", (b2,), (-quarter,), role="distill", pair=pair),
        Op("cx", (a, a2), role="distill", pair=pair),
        Op("cx", (b, b2), role="distill", pair=pair),
    ]


def pair_fidelity(q: float) -> float:
    """Fidelity of a raw pair with the ideal Bell state."""
    return (1.0 - q) ** 2


def bell_weights(q: float) -> tuple[float, float, float, float]:
    """Weights of a raw pair on (Phi+, Psi+, Phi-, Psi-)."""
    return ((1 - q) ** 2, q * (1 - q), q * (1 - q), q * q)


def distilled(q: float) -> tuple[float, float]:
    """Fidelity of the kept pair and the probability of keeping it.

    After the rotations the bit-flip-type weight of a pair is ``2q(1-q)`` and
    the undetectable phase-type weight is ``q^2``. The pair is kept when both
    or neither of the two pairs carries a bit flip, and it is correct when
    neither does and their phase errors cancel.
    """
    flip = 2 * q * (1 - q)
    kept = (1 - flip) ** 2 + flip**2
    return ((1 - q) ** 4 + q**4) / kept, kept


DISTILLATION_LIMIT = 1.0 - math.sqrt(0.5)
"""Link error at which a raw pair reaches fidelity 1/2 and distillation stops helping."""
