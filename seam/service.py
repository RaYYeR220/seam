"""JSON front door of the engine; the only module the page imports.

Every function takes and returns JSON strings, except :func:`circuit`, which
returns the Qiskit circuit to submit. Anything a user can cause comes back as
``{"error": "<sentence>"}`` instead of an exception.
"""

from __future__ import annotations

import base64
import functools
import json
from typing import Callable

from qiskit import QuantumCircuit, qasm2

from . import algorithms, budget, build, experiments, link, verify
from .plan import Plan, make_plan

MAX_TRIALS = 64


def _loads(value: object, what: str) -> object:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{what} is not valid JSON") from exc
    return value


def _api(function: Callable[..., dict]) -> Callable[..., str]:
    @functools.wraps(function)
    def wrapper(*args: object, **kwargs: object) -> str:
        try:
            result = function(*args, **kwargs)
        except ValueError as exc:
            result = {"error": str(exc)}
        except (KeyError, TypeError) as exc:
            result = {"error": f"Bad request: {exc!r}"}
        except Exception as exc:
            result = {"error": f"Internal error: {exc!r}"}
        return json.dumps(result)

    return wrapper


def _options(raw: object) -> dict:
    options = _loads(raw, "options")
    if not isinstance(options, dict):
        raise ValueError("options must be a JSON object")
    return options


def _link_settings(options: dict) -> tuple[float, bool]:
    q = options.get("q", 0.0)
    if isinstance(q, bool) or not isinstance(q, (int, float)):
        raise ValueError("'q' must be a number between 0 and 0.5")
    distill = options.get("distill", False)
    if not isinstance(distill, bool):
        raise ValueError("'distill' must be true or false")
    return link.check_error_rate(q), distill


def _distributed(options: dict) -> tuple[Plan, build.Distributed]:
    plan = make_plan(options)
    q, distill = _link_settings(options)
    plan.check_fits(q, distill)
    return plan, build.distribute(plan.gates, plan.assignment, plan.bursts, q, distill)


@_api
def catalog() -> dict:
    """Algorithms on offer, the backend limit, the link rate and the basis gates."""
    return {
        "algorithms": [a.describe() for a in algorithms.CATALOG.values()],
        "limits": {"max_backend_qubits": build.MAX_BACKEND_QUBITS},
        "link": budget.link_info(),
        "basis": list(build.BASIS),
        "experiments": list(experiments.KINDS),
    }


@_api
def plan(options: object) -> dict:
    """Lowered gates, the cut, its bursts and what it costs in pairs and qubits."""
    made = make_plan(_options(options))
    made.check_fits()
    return made.to_dict()


@_api
def distributed(options: object) -> dict:
    """Drawing data for the distributed circuit (plan options plus ``q`` and ``distill``)."""
    return _distributed(_options(options))[1].layout()


@_api
def proof(options: object) -> dict:
    """Statevector proof of equivalence on a perfect link, with a negative control."""
    options = _options(options)
    made = make_plan(options)
    made.check_fits()
    trials = options.get("trials", 16)
    if isinstance(trials, bool) or not isinstance(trials, int) or not 1 <= trials <= MAX_TRIALS:
        raise ValueError(f"'trials' must be an integer from 1 to {MAX_TRIALS}")
    seed = options.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("'seed' must be a non-negative integer")
    return verify.prove(made.gates, made.assignment, made.bursts, trials, seed).to_dict()


@_api
def experiment(spec: object) -> dict:
    """Build and cache the circuits of an experiment; returns their ids."""
    return experiments.describe(_options(spec))


def circuit(cid: str) -> QuantumCircuit:
    """Transpiled, measured circuit for a circuit id returned by :func:`experiment`."""
    return experiments.circuit(cid)


@_api
def ingest(experiment_id: str, counts_by_cid: object, shots: object = None) -> dict:
    """Result of an experiment from backend counts keyed by circuit id."""
    counts = _loads(counts_by_cid, "counts")
    if isinstance(shots, str):
        shots = _loads(shots, "shots")
    if shots is not None and (isinstance(shots, bool) or not isinstance(shots, (int, float))):
        raise ValueError("'shots' must be a number")
    return experiments.ingest(str(experiment_id), counts, None if shots is None else int(shots))


@_api
def exact(spec: object) -> dict:
    """Result of an experiment computed exactly, without a backend."""
    return experiments.exact(_options(spec))


def _send(filename: str, text: str) -> bool:
    """Offer the file for download when running inside the Qollab page."""
    try:
        from js import sendFile

        encoded = base64.b64encode(text.encode()).decode()
        sendFile(filename, "text/plain", "data:text/plain;base64," + encoded)
        return True
    except Exception:
        return False


@_api
def export_qasm(options: object) -> dict:
    """OpenQASM 2 of the distributed circuit, with every wire named in the header."""
    made, dist = _distributed(_options(options))
    lines = qasm2.dumps(dist.backend_circuit()).split("\n")
    body = next(k for k, line in enumerate(lines) if line.startswith("qreg"))
    module = {0: "Trap A", 1: "Trap B", None: "environment"}
    header = [
        f"// Seam: {made.instance.algorithm} on {made.n} qubits, split across two ion-trap modules",
        f"// Bell pairs: {dist.pairs} ({dist.raw_pairs} raw); only pair generation and",
        "// the deferred classical bits (cx a->b, cz b->control) cross the link",
    ]
    header += [f"// q[{w.id}] = {w.label} ({w.kind}, {module[w.module]})" for w in dist.wires]
    flags = "; f = distillation flags, keep a shot when each pair of bits agrees"
    header.append("// c = data bits" + (flags if dist.flags else ""))
    text = "\n".join(lines[:body] + header + lines[body:])
    if not text.endswith("\n"):
        text += "\n"
    filename = f"seam-{made.instance.algorithm}-{made.n}.qasm"
    return {
        "filename": filename,
        "bytes": len(text.encode()),
        "sent": _send(filename, text),
        "text": text,
    }
