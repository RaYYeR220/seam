"""service.py: JSON in, JSON out, errors as data."""

import json

import pytest
from qiskit import QuantumCircuit, qasm2

from seam import build, experiments, link, service

CATALOG = json.loads(service.catalog())
IDS = [a["id"] for a in CATALOG["algorithms"]]


def call(function, *args):
    raw = function(*(json.dumps(a) if isinstance(a, (dict, list)) else a for a in args))
    assert isinstance(raw, str)
    return json.loads(raw)


def test_catalog_shape():
    assert set(IDS) == {"ghz", "bv", "qft_phase", "grover", "qaoa_ring"}
    assert CATALOG["limits"] == {"max_backend_qubits": 22}
    assert CATALOG["basis"] == ["rx", "ry", "rz", "h", "x", "cx"]
    assert CATALOG["link"]["pair_rate_hz"] == 1000
    assert set(CATALOG["link"]) == {"pair_rate_hz", "source", "note"}
    for entry in CATALOG["algorithms"]:
        assert {"id", "name", "blurb", "n_default", "n_min", "n_max", "params"} <= set(entry)
        assert entry["n_min"] <= entry["n_default"] <= entry["n_max"]
        for param in entry["params"]:
            assert {"id", "label", "type", "default"} <= set(param)


@pytest.mark.parametrize("algorithm", IDS)
def test_plan_shape_and_invariants(algorithm):
    plan = call(service.plan, {"algorithm": algorithm})
    assert "error" not in plan
    n = plan["n"]
    assert plan["algorithm"] == algorithm and plan["auto"] is True
    assert len(plan["assignment"]) == n and set(plan["assignment"]) == {0, 1}
    assert [g["i"] for g in plan["gates"]] == list(range(len(plan["gates"])))
    for gate in plan["gates"]:
        assert set(gate) == {"i", "name", "qubits", "params", "layer", "cross", "burst"}
        assert 0 <= gate["layer"] < plan["layers"]
        modules = {plan["assignment"][q] for q in gate["qubits"]}
        assert gate["cross"] == (len(modules) == 2)
        assert (gate["burst"] is not None) == gate["cross"]
    cross = [g["i"] for g in plan["gates"] if g["cross"]]
    assert plan["cut"]["cross_gates"] == plan["cut"]["pairs_without_reuse"] == len(cross)
    assert plan["cut"]["pairs"] == len(plan["bursts"]) <= len(cross)
    assert sorted(i for b in plan["bursts"] for i in b["gate_indices"]) == cross
    for burst in plan["bursts"]:
        assert burst["control_module"] == plan["assignment"][burst["control"]]
        assert all(plan["gates"][i]["burst"] == burst["id"] for i in burst["gate_indices"])
    scores = plan["scores"]
    assert scores["best"] == scores["this"] == plan["cut"]["pairs"] <= scores["worst"]
    pairs = plan["cut"]["pairs"]
    assert plan["qubits"] == {
        "data": n,
        "comm": 2 * pairs,
        "total_clean": n + 2 * pairs,
        "total_noisy": n + 4 * pairs,
        "total_distilled": n + 4 * pairs,
        "total_noisy_distilled": n + 8 * pairs,
    }
    assert plan["target"] is None or all(len(t) == n for t in plan["target"])


@pytest.mark.parametrize("algorithm", IDS)
def test_default_size_fits_the_backend_with_noise_and_distillation(algorithm):
    plan = call(service.plan, {"algorithm": algorithm})
    assert plan["qubits"]["total_noisy_distilled"] <= CATALOG["limits"]["max_backend_qubits"]
    layout = call(service.distributed, {"algorithm": algorithm, "q": 0.1, "distill": True})
    assert layout["qubits"]["total"] == plan["qubits"]["total_noisy_distilled"]


