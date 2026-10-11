"""Experiments: backend circuits, decoding of counts, exact predictions and intervals."""

import math

import numpy as np
import pytest
from qiskit.providers.basic_provider import BasicSimulator

from seam import algorithms, build, experiments, link

SPECS = {
    "truth_table": {"kind": "truth_table", "q": 0.0},
    "truth_table_noisy": {"kind": "truth_table", "q": 0.1},
    "remote_bell": {"kind": "remote_bell", "qs": [0, 0.1, 0.3], "distill": "both"},
    "burst": {"kind": "burst", "k": 3, "q": 0.05},
    "burst_max": {"kind": "burst", "k": 4, "q": 0.2},
    "ghz": {"kind": "algorithm", "algorithm": "ghz", "n": 4, "q": 0.1, "distill": True},
    "grover": {"kind": "algorithm", "algorithm": "grover", "q": 0.05, "distill": False},
    "qaoa": {"kind": "algorithm", "algorithm": "qaoa_ring", "q": 0.1, "distill": False},
    "sweep": {"kind": "algorithm_sweep", "algorithm": "bv", "n": 4, "qs": [0, 0.1, 0.25], "distill": "both"},
    "sweep_qaoa": {"kind": "algorithm_sweep", "algorithm": "qaoa_ring", "qs": [0.1], "distill": False},
}
for _spec in algorithms.CATALOG.values():
    SPECS[f"default_{_spec.id}"] = {"kind": "algorithm", "algorithm": _spec.id, "q": 0.05, "distill": True}

HEADLINES = ("value", "f", "p_expected", "success", "hellinger")


def within_stretched_interval(value, lo, hi, truth, shots):
    """True when ``truth`` lies in the 95% interval stretched to five standard errors."""
    stretch = 5 / experiments.Z95
    slack = 1 / shots
    return value - stretch * (value - lo) - slack <= truth <= value + stretch * (hi - value) + slack


def estimates(measured, exact, path=""):
    """Pair every measured estimate that carries an interval with its exact value."""
    if isinstance(measured, dict):
        if "lo" in measured and "hi" in measured:
            name = next(k for k in HEADLINES if measured.get(k) is not None)
            yield path + "." + name, measured[name], measured["lo"], measured["hi"], exact[name]
        for key, value in measured.items():
            if isinstance(value, (dict, list)) and key not in ("counts", "top"):
                yield from estimates(value, exact[key], f"{path}.{key}")
    elif isinstance(measured, list):
        for k, value in enumerate(measured):
            yield from estimates(value, exact[k], f"{path}[{k}]")


@pytest.mark.parametrize("name", sorted(SPECS))
def test_backend_circuits_fit_and_end_with_measurements_only(name):
    described = experiments.describe(SPECS[name])
    assert described["shots"] == experiments.DEFAULT_SHOTS
    assert described["circuits"]
    for entry in described["circuits"]:
        circuit = experiments.circuit(entry["cid"])
        assert circuit.num_qubits == entry["qubits"] <= build.MAX_BACKEND_QUBITS
        assert circuit.depth() == entry["depth"]
        names = [inst.operation.name for inst in circuit.data]
        assert set(names) <= set(build.BASIS) | {"measure"}
        first = names.index("measure")
        assert set(names[first:]) == {"measure"}
        written = [circuit.find_bit(inst.clbits[0]).index for inst in circuit.data[first:]]
        assert sorted(written) == list(range(circuit.num_clbits))


@pytest.mark.parametrize("name", sorted(SPECS))
def test_exact_runs_without_a_backend_and_reports_no_intervals(name):
    result = experiments.exact(SPECS[name])
    assert result["source"] == "exact" and result["shots"] is None
    assert list(estimates(result, result)) == []


