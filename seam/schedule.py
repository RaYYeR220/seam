"""From cross gates to bursts to Bell pairs.

A burst is a set of cross gates that share one control-side qubit ``c`` and
are served by a single Bell pair: the pair turns into a Z-basis copy of ``c``
in the other module, every gate of the burst is driven from that copy, and
the copy is then erased. The copy stays faithful for as long as nothing acts
on ``c`` that is not diagonal in Z, so the timeline of every qubit is cut
into segments at its non-diagonal gates and a burst must live inside one
segment.

A ``cx`` can only be driven from its control. A ``cz`` can be driven from
either end. Choosing the fewest (qubit, segment) pairs that drive all cross
gates is a minimum vertex cover on a bipartite graph (module 0 segments
against module 1 segments, one edge per cross ``cz``), solved exactly through
Koenig's theorem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .lower import Gate

Vertex = tuple[int, int]  # (qubit, segment)


@dataclass(frozen=True)
class Burst:
    """Cross gates served by one Bell pair, all driven from ``control``."""

    id: int
    control: int
    control_module: int
    gate_indices: tuple[int, ...]


@dataclass(frozen=True)
class _TwoQubit:
    i: int
    name: str
    a: int
    b: int
    seg_a: int
    seg_b: int


def is_cross(gate: Gate, assignment: Sequence[int]) -> bool:
    return len(gate.qubits) == 2 and assignment[gate.qubits[0]] != assignment[gate.qubits[1]]


def cross_gates(gates: Sequence[Gate], assignment: Sequence[int]) -> list[Gate]:
    """Gates whose two qubits sit in different modules."""
    return [g for g in gates if is_cross(g, assignment)]


def _min_vertex_cover(edges: list[tuple[Vertex, Vertex]]) -> set[Vertex]:
    """Minimum vertex cover of a bipartite graph given as (left, right) edges."""
    adjacency: dict[Vertex, list[Vertex]] = {}
    for left, right in edges:
        adjacency.setdefault(left, []).append(right)
    match_right: dict[Vertex, Vertex] = {}

    def augment(left: Vertex, seen: set[Vertex]) -> bool:
        for right in adjacency[left]:
            if right in seen:
                continue
            seen.add(right)
            if right not in match_right or augment(match_right[right], seen):
                match_right[right] = left
                return True
        return False

    for left in adjacency:
        augment(left, set())

    matched_left = set(match_right.values())
    reached_left = {left for left in adjacency if left not in matched_left}
    reached_right: set[Vertex] = set()
    stack = list(reached_left)
    while stack:
        left = stack.pop()
        for right in adjacency[left]:
            if right in reached_right:
                continue
            reached_right.add(right)
            partner = match_right.get(right)
            if partner is not None and partner not in reached_left:
                reached_left.add(partner)
                stack.append(partner)
    return (set(adjacency) - reached_left) | reached_right


class Scheduler:
    """Burst scheduler for one gate list, reusable across assignments."""

    def __init__(self, gates: Sequence[Gate]) -> None:
        breaks: dict[int, int] = {}
        self._two: list[_TwoQubit] = []
        for gate in gates:
            if len(gate.qubits) == 2:
                a, b = gate.qubits
                self._two.append(
                    _TwoQubit(gate.i, gate.name, a, b, breaks.get(a, 0), breaks.get(b, 0))
                )
            for q in gate.qubits:
                if not gate.diagonal_on(q):
                    breaks[q] = breaks.get(q, 0) + 1

    def count_cross(self, assignment: Sequence[int]) -> int:
        return sum(1 for e in self._two if assignment[e.a] != assignment[e.b])

    def _groups(self, assignment: Sequence[int], reuse: bool) -> list[tuple[int, list[int]]]:
        cross = [e for e in self._two if assignment[e.a] != assignment[e.b]]
        if not reuse:
            return [(e.a, [e.i]) for e in cross]
        forced = {(e.a, e.seg_a) for e in cross if e.name == "cx"}
        edges = []
        for e in cross:
            if e.name != "cz":
                continue
            va, vb = (e.a, e.seg_a), (e.b, e.seg_b)
            if va in forced or vb in forced:
                continue
            edges.append((va, vb) if assignment[e.a] == 0 else (vb, va))
        cover = forced | _min_vertex_cover(edges)
        members: dict[Vertex, list[int]] = {}
        for e in cross:
            va, vb = (e.a, e.seg_a), (e.b, e.seg_b)
            driver = va if (e.name == "cx" or va in cover) else vb
            members.setdefault(driver, []).append(e.i)
        groups = [(vertex[0], indices) for vertex, indices in members.items()]
        groups.sort(key=lambda group: group[1][0])
        return groups

    def pairs(self, assignment: Sequence[int], reuse: bool = True) -> int:
        """Number of Bell pairs the cut costs."""
        if not reuse:
            return self.count_cross(assignment)
        return len(self._groups(assignment, True))

    def bursts(self, assignment: Sequence[int], reuse: bool = True) -> list[Burst]:
        return [
            Burst(k, control, assignment[control], tuple(indices))
            for k, (control, indices) in enumerate(self._groups(assignment, reuse))
        ]


def schedule(gates: Sequence[Gate], assignment: Sequence[int], reuse: bool = True) -> list[Burst]:
    """Group the cross gates into bursts, one Bell pair each.

    With ``reuse=False`` every cross gate gets its own pair. With
    ``reuse=True`` the number of bursts is the minimum the burst rule allows.
    """
    return Scheduler(gates).bursts(assignment, reuse)


def validate(gates: Sequence[Gate], assignment: Sequence[int], bursts: Sequence[Burst]) -> None:
    """Raise ``ValueError`` unless ``bursts`` is a legal schedule for the cut."""
    owner: dict[int, int] = {}
    for burst in bursts:
        c = burst.control
        if not burst.gate_indices:
            raise ValueError(f"burst {burst.id} is empty")
        for i in burst.gate_indices:
            gate = gates[i]
            if not is_cross(gate, assignment):
                raise ValueError(f"gate {i} in burst {burst.id} does not cross the cut")
            if c not in gate.qubits or not gate.diagonal_on(c):
                raise ValueError(f"gate {i} cannot be driven from qubit {c}")
            if i in owner:
                raise ValueError(f"gate {i} is in bursts {owner[i]} and {burst.id}")
            owner[i] = burst.id
        for gate in gates[min(burst.gate_indices) : max(burst.gate_indices) + 1]:
            if c in gate.qubits and not gate.diagonal_on(c):
                raise ValueError(
                    f"gate {gate.i} ({gate.name}) is not diagonal on the control of burst {burst.id}"
                )
    for gate in cross_gates(gates, assignment):
        if gate.i not in owner:
            raise ValueError(f"cross gate {gate.i} has no Bell pair")