@pytest.mark.parametrize("entry", CATALOG["algorithms"], ids=IDS)
def test_every_catalog_size_plans_and_proves(entry):
    for n in range(entry["n_min"], entry["n_max"] + 1):
        options = {"algorithm": entry["id"], "n": n}
        plan = call(service.plan, options)
        assert "error" not in plan, plan
        proof = call(service.proof, {**options, "trials": 4})
        assert proof["passed"] is True and proof["trials"] == 4
        assert proof["fidelity_min"] > 1 - 1e-9
        assert proof["qubits"] == plan["qubits"]["total_clean"]
        if plan["cut"]["pairs"]:
            assert proof["negative_control"] < 0.999
        else:
            assert proof["negative_control"] is None


def test_plan_respects_a_user_assignment_and_reuse_flag():
    options = {"algorithm": "qft_phase", "n": 4, "assignment": [0, 0, 1, 1]}
    plan = call(service.plan, options)
    assert plan["auto"] is False and plan["assignment"] == [0, 0, 1, 1]
    assert plan["scores"]["this"] >= plan["scores"]["best"]
    without = call(service.plan, {**options, "reuse": False})
    assert without["cut"]["pairs"] == without["cut"]["cross_gates"] == plan["cut"]["cross_gates"]
    assert all(len(b["gate_indices"]) == 1 for b in without["bursts"])
    one_module = call(service.plan, {"algorithm": "ghz", "n": 4, "assignment": [0, 0, 0, 0]})
    assert one_module["cut"] == {"cross_gates": 0, "pairs": 0, "pairs_without_reuse": 0}


def test_plan_capacity():
    plan = call(service.plan, {"algorithm": "ghz", "n": 6, "capacity": [1, 5]})
    assert sorted(plan["assignment"]).count(0) == 1
    unbalanced = {"algorithm": "ghz", "n": 6, "assignment": [0, 0, 0, 1, 1, 1], "capacity": [1, 5]}
    error = call(service.plan, unbalanced)
    assert "capacities" in error["error"]


@pytest.mark.parametrize("algorithm", IDS)
@pytest.mark.parametrize("q,distill", [(0.0, False), (0.1, False), (0.0, True), (0.1, True)])
def test_distributed_layout(algorithm, q, distill):
    plan = call(service.plan, {"algorithm": algorithm})
    layout = call(service.distributed, {"algorithm": algorithm, "q": q, "distill": distill})
    wires, ops = layout["wires"], layout["ops"]
    assert [w["id"] for w in wires] == list(range(len(wires)))
    assert {w["kind"] for w in wires} <= {"data", "comm", "env", "sacrifice"}
    for wire in wires:
        assert set(wire) == {"id", "kind", "module", "label", "pair", "data_index"}
        assert (wire["module"] is None) == (wire["kind"] == "env")
        assert (wire["data_index"] is not None) == (wire["kind"] == "data")
    pairs = plan["cut"]["pairs"]
    raw = pairs * (2 if distill else 1)
    assert layout["pairs"] == pairs and layout["raw_pairs"] == raw
    assert layout["qubits"] == {
        "data": plan["n"],
        "comm": 2 * pairs,
        "env": 2 * raw if q else 0,
        "sacrifice": 2 * pairs if distill else 0,
        "total": len(wires),
    }
    busy = set()
    for op in ops:
        assert set(op) == {"name", "wires", "params", "role", "pair", "gate", "layer", "crosses_link"}
        assert op["role"] in link.ROLES
        assert 0 <= op["layer"] < layout["layers"]
        modules = [wires[w]["module"] for w in op["wires"]]
        assert op["crosses_link"] == (len(modules) == 2 and None not in modules and modules[0] != modules[1])
        if op["crosses_link"]:
            assert op["role"] in ("pair", "classical")
        for wire in op["wires"]:
            assert (wire, op["layer"]) not in busy
            busy.add((wire, op["layer"]))
    measured = [op for op in ops if op["role"] == "measure"]
    assert len(measured) == plan["n"] + (2 * pairs if distill else 0)
    assert {op["layer"] for op in measured} == {layout["layers"] - 1}
    local = [op["gate"] for op in ops if op["role"] in ("local", "remote")]
    assert local == list(range(len(plan["gates"])))
    assert sum(op["role"] == "remote" for op in ops) == plan["cut"]["cross_gates"]
    assert sum(op["role"] == "cat" for op in ops) == pairs
    assert sum(op["role"] == "classical" for op in ops) == 2 * pairs


