"""Command line: plan a split, run both circuits locally and compare them.

    python -m seam ghz --n 6 --q 0.05 --distill --shots 4000
"""

from __future__ import annotations

import argparse
import json
import sys

from . import algorithms, service


def _run(spec: dict, shots: int, seed: int) -> dict:
    from qiskit.providers.basic_provider import BasicSimulator

    described = json.loads(service.experiment(json.dumps(spec)))
    if "error" in described:
        return described
    backend = BasicSimulator()
    counts = {}
    for entry in described["circuits"]:
        job = backend.run(service.circuit(entry["cid"]), shots=shots, seed_simulator=seed)
        counts[entry["cid"]] = job.result().get_counts()
    return json.loads(service.ingest(described["id"], json.dumps(counts), shots))


def _cell(entry: dict, name: str) -> str:
    value = entry.get(name)
    return "   -   " if value is None else f"{value:7.4f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seam", description=__doc__.splitlines()[0])
    parser.add_argument("algorithm", choices=sorted(algorithms.CATALOG))
    parser.add_argument("--n", type=int, default=None, help="number of qubits")
    parser.add_argument("--q", type=float, default=0.0, help="link error probability")
    parser.add_argument("--distill", action="store_true", help="distill two raw pairs into one")
    parser.add_argument("--shots", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    options = {"algorithm": args.algorithm, "n": args.n}
    plan = json.loads(service.plan(json.dumps(options)))
    spec = {"kind": "algorithm", **options, "q": args.q, "distill": args.distill, "shots": args.shots}
    measured = plan if "error" in plan else _run(spec, args.shots, args.seed)
    if "error" in measured:
        print(f"error: {measured['error']}", file=sys.stderr)
        return 1
    theory = json.loads(service.exact(json.dumps(spec)))

    cut = plan["cut"]
    modules = ["".join(f" q{i}" for i, m in enumerate(plan["assignment"]) if m == side) for side in (0, 1)]
    print(f"{args.algorithm}  n={plan['n']}  Trap A:{modules[0]}  |  Trap B:{modules[1]}")
    print(
        f"cross gates {cut['cross_gates']}  ->  pairs {cut['pairs']} "
        f"(without reuse {cut['pairs_without_reuse']})   link error q={args.q:g}"
        f"{'  distilled' if args.distill else ''}   shots {args.shots}"
    )
    print(f"{'':12s}{'qubits':>7s}{'depth':>7s}{'success':>9s}{'hellinger':>11s}{'exact':>9s}{'kept':>7s}")
    metric = measured["metric"]
    for name, label in (("mono", "monolithic"), ("dist", "distributed")):
        row, ideal = measured[name], theory[name]
        kept = f"{row['kept']:7.3f}" if "kept" in row else ""
        print(
            f"{label:12s}{row['qubits']:7d}{row['depth']:7d}  {_cell(row, 'success')}"
            f"    {_cell(row, 'hellinger')}  {_cell(ideal, metric)}{kept}"
        )
    guess = measured["classical_guess"]
    print(f"exact column: {metric} predicted without sampling; classical guess {guess:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
