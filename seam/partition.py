"""Choosing the cut: which data qubit lives in which module.

The cost of an assignment is the number of Bell pairs the scheduler needs for
it, not the number of gates that cross. The search is exhaustive, which is
exact and cheap for the register sizes a two-module demo can simulate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence

from .lower import Gate
from .schedule import Scheduler

MAX_EXHAUSTIVE = 12


@dataclass(frozen=True)
class Search:
    """Best assignment under the capacities, with the range of costs seen."""

    assignment: list[int]
    best: int
    worst: int


def default_capacity(num_qubits: int) -> list[int]:
    """Balanced modules: each holds at most half of the qubits, rounded up."""
    half = (num_qubits + 1) // 2
    return [half, half]


def check_capacity(num_qubits: int, capacity: Sequence[int] | None) -> list[int]:
    if capacity is None:
        return default_capacity(num_qubits)
    if (
        len(capacity) != 2
        or any(isinstance(c, bool) or not isinstance(c, int) or c < 1 for c in capacity)
    ):
        raise ValueError("capacity must be two positive integers, one per module")
    if sum(capacity) < num_qubits:
        raise ValueError(f"capacity {list(capacity)} cannot hold {num_qubits} qubits")
    return [int(c) for c in capacity]


def check_assignment(num_qubits: int, assignment: Sequence[int]) -> list[int]:
    if len(assignment) != num_qubits or any(m not in (0, 1) for m in assignment):
        raise ValueError(f"assignment must list a module (0 or 1) for each of the {num_qubits} qubits")
    return [int(m) for m in assignment]


def within(assignment: Sequence[int], capacity: Sequence[int]) -> bool:
    ones = sum(assignment)
    return len(assignment) - ones <= capacity[0] and ones <= capacity[1]


def interaction_graph(gates: Sequence[Gate]) -> dict[tuple[int, int], int]:
    """Number of two-qubit gates between each pair of qubits."""
    weights: dict[tuple[int, int], int] = {}
    for gate in gates:
        if len(gate.qubits) == 2:
            edge = (min(gate.qubits), max(gate.qubits))
            weights[edge] = weights.get(edge, 0) + 1
    return weights


def feasible(num_qubits: int, capacity: Sequence[int]) -> Iterator[list[int]]:
    """Every assignment that uses both modules and respects the capacities."""
    for mask in range(1, 2**num_qubits - 1):
        assignment = [(mask >> k) & 1 for k in range(num_qubits)]
        if within(assignment, capacity):
            yield assignment


def search(
    gates: Sequence[Gate],
    num_qubits: int,
    capacity: Sequence[int] | None = None,
    reuse: bool = True,
) -> Search:
    """Exhaustive search for the assignment that costs the fewest Bell pairs.

    Ties are broken by fewer cross gates, then by keeping low qubits in
    module 0, which makes the result deterministic.
    """
    if num_qubits < 2:
        raise ValueError("a cut needs at least two qubits")
    if num_qubits > MAX_EXHAUSTIVE:
        raise ValueError(f"exhaustive partitioning is limited to {MAX_EXHAUSTIVE} qubits")
    capacity = check_capacity(num_qubits, capacity)
    scheduler = Scheduler(gates)
    best_key, best_assignment, worst = None, None, 0
    for assignment in feasible(num_qubits, capacity):
        pairs = scheduler.pairs(assignment, reuse)
        worst = max(worst, pairs)
        key = (pairs, scheduler.count_cross(assignment), assignment)
        if best_key is None or key < best_key:
            best_key, best_assignment = key, assignment
    if best_assignment is None:
        raise ValueError(f"no assignment uses both modules within capacity {capacity}")
    return Search(best_assignment, best_key[0], worst)


def score(gates: Sequence[Gate], assignment: Sequence[int], reuse: bool = True) -> int:
    """Bell pairs needed by a given assignment."""
    return Scheduler(gates).pairs(assignment, reuse)