@pytest.mark.parametrize("name", sorted(SPECS))
def test_ingest_on_sampled_counts_agrees_with_exact(name):
    """Counts drawn from the exact distribution, many times over.

    Every 95% interval contains its own estimate, each kind of interval covers
    the exact value at least 90% of the time, and on every single draw the
    exact value lies inside the interval stretched to five standard errors.
    """
    spec = SPECS[name]
    exact = experiments.exact(spec)
    made = experiments.find(experiments.describe(spec)["id"])
    shots, seeds = 2000, 40
    coverage = {}
    for seed in range(seeds):
        measured = experiments.ingest(made.id, experiments.sample(spec, shots, seed), shots)
        assert measured["source"] == "measured" and measured["shots"] == shots
        found = list(estimates(measured, exact))
        assert found
        for path, value, lo, hi, truth in found:
            kind = path.rsplit(".", 1)[1]
            assert lo <= value <= hi, path
            assert within_stretched_interval(value, lo, hi, truth, shots), path
            hits = coverage.setdefault(kind, [0, 0])
            hits[0] += lo - 1e-12 <= truth <= hi + 1e-12
            hits[1] += 1
    for kind, (covered, total) in coverage.items():
        assert covered / total >= 0.9, (kind, covered, total)


BACKEND_CASES = ["truth_table", "truth_table_noisy", "remote_bell", "burst", "ghz", "grover", "qaoa", "sweep"]


@pytest.mark.parametrize("name", BACKEND_CASES)
def test_transpiled_circuits_on_basic_simulator_match_exact(name):
    """The circuits handed to a backend really produce the predicted statistics."""
    spec = SPECS[name]
    shots = 4000
    described = experiments.describe({**spec, "shots": shots})
    backend = BasicSimulator()
    counts = {
        entry["cid"]: backend.run(experiments.circuit(entry["cid"]), shots=shots, seed_simulator=11)
        .result()
        .get_counts()
        for entry in described["circuits"]
    }
    measured = experiments.ingest(described["id"], counts, shots)
    exact = experiments.exact(spec)
    found = list(estimates(measured, exact))
    assert found
    for path, value, lo, hi, truth in found:
        assert within_stretched_interval(value, lo, hi, truth, shots), path


@pytest.mark.parametrize("q", [0.0, 0.05, 0.2, 0.5])
def test_truth_table_sees_only_bit_flips(q):
    result = experiments.exact({"kind": "truth_table", "q": q})
    assert [row["input"] for row in result["rows"]] == ["00", "01", "10", "11"]
    assert [row["expected"] for row in result["rows"]] == ["00", "01", "11", "10"]
    for row in result["rows"]:
        assert abs(row["p_expected"] - (1 - q)) < 1e-9
    assert abs(result["agreement"] - (1 - q)) < 1e-9
    assert result["pairs"] == 1


def test_truth_table_packs_four_inputs_into_one_circuit_when_clean():
    clean = experiments.describe({"kind": "truth_table", "q": 0.0})
    noisy = experiments.describe({"kind": "truth_table", "q": 0.1})
    assert [c["qubits"] for c in clean["circuits"]] == [16]
    assert [c["qubits"] for c in noisy["circuits"]] == [6, 6, 6, 6]


def test_remote_bell_fidelity_equals_pair_fidelity():
    qs = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]
    result = experiments.exact({"kind": "remote_bell", "qs": qs, "distill": "both"})
    for q, point in zip(qs, result["points"]):
        fidelity, kept = link.distilled(q)
        assert abs(point["pair_fidelity"] - (1 - q) ** 2) < 1e-9
        assert abs(point["raw"]["f"] - (1 - q) ** 2) < 1e-9
        assert abs(point["distilled"]["f"] - fidelity) < 1e-9
        assert abs(point["distilled"]["kept"] - kept) < 1e-9
    stops = result["thresholds"]["distill_stops_helping_q"]
    assert abs(stops - link.DISTILLATION_LIMIT) < 1e-4
    assert stops < 0.5 and result["thresholds"]["entanglement"] == 0.5


def test_remote_bell_variants_follow_the_distill_option():
    spec = {"kind": "remote_bell", "qs": [0.1]}
    assert len(experiments.describe({**spec, "distill": "both"})["circuits"]) == 6
    raw = experiments.exact({**spec, "distill": False})["points"][0]
    distilled = experiments.exact({**spec, "distill": True})["points"][0]
    assert "raw" in raw and "distilled" not in raw
    assert "distilled" in distilled and "raw" not in distilled


