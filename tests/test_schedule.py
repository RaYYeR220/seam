"""Scheduler: cross gates -> bursts -> pairs."""

import itertools

import pytest

from helpers import random_case
from seam import lower, schedule

SEEDS = range(120)


@pytest.mark.parametrize("seed", SEEDS)
def test_pairs_bounded_by_cross_gates_and_schedule_is_legal(seed):
    gates, assignment = random_case(seed)
    cross = schedule.cross_gates(gates, assignment)
    with_reuse = schedule.schedule(gates, assignment, reuse=True)
    without = schedule.schedule(gates, assignment, reuse=False)
    schedule.validate(gates, assignment, with_reuse)
    schedule.validate(gates, assignment, without)
    assert len(with_reuse) <= len(cross)
    assert len(without) == len(cross)
    assert all(len(b.gate_indices) == 1 for b in without)
    covered = sorted(i for b in with_reuse for i in b.gate_indices)
    assert covered == [g.i for g in cross]


def brute_force_pairs(gates, assignment):
    """Fewest (qubit, segment) drivers over every choice of driving end for each cz."""
    breaks = {}
    options = []
    for gate in gates:
        if schedule.is_cross(gate, assignment):
            ends = gate.qubits if gate.name == "cz" else gate.qubits[:1]
            options.append([(q, breaks.get(q, 0)) for q in ends])
        for q in gate.qubits:
            if not gate.diagonal_on(q):
                breaks[q] = breaks.get(q, 0) + 1
    if not options:
        return 0
    return min(len(set(choice)) for choice in itertools.product(*options))


@pytest.mark.parametrize("seed", SEEDS)
def test_reuse_schedule_is_optimal_under_the_burst_rule(seed):
    gates, assignment = random_case(seed)
    assert len(schedule.schedule(gates, assignment)) == brute_force_pairs(gates, assignment)


@pytest.mark.parametrize("k", [1, 2, 3, 4, 7])
def test_fan_out_from_one_control_is_one_pair(k):
    gates = lower.from_steps([("h", [0])] + [("cx", [0, t]) for t in range(1, k + 1)])
    assignment = [0] + [1] * k
    bursts = schedule.schedule(gates, assignment)
    assert len(bursts) == 1
    assert bursts[0].control == 0 and bursts[0].control_module == 0
    assert bursts[0].gate_indices == tuple(range(1, k + 1))
    assert len(schedule.schedule(gates, assignment, reuse=False)) == k


def test_diagonal_gates_on_control_keep_the_burst_open():
    steps = [("cx", [0, 1]), ("rz", [0], [0.3]), ("t", [0]), ("s", [0]), ("cz", [0, 2]), ("cx", [0, 2])]
    gates = lower.from_steps(steps)
    assert len(schedule.schedule(gates, [0, 1, 1])) == 1


@pytest.mark.parametrize("breaker", [("h", [0]), ("rx", [0], [0.4]), ("x", [0]), ("cx", [2, 0])])
def test_non_diagonal_gate_on_control_splits_the_burst(breaker):
    gates = lower.from_steps([("cx", [0, 1]), breaker, ("cx", [0, 1])])
    assert len(schedule.schedule(gates, [0, 1, 0])) == 2


def test_a_cross_cx_onto_the_control_splits_the_burst_and_costs_a_pair():
    gates = lower.from_steps([("cx", [0, 1]), ("cx", [1, 0]), ("cx", [0, 1])])
    assert [b.control for b in schedule.schedule(gates, [0, 1])] == [0, 1, 0]


def test_gates_on_other_qubits_do_not_split_a_burst():
    gates = lower.from_steps([("cx", [0, 2]), ("h", [1]), ("h", [2]), ("cx", [1, 2]), ("cx", [0, 3])])
    bursts = schedule.schedule(gates, [0, 0, 1, 1])
    assert [b.control for b in bursts] == [0, 1]
    assert bursts[0].gate_indices == (0, 4)


def test_cz_can_be_driven_from_either_end():
    gates = lower.from_steps([("cz", [0, 2]), ("cz", [1, 2])])
    bursts = schedule.schedule(gates, [0, 0, 1])
    assert len(bursts) == 1 and bursts[0].control == 2 and bursts[0].control_module == 1


def test_shared_target_of_cx_is_not_merged():
    gates = lower.from_steps([("cx", [0, 2]), ("cx", [1, 2])])
    assert len(schedule.schedule(gates, [0, 0, 1])) == 2


def test_cz_joins_a_burst_already_forced_by_a_cx():
    gates = lower.from_steps([("cx", [0, 2]), ("cz", [3, 0]), ("cz", [1, 3])])
    bursts = schedule.schedule(gates, [0, 0, 1, 1])
    assert len(bursts) == 2
    assert bursts[0].control == 0 and bursts[0].gate_indices == (0, 1)


def test_no_cross_gates_means_no_pairs():
    gates = lower.from_steps([("cx", [0, 1]), ("cz", [2, 3])])
    assert schedule.schedule(gates, [0, 0, 1, 1]) == []


def test_validate_rejects_a_burst_across_a_hadamard():
    gates = lower.from_steps([("cx", [0, 1]), ("h", [0]), ("cx", [0, 1])])
    merged = [schedule.Burst(0, 0, 0, (0, 2))]
    with pytest.raises(ValueError):
        schedule.validate(gates, [0, 1], merged)


def test_validate_rejects_missing_and_misdriven_gates():
    gates = lower.from_steps([("cx", [0, 1]), ("cx", [0, 1])])
    with pytest.raises(ValueError):
        schedule.validate(gates, [0, 1], [schedule.Burst(0, 0, 0, (0,))])
    with pytest.raises(ValueError):
        schedule.validate(gates, [0, 1], [schedule.Burst(0, 1, 1, (0, 1))])
