"""Partition search: optimal on small cases, capacities respected."""

import itertools

import pytest

from helpers import random_case
from seam import algorithms, lower, partition, schedule


def brute_force(gates, n, capacity, reuse=True):
    costs = []
    for bits in itertools.product((0, 1), repeat=n):
        ones = sum(bits)
        if 0 < ones < n and n - ones <= capacity[0] and ones <= capacity[1]:
            costs.append(len(schedule.schedule(gates, list(bits), reuse=reuse)))
    return min(costs), max(costs)


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("reuse", [True, False])
def test_search_is_optimal_on_random_circuits(seed, reuse):
    gates, assignment = random_case(seed)
    n = len(assignment)
    capacity = partition.default_capacity(n)
    result = partition.search(gates, n, reuse=reuse)
    assert (result.best, result.worst) == brute_force(gates, n, capacity, reuse)
    assert partition.score(gates, result.assignment, reuse) == result.best
    assert partition.within(result.assignment, capacity)
    assert 0 < sum(result.assignment) < n


@pytest.mark.parametrize("capacity", [[1, 5], [5, 1], [2, 4], [4, 4], [3, 3], [6, 6]])
def test_capacities_are_respected(capacity):
    gates = lower.lower(algorithms.build("qft_phase", 6).circuit)
    result = partition.search(gates, 6, capacity=capacity)
    ones = sum(result.assignment)
    assert 6 - ones <= capacity[0] and ones <= capacity[1]
    assert 0 < ones < 6
    assert (result.best, result.worst) == brute_force(gates, 6, capacity)


def test_default_capacity_is_balanced():
    assert partition.default_capacity(6) == [3, 3]
    assert partition.default_capacity(5) == [3, 3]
    for n in range(2, 9):
        gates = lower.from_steps([("cx", [k, k + 1]) for k in range(n - 1)])
        ones = sum(partition.search(gates, n).assignment)
        assert abs(n - 2 * ones) <= 1


def test_ghz_chain_is_cut_once():
    gates = lower.lower(algorithms.build("ghz", 6).circuit)
    result = partition.search(gates, 6)
    assert result.assignment == [0, 0, 0, 1, 1, 1]
    assert (result.best, result.worst) == (1, 5)


def test_search_minimises_pairs_not_cross_gates():
    steps = [("cx", [0, 2]), ("cx", [0, 3]), ("cx", [0, 2]), ("cx", [0, 3]), ("cx", [2, 3])]
    gates = lower.from_steps(steps)
    result = partition.search(gates, 4)
    assert result.assignment == [0, 0, 1, 1] and result.best == 1
    assert len(schedule.cross_gates(gates, result.assignment)) == 4
    by_cross = {}
    for assignment in partition.feasible(4, [2, 2]):
        count = len(schedule.cross_gates(gates, assignment))
        by_cross.setdefault(count, []).append(partition.score(gates, assignment))
    assert min(by_cross) == 3
    assert set(by_cross[3]) == {2}


def test_interaction_graph_counts_gates():
    gates = lower.from_steps([("cx", [0, 1]), ("cz", [1, 0]), ("cx", [2, 1]), ("h", [0])])
    assert partition.interaction_graph(gates) == {(0, 1): 2, (1, 2): 1}


@pytest.mark.parametrize("capacity", [[0, 3], [1], [1, 1], [2.5, 2], "33"])
def test_bad_capacity_is_rejected(capacity):
    with pytest.raises(ValueError):
        partition.check_capacity(4, capacity)


@pytest.mark.parametrize("assignment", [[0, 1], [0, 1, 2, 0], [0, 1, 1, "a"]])
def test_bad_assignment_is_rejected(assignment):
    with pytest.raises(ValueError):
        partition.check_assignment(4, assignment)