@pytest.mark.parametrize("k", [1, 2, 3, 4])
@pytest.mark.parametrize("q", [0.0, 0.05, 0.2])
def test_burst_reuse_pays_for_one_pair_instead_of_k(k, q):
    result = experiments.exact({"kind": "burst", "k": k, "q": q})
    shared, separate = result["variants"]
    assert (shared["reuse"], shared["pairs"]) == (True, 1)
    assert (separate["reuse"], separate["pairs"]) == (False, k)
    assert shared["qubits"] == k + 1 + (4 if q else 2)
    assert separate["qubits"] == k + 1 + k * (4 if q else 2)
    assert abs(shared["p_equal"]["value"] - (1 - q)) < 1e-9
    assert abs(shared["x_parity"]["value"] - (1 - 2 * q)) < 1e-9
    assert abs(separate["p_equal"]["value"] - (1 - q) ** k) < 1e-9
    assert abs(separate["x_parity"]["value"] - (1 - 2 * q) ** k) < 1e-9
    for variant in (shared, separate):
        bound = max(0.0, variant["p_equal"]["value"] - (1 - variant["x_parity"]["value"]) / 2)
        assert abs(variant["fidelity"]["value"] - bound) < 1e-9


def test_burst_fidelity_bound_never_exceeds_the_true_ghz_fidelity():
    """With one pair the state is GHZ unless an X or a Z flip happened: F = (1-q)^2."""
    for q in (0.0, 0.05, 0.2, 0.4):
        shared = experiments.exact({"kind": "burst", "k": 3, "q": q, "reuse": True})["variants"][0]
        assert shared["fidelity"]["value"] <= (1 - q) ** 2 + 1e-9
        assert (1 - q) ** 2 - shared["fidelity"]["value"] <= q * q + 1e-9


@pytest.mark.parametrize("algorithm", sorted(algorithms.CATALOG))
def test_perfect_link_reproduces_the_monolithic_distribution(algorithm):
    for distill in (False, True):
        spec = {"kind": "algorithm", "algorithm": algorithm, "q": 0.0, "distill": distill}
        result = experiments.exact(spec)
        assert abs(result["dist"]["hellinger"] - 1) < 1e-9
        assert abs(result["mono"]["hellinger"] - 1) < 1e-9
        assert abs(result["dist"]["kept"] - 1) < 1e-9
        assert result["mono"]["success"] == pytest.approx(result["dist"]["success"], abs=1e-9)
        assert (result["metric"] == "success") == (result["target"] is not None)


def test_algorithm_result_shape_and_budget():
    result = experiments.exact({"kind": "algorithm", "algorithm": "bv", "q": 0.05, "distill": True})
    assert result["target"] == ["010110"] and result["classical_guess"] == 1 / 32
    assert result["pairs"] == 1 and result["pairs_without_reuse"] == 1
    assert result["mono"]["qubits"] == 6 and result["dist"]["qubits"] == 14
    assert abs(result["dist"]["kept"] - link.distilled(0.05)[1]) < 1e-9
    assert result["dist"]["top"][0][0] == "010110"
    budget = result["budget"]
    assert budget["pairs_per_shot"] == 1 and budget["raw_pairs_per_shot"] == 2
    assert budget["shots_per_second"] == 500
    assert abs(budget["kept_shots_per_second"] - 500 * result["dist"]["kept"]) < 1e-6
    assert budget["model"].startswith("Modeled")


def test_ghz_success_only_sees_bit_flips():
    for q in (0.05, 0.2, 0.4):
        result = experiments.exact({"kind": "algorithm", "algorithm": "ghz", "q": q, "distill": False})
        assert abs(result["dist"]["success"] - (1 - q)) < 1e-9


def test_sweep_shape_and_break_even():
    qs = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]
    spec = {"kind": "algorithm_sweep", "algorithm": "grover", "qs": qs, "distill": "both"}
    result = experiments.exact(spec)
    assert result["metric"] == "success" and result["classical_guess"] == 1 / 8
    assert abs(result["mono"] - 25 / 32) < 1e-9
    assert [p["q"] for p in result["points"]] == qs
    first = result["points"][0]
    assert abs(first["raw"]["value"] - result["mono"]) < 1e-9
    assert abs(first["distilled"]["value"] - result["mono"]) < 1e-9
    assert abs(first["distilled"]["kept"] - 1) < 1e-9
    for variant in ("raw", "distilled"):
        crossing = result["break_even_q"][variant]
        assert 0 < crossing < 0.5
        single = {**spec, "distill": variant == "distilled"}
        just_before, just_after = (
            experiments.exact({**single, "qs": [q]})["points"][0][variant]["value"]
            for q in (crossing - 1e-3, crossing + 1e-3)
        )
        assert just_after < 0.5 < just_before
    assert 0 < result["distill_stops_helping_q"] < 0.5