@pytest.mark.parametrize("algorithm", IDS)
def test_experiment_round_trip(algorithm):
    spec = {"kind": "algorithm", "algorithm": algorithm, "q": 0.05, "distill": False, "shots": 1000}
    described = call(service.experiment, spec)
    assert set(described) == {"id", "kind", "circuits", "shots"} and described["shots"] == 1000
    assert [c["label"] for c in described["circuits"]] == ["monolithic", "distributed, q=0.05"]
    for entry in described["circuits"]:
        circuit = service.circuit(entry["cid"])
        assert isinstance(circuit, QuantumCircuit)
        assert circuit.num_qubits == entry["qubits"] <= 22
    counts = experiments.sample(spec, 1000, seed=3)
    measured = call(service.ingest, described["id"], counts, 1000)
    exact = call(service.exact, spec)
    assert measured["source"] == "measured" and exact["source"] == "exact"
    assert set(measured) == set(exact)
    for side in ("mono", "dist"):
        assert {"success", "hellinger", "top", "qubits", "depth"} <= set(exact[side])
        assert {"lo", "hi"} <= set(measured[side]) and "lo" not in exact[side]
    assert set(exact["budget"]) >= {"pairs_per_shot", "raw_pairs_per_shot", "shots_per_second", "model"}


def test_ingest_accepts_shots_as_text_and_counts_as_object():
    described = call(service.experiment, {"kind": "truth_table", "q": 0})
    cid = described["circuits"][0]["cid"]
    # Blocks are (control, target) on bits (0, 1), (2, 3), (4, 5), (6, 7) with inputs
    # 00, 01, 10, 11, so the ideal outputs are 00, 01, 11, 10; bit 7 is the leftmost character.
    counts = {cid: {"01111000": 50}}
    result = json.loads(service.ingest(described["id"], json.dumps(counts), "50"))
    assert result["shots"] == 50 and result["agreement"] == 1.0
    assert [row["counts"] for row in result["rows"]] == [{"00": 50}, {"01": 50}, {"11": 50}, {"10": 50}]
    assert json.loads(service.ingest(described["id"], counts, 50)) == result


@pytest.mark.parametrize("kind", experiments.KINDS)
def test_every_experiment_kind_returns_json(kind):
    spec = {
        "truth_table": {"kind": kind, "q": 0.05},
        "remote_bell": {"kind": kind, "qs": [0, 0.1]},
        "burst": {"kind": kind, "k": 2, "reuse": True},
        "algorithm": {"kind": kind, "algorithm": "ghz"},
        "algorithm_sweep": {"kind": kind, "algorithm": "ghz", "qs": [0, 0.1]},
    }[kind]
    described = call(service.experiment, spec)
    exact = call(service.exact, spec)
    assert "error" not in described and "error" not in exact
    assert described["kind"] == exact["kind"] == kind
    measured = call(service.ingest, described["id"], experiments.sample(spec, 500), 500)
    assert measured["kind"] == kind and measured["source"] == "measured"


@pytest.mark.parametrize("algorithm", IDS)
def test_export_qasm(algorithm):
    options = {"algorithm": algorithm, "q": 0.05, "distill": True}
    exported = call(service.export_qasm, options)
    layout = call(service.distributed, options)
    assert exported["filename"] == f"seam-{algorithm}-{call(service.plan, options)['n']}.qasm"
    assert exported["sent"] is False
    text = exported["text"]
    assert text.startswith("OPENQASM 2.0;") and exported["bytes"] == len(text.encode())
    for wire in layout["wires"]:
        assert f"// q[{wire['id']}] = {wire['label']} " in text
    parsed = qasm2.loads(text)
    assert parsed.num_qubits == layout["qubits"]["total"]
    names = {inst.operation.name for inst in parsed.data}
    assert names <= set(build.BASIS) | {"measure"}
    assert parsed.num_clbits == layout["qubits"]["data"] + layout["qubits"]["sacrifice"]


