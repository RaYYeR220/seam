"""Deliberately broken circuits must be caught by the equivalence check."""

import numpy as np
import pytest

from helpers import random_case
from seam import build, lower, schedule, verify

BROKEN = 0.999
SEEDS = range(40)


def fidelity(gates, assignment, bursts, drop=None, seed=0, trials=8):
    dist = build.distribute(gates, assignment, bursts, drop=drop)
    inputs = verify.random_inputs(len(assignment), trials, np.random.default_rng(seed))
    return verify.fidelities(gates, dist, inputs)


def cases_with_a_cross_gate():
    cases = []
    for seed in SEEDS:
        gates, assignment = random_case(seed)
        bursts = schedule.schedule(gates, assignment)
        if bursts:
            cases.append((seed, gates, assignment, bursts))
    return cases


@pytest.mark.parametrize("kind", ["z", "x"])
def test_single_teleported_cnot_needs_both_corrections(kind):
    gates = lower.from_steps([("cx", [0, 1])])
    bursts = schedule.schedule(gates, [0, 1])
    assert fidelity(gates, [0, 1], bursts).min() > 1 - 1e-9
    assert fidelity(gates, [0, 1], bursts, drop=(kind, 0)).max() < BROKEN


@pytest.mark.parametrize("kind", ["z", "x"])
def test_dropping_a_correction_breaks_random_circuits(kind):
    cases = cases_with_a_cross_gate()
    assert len(cases) >= 30
    broken = 0
    for seed, gates, assignment, bursts in cases:
        assert fidelity(gates, assignment, bursts, seed=seed).min() > 1 - 1e-9
        if fidelity(gates, assignment, bursts, drop=(kind, bursts[0].id), seed=seed).min() < BROKEN:
            broken += 1
    assert broken >= 0.9 * len(cases)


@pytest.mark.parametrize(
    "breaker", [("h", [0]), ("rx", [0], [0.9]), ("x", [0]), ("cx", [2, 0])], ids=lambda b: b[0]
)
def test_merging_a_burst_across_a_non_diagonal_gate_breaks_equivalence(breaker):
    gates = lower.from_steps([("cx", [0, 1]), breaker, ("cx", [0, 1])])
    assignment = [0, 1, 0]
    legal = schedule.schedule(gates, assignment)
    assert len(legal) == 2
    assert fidelity(gates, assignment, legal).min() > 1 - 1e-9
    merged = [schedule.Burst(0, 0, 0, (0, 2))]
    with pytest.raises(ValueError):
        schedule.validate(gates, assignment, merged)
    assert fidelity(gates, assignment, merged).max() < BROKEN


def test_merging_across_a_diagonal_gate_is_fine():
    gates = lower.from_steps([("cx", [0, 1]), ("rz", [0], [0.9]), ("t", [0]), ("cx", [0, 1])])
    merged = [schedule.Burst(0, 0, 0, (0, 3))]
    schedule.validate(gates, [0, 1], merged)
    assert fidelity(gates, [0, 1], merged).min() > 1 - 1e-9