def test_break_even_is_null_when_the_result_never_drops_below_the_floor():
    spec = {"kind": "algorithm_sweep", "algorithm": "ghz", "qs": [0, 0.5], "distill": False}
    result = experiments.exact(spec)
    assert result["break_even_q"] == {"raw": None}
    assert abs(result["points"][1]["raw"]["value"] - 0.5) < 1e-9


def test_distillation_helps_at_small_error_and_hurts_at_large_error():
    spec = {"kind": "algorithm_sweep", "algorithm": "qft_phase", "qs": [0.05, 0.4], "distill": "both"}
    small, large = experiments.exact(spec)["points"]
    assert small["distilled"]["value"] > small["raw"]["value"]
    assert large["distilled"]["value"] < large["raw"]["value"]


def test_counts_with_register_spaces_and_flags_are_decoded():
    spec = {"kind": "algorithm", "algorithm": "ghz", "n": 3, "q": 0.1, "distill": True}
    described = experiments.describe(spec)
    mono, dist = (c["cid"] for c in described["circuits"])
    counts = {
        mono: {"000": 50, "111": 50},
        dist: {"00 000": 40, "11 111": 30, "01 000": 20, "10 111": 6, "11 011": 4},
    }
    result = experiments.ingest(described["id"], counts, 100)
    assert result["dist"]["kept"] == pytest.approx(0.74)
    assert result["dist"]["success"] == pytest.approx(70 / 74)
    assert result["dist"]["top"][0] == ["000", 40]
    assert result["mono"]["success"] == 1.0
    unspaced = dict(counts)
    unspaced[dist] = {key.replace(" ", ""): value for key, value in counts[dist].items()}
    assert experiments.ingest(described["id"], unspaced, 100)["dist"] == result["dist"]


@pytest.mark.parametrize(
    "bad",
    [
        {"00 00": 10},
        {"00 0x0": 10},
        {"00 000": -1},
        {"01 000": 10},
        {},
        "not counts",
    ],
)
def test_bad_counts_are_rejected(bad):
    spec = {"kind": "algorithm", "algorithm": "ghz", "n": 3, "q": 0.1, "distill": True}
    described = experiments.describe(spec)
    mono, dist = (c["cid"] for c in described["circuits"])
    with pytest.raises(ValueError):
        experiments.ingest(described["id"], {mono: {"000": 10}, dist: bad}, 10)


def test_missing_circuit_counts_are_rejected():
    described = experiments.describe({"kind": "truth_table", "q": 0.1})
    with pytest.raises(ValueError):
        experiments.ingest(described["id"], {described["circuits"][0]["cid"]: {"00": 5}}, 5)


def test_same_spec_reuses_the_cached_circuits():
    spec = {"kind": "burst", "k": 2, "q": 0.05}
    first = experiments.describe(spec)
    second = experiments.describe({**spec, "shots": 500})
    assert first["id"] == second["id"] and second["shots"] == 500
    cid = first["circuits"][0]["cid"]
    assert experiments.circuit(cid) is experiments.circuit(cid)


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "nope"},
        {"kind": "truth_table", "q": 0.7},
        {"kind": "truth_table", "q": "0.1"},
        {"kind": "remote_bell", "qs": []},
        {"kind": "remote_bell", "qs": [0.1, 0.9]},
        {"kind": "remote_bell", "qs": [0.1], "distill": "maybe"},
        {"kind": "burst", "k": 5},
        {"kind": "burst", "k": 2, "reuse": "yes"},
        {"kind": "algorithm", "algorithm": "ghz", "q": 0.1, "distill": "both"},
        {"kind": "algorithm", "algorithm": "qaoa_ring", "n": 8, "q": 0.1, "distill": True},
        {"kind": "algorithm_sweep", "algorithm": "qaoa_ring", "n": 8, "qs": [0.1], "distill": "both"},
        {"kind": "algorithm_sweep", "algorithm": "ghz"},
        {"kind": "truth_table", "shots": 0},
    ],
)
def test_bad_specs_raise_value_error(spec):
    with pytest.raises(ValueError):
        experiments.describe(spec)