BAD_OPTIONS = [
    "not json",
    "[]",
    "42",
    "null",
    "{}",
    {"algorithm": "nope"},
    {"algorithm": 7},
    {"algorithm": "ghz", "n": 99},
    {"algorithm": "ghz", "n": "six"},
    {"algorithm": "ghz", "n": 4, "assignment": [0, 1]},
    {"algorithm": "ghz", "n": 4, "assignment": "0011"},
    {"algorithm": "ghz", "n": 4, "capacity": [1, 1]},
    {"algorithm": "ghz", "n": 4, "capacity": 3},
    {"algorithm": "ghz", "reuse": "yes"},
    {"algorithm": "bv", "params": {"secret": "1"}},
    {"algorithm": "bv", "params": "10110"},
    {"algorithm": "grover", "params": {"iterations": 9}},
]


@pytest.mark.parametrize("bad", BAD_OPTIONS, ids=range(len(BAD_OPTIONS)))
@pytest.mark.parametrize("function", ["plan", "distributed", "proof", "export_qasm"])
def test_bad_options_return_an_error_field(function, bad):
    result = call(getattr(service, function), bad)
    assert set(result) == {"error"} and isinstance(result["error"], str) and result["error"]


@pytest.mark.parametrize(
    "extra",
    [{"q": 0.9}, {"q": "0.1"}, {"q": -0.1}, {"distill": "yes"}, {"n": 8, "q": 0.1, "distill": True}],
)
def test_bad_link_settings_return_an_error_field(extra):
    options = {"algorithm": "qaoa_ring", **extra}
    for function in (service.distributed, service.export_qasm):
        assert set(call(function, options)) == {"error"}


@pytest.mark.parametrize("extra", [{"trials": 0}, {"trials": 1000}, {"trials": 2.5}, {"seed": -1}])
def test_bad_proof_settings_return_an_error_field(extra):
    assert set(call(service.proof, {"algorithm": "ghz", **extra})) == {"error"}


@pytest.mark.parametrize(
    "spec",
    [
        "not json",
        "[]",
        {},
        {"kind": "nope"},
        {"kind": ["truth_table"]},
        {"kind": "truth_table", "q": 2},
        {"kind": "remote_bell"},
        {"kind": "burst", "k": 9},
        {"kind": "algorithm"},
        {"kind": "algorithm", "algorithm": "ghz", "shots": -5},
        {"kind": "algorithm_sweep", "algorithm": "ghz", "qs": "all"},
    ],
)
def test_bad_specs_return_an_error_field(spec):
    assert set(call(service.experiment, spec)) == {"error"}
    if not (isinstance(spec, dict) and "shots" in spec):
        assert set(call(service.exact, spec)) == {"error"}


def test_bad_ingest_returns_an_error_field():
    described = call(service.experiment, {"kind": "truth_table", "q": 0.1})
    cids = [c["cid"] for c in described["circuits"]]
    good = {cid: {"00": 10} for cid in cids}
    assert "error" not in call(service.ingest, described["id"], good, 10)
    assert set(call(service.ingest, "x999999", good, 10)) == {"error"}
    assert set(call(service.ingest, described["id"], "not json", 10)) == {"error"}
    assert set(call(service.ingest, described["id"], {cids[0]: {"00": 10}}, 10)) == {"error"}
    assert set(call(service.ingest, described["id"], {**good, cids[1]: {"000": 10}}, 10)) == {"error"}
    assert set(call(service.ingest, described["id"], {**good, cids[1]: {}}, 10)) == {"error"}
    assert set(call(service.ingest, described["id"], good, "many")) == {"error"}
    assert set(call(service.ingest, described["id"], [1, 2], 10)) == {"error"}


def test_unknown_circuit_id_raises_a_clear_error():
    with pytest.raises(ValueError, match="unknown"):
        service.circuit("x999999-0")
    described = call(service.experiment, {"kind": "truth_table", "q": 0.1})
    with pytest.raises(ValueError, match="unknown circuit"):
        service.circuit(described["id"] + "-99")
