"""Shared generators for the test suite."""

import numpy as np

from seam import lower

GATE_SET = ("h", "rz", "rx", "cx", "cz", "t", "s")
MAX_QUBITS = 17


def random_case(seed):
    """A random circuit over GATE_SET with a random two-module assignment.

    The number of cross gates is capped so that the distributed circuit stays
    simulable even with one pair per gate.
    """
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 7))
    while True:
        assignment = [int(m) for m in rng.integers(0, 2, n)]
        if 0 < sum(assignment) < n:
            break
    length = int(rng.integers(4, 25))
    max_cross = (MAX_QUBITS - n) // 2
    steps, cross = [], 0
    while len(steps) < length:
        name = GATE_SET[int(rng.integers(len(GATE_SET)))]
        if name in ("cx", "cz"):
            a, b = (int(q) for q in rng.choice(n, 2, replace=False))
            if assignment[a] != assignment[b]:
                if cross == max_cross:
                    continue
                cross += 1
            steps.append((name, [a, b]))
        elif name in ("rz", "rx"):
            steps.append((name, [int(rng.integers(n))], [float(rng.uniform(0, 2 * np.pi))]))
        else:
            steps.append((name, [int(rng.integers(n))]))
    return lower.from_steps(steps), assignment