def test_wilson_interval():
    lo, hi = experiments.wilson(0.5, 100)
    assert abs(lo - 0.40383) < 1e-4 and abs(hi - 0.59617) < 1e-4
    lo, hi = experiments.wilson(1.0, 2000)
    assert hi == 1.0 and 0.998 < lo < 1.0
    lo, hi = experiments.wilson(0.0, 2000)
    assert lo == 0.0 and 0 < hi < 0.002


def test_hellinger_fidelity():
    p = {"00": 0.5, "11": 0.5}
    assert experiments.hellinger(p, p) == pytest.approx(1.0)
    assert experiments.hellinger(p, {"01": 1.0}) == 0.0
    assert experiments.hellinger(p, {"00": 1.0}) == pytest.approx(0.5)
    uniform = {format(i, "02b"): 0.25 for i in range(4)}
    assert experiments.hellinger(uniform, p) == pytest.approx((2 * math.sqrt(0.125)) ** 2)


def test_model_reweighting_matches_direct_simulation():
    """One run with the environment in superposition predicts every q exactly."""
    from seam import lower, schedule, sim

    gates = lower.lower(algorithms.build("qft_phase").circuit)
    assignment = [0, 1, 1, 0]
    bursts = schedule.schedule(gates, assignment)
    for q in (0.03, 0.2, 0.45):
        dist = build.distribute(gates, assignment, bursts, q, True)
        direct = sim.run(dist.ops, dist.num_qubits)
        measured = list(range(4)) + [w for pair in dist.flags for w in pair]
        table = sim.probabilities(direct, measured, dist.num_qubits)
        for _ in dist.flags:
            table = table[..., 0, 0] + table[..., 1, 1]
        assert np.allclose(experiments.model_for(dist).kept(q), table, atol=1e-12)


def test_submitted_experiments_survive_many_exact_requests():
    described = experiments.describe({"kind": "truth_table", "q": 0.123})
    cid = described["circuits"][0]["cid"]
    for k in range(experiments._SETUP_CACHE + 5):
        experiments.exact({"kind": "truth_table", "q": 0.2 + k / 1000})
    assert experiments.circuit(cid).num_qubits == 6
    counts = {c["cid"]: {"00": 7} for c in described["circuits"]}
    assert experiments.ingest(described["id"], counts, 7)["shots"] == 7


@pytest.mark.parametrize(
    "algorithm,n,distill",
    [
        ("qft_phase", 4, False),
        ("grover", 3, False),
        ("qaoa_ring", 4, False),
        ("ghz", 4, True),
        ("bv", 5, True),
    ],
)
@pytest.mark.parametrize("q", [0.07, 0.3])
def test_environment_model_equals_an_explicit_mixture_over_pauli_errors(algorithm, n, distill, q):
    """Insert X and Z by hand after each raw pair of a noiseless circuit and average."""
    import itertools

    from seam import lower, partition, schedule, sim
    from seam.link import Op

    gates = lower.lower(algorithms.build(algorithm, n).circuit)
    assignment = partition.search(gates, n).assignment
    bursts = schedule.schedule(gates, assignment)
    clean = build.distribute(gates, assignment, bursts, 0.0, distill)
    made = [k for k, op in enumerate(clean.ops) if op.role == "pair" and op.name == "cx"]
    assert len(made) == clean.raw_pairs
    measured = list(range(n)) + [w for pair in clean.flags for w in pair]
    mixture = 0.0
    for pattern in itertools.product(itertools.product((0, 1), repeat=2), repeat=len(made)):
        ops, weight = list(clean.ops), 1.0
        for position, (x_flip, z_flip) in sorted(zip(made, pattern), reverse=True):
            half = clean.ops[position].wires[1]
            errors = [Op(name, (half,)) for name, on in (("x", x_flip), ("z", z_flip)) if on]
            ops[position + 1 : position + 1] = errors
            weight *= (q if x_flip else 1 - q) * (q if z_flip else 1 - q)
        table = sim.probabilities(sim.run(ops, clean.num_qubits), measured, clean.num_qubits)
        for _ in clean.flags:
            table = table[..., 0, 0] + table[..., 1, 1]
        mixture = mixture + weight * table
    noisy = build.distribute(gates, assignment, bursts, q, distill)
    assert np.allclose(experiments.model_for(noisy).kept(q), mixture, atol=1e-12)
