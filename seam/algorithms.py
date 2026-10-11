"""Catalog of demo circuits, each with its ideal answer where one exists.

Bitstrings follow Qiskit's convention: the leftmost character is the highest
qubit. Two-qubit gates are written so that the qubit that only ever acts as a
control comes first, which is what lets one Bell pair serve several of them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from qiskit import QuantumCircuit


@dataclass(frozen=True)
class Param:
    id: str
    label: str
    type: str
    default: Callable[[int], object]
    length_offset: int | None = None
    minimum: int | None = None
    maximum: int | None = None

    def describe(self, n: int) -> dict:
        out = {"id": self.id, "label": self.label, "type": self.type, "default": self.default(n)}
        if self.type == "bits":
            out["length_offset"] = self.length_offset
        else:
            out["min"], out["max"] = self.minimum, self.maximum
        return out


@dataclass(frozen=True)
class Instance:
    """A concrete circuit of the catalog.

    ``targets`` are the bitstrings an ideal run returns (``None`` when the
    output is a distribution rather than an answer) and ``classical_guess`` is
    the chance of hitting one of them without running anything.
    """

    algorithm: str
    n: int
    params: dict
    circuit: QuantumCircuit
    targets: list[str] | None
    classical_guess: float | None
    default_assignment: list[int]


@dataclass(frozen=True)
class Algorithm:
    id: str
    name: str
    blurb: str
    n_default: int
    n_min: int
    n_max: int
    builder: Callable[[int, dict], tuple[QuantumCircuit, list[str] | None, float | None]]
    params: tuple[Param, ...] = field(default=())

    def describe(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "blurb": self.blurb,
            "n_default": self.n_default,
            "n_min": self.n_min,
            "n_max": self.n_max,
            "params": [p.describe(self.n_default) for p in self.params],
        }


def _pattern(length: int) -> str:
    return ("1011010" * 3)[:length]


def _ghz(n: int, params: dict) -> tuple[QuantumCircuit, list[str] | None, float | None]:
    qc = QuantumCircuit(n)
    qc.h(0)
    for k in range(n - 1):
        qc.cx(k, k + 1)
    return qc, ["0" * n, "1" * n], 2 / 2**n


def _bv(n: int, params: dict) -> tuple[QuantumCircuit, list[str] | None, float | None]:
    """Bernstein-Vazirani: one query returns the hidden string.

    Inputs are qubits ``0..n-2`` and the last qubit is the oracle ancilla,
    returned to |0> at the end so the whole register has one answer.
    """
    secret = params["secret"]
    inputs, ancilla = n - 1, n - 1
    qc = QuantumCircuit(n)
    qc.x(ancilla)
    qc.h(range(n))
    for k in range(inputs):
        if secret[inputs - 1 - k] == "1":
            qc.cx(k, ancilla)
    qc.h(range(n))
    qc.x(ancilla)
    return qc, ["0" + secret], 1 / 2**inputs


def _qft_phase(n: int, params: dict) -> tuple[QuantumCircuit, list[str] | None, float | None]:
    """Phase estimation of ``p(2 pi phi)`` on its eigenstate |1>.

    ``phi = 0.b1 b2 ... bt`` in binary with ``t = n - 1`` counting qubits, so
    the counting register reads the bits of ``phi`` exactly. Counting qubit
    ``k`` picks up the phase of ``U^(2^(t-1-k))``, which makes the inverse
    Fourier transform swap-free.
    """
    bits = params["phase"]
    t, eigen = n - 1, n - 1
    phi = int(bits, 2) / 2**t
    qc = QuantumCircuit(n)
    qc.x(eigen)
    qc.h(range(t))
    for k in range(t):
        angle = (2 * math.pi * phi * 2 ** (t - 1 - k)) % (2 * math.pi)
        if angle:
            qc.cp(angle, eigen, k)
    for j in range(t):
        for l in range(j):
            qc.cp(-math.pi / 2 ** (j - l), l, j)
        qc.h(j)
    return qc, ["1" + bits], 1 / 2**t


def _mcz(qc: QuantumCircuit, qubits: list[int]) -> None:
    """Z controlled on all but one of ``qubits`` (symmetric in all of them)."""
    if len(qubits) == 2:
        qc.cz(*qubits)
    elif len(qubits) == 3:
        qc.ccz(*qubits)
    elif len(qubits) == 4:
        a, b, c, d = qubits
        quarter = math.pi / 2
        qc.cp(quarter, c, d)
        qc.ccx(a, b, c)
        qc.cp(-quarter, c, d)
        qc.ccx(a, b, c)
        qc.cp(quarter / 2, b, d)
        qc.cx(a, b)
        qc.cp(-quarter / 2, b, d)
        qc.cx(a, b)
        qc.cp(quarter / 2, a, d)
    else:
        raise ValueError("multi-controlled Z is implemented for up to four qubits")


def _grover(n: int, params: dict) -> tuple[QuantumCircuit, list[str] | None, float | None]:
    """Grover search for one marked bitstring among ``2^n``."""
    marked, iterations = params["marked"], params["iterations"]
    qubits = list(range(n))
    zeros = [k for k in qubits if marked[n - 1 - k] == "0"]
    qc = QuantumCircuit(n)
    qc.h(qubits)
    for _ in range(iterations):
        if zeros:
            qc.x(zeros)
        _mcz(qc, qubits)
        if zeros:
            qc.x(zeros)
        qc.h(qubits)
        qc.x(qubits)
        _mcz(qc, qubits)
        qc.x(qubits)
        qc.h(qubits)
    return qc, [marked], 1 / 2**n


QAOA_GAMMA = math.pi / 4
QAOA_BETA = math.pi / 8


def _qaoa_ring(n: int, params: dict) -> tuple[QuantumCircuit, list[str] | None, float | None]:
    """Depth-one QAOA for MaxCut on a ring, at the angles optimal for long rings."""
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for k in range(n):
        qc.rzz(-QAOA_GAMMA, k, (k + 1) % n)
    qc.rx(2 * QAOA_BETA, range(n))
    return qc, None, None


CATALOG: dict[str, Algorithm] = {
    a.id: a
    for a in (
        Algorithm(
            "ghz",
            "GHZ state",
            "All qubits agree: the chain of CNOTs crosses the cut exactly once.",
            6,
            3,
            8,
            _ghz,
        ),
        Algorithm(
            "bv",
            "Bernstein-Vazirani",
            "One oracle query reveals a hidden bit string; every 1 is a CNOT onto the ancilla.",
            6,
            3,
            7,
            _bv,
            (Param("secret", "Hidden string", "bits", lambda n: _pattern(n - 1), length_offset=-1),),
        ),
        Algorithm(
            "qft_phase",
            "Phase estimation",
            "Reads out a phase exactly; controlled phases fan out across the cut in bursts.",
            4,
            4,
            7,
            _qft_phase,
            (Param("phase", "Phase bits", "bits", lambda n: _pattern(n - 1), length_offset=-1),),
        ),
        Algorithm(
            "grover",
            "Grover search",
            "Finds one marked item among eight; each doubly-controlled Z across the cut is one burst.",
            3,
            3,
            3,
            _grover,
            (
                Param("marked", "Marked item", "bits", lambda n: _pattern(n), length_offset=0),
                Param("iterations", "Grover iterations", "int", lambda n: 1, minimum=1, maximum=2),
            ),
        ),
        Algorithm(
            "qaoa_ring",
            "QAOA MaxCut on a ring",
            "Depth-one QAOA; a ring crosses any cut at least twice, so the best split costs two pairs.",
            4,
            4,
            8,
            _qaoa_ring,
        ),
    )
}


def _clean_params(algorithm: Algorithm, n: int, params: dict | None) -> dict:
    params = dict(params or {})
    known = {p.id for p in algorithm.params}
    unknown = sorted(set(params) - known)
    if unknown:
        raise ValueError(f"{algorithm.name} has no parameter '{unknown[0]}'")
    clean = {}
    for p in algorithm.params:
        value = params.get(p.id)
        if value is None:
            value = p.default(n)
        if p.type == "bits":
            length = n + p.length_offset
            if not isinstance(value, str) or set(value) - {"0", "1"} or len(value) != length:
                raise ValueError(f"{p.label} must be a string of {length} bits for n = {n}")
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{p.label} must be an integer")
            if not p.minimum <= value <= p.maximum:
                raise ValueError(f"{p.label} must be between {p.minimum} and {p.maximum}")
        clean[p.id] = value
    return clean


def build(algorithm: str, n: int | None = None, params: dict | None = None) -> Instance:
    """Build a catalog circuit; raises ``ValueError`` with a readable message on bad input."""
    spec = CATALOG.get(algorithm)
    if spec is None:
        raise ValueError(f"unknown algorithm '{algorithm}'; choose one of {', '.join(CATALOG)}")
    if n is None:
        n = spec.n_default
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an integer")
    if not spec.n_min <= n <= spec.n_max:
        raise ValueError(f"{spec.name} supports n from {spec.n_min} to {spec.n_max}")
    clean = _clean_params(spec, n, params)
    circuit, targets, guess = spec.builder(n, clean)
    half = (n + 1) // 2
    return Instance(algorithm, n, clean, circuit, targets, guess, [0] * half + [1] * (n - half))
