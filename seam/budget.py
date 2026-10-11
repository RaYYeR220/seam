"""Link budget: how fast shots can be taken given a pair generation rate.

These numbers are MODELED, not measured. The model is deliberately crude: the
link produces Bell pairs one at a time at a fixed rate, a shot has to wait for
all of its raw pairs, and local gate time is ignored. With end-of-circuit
post-selection a rejected shot wastes all of its pairs.
"""

from __future__ import annotations

PAIR_RATE_HZ = 1000
SOURCE = "IonQ press release, 9 Oct 2026"
NOTE = "ion–memory entanglement events per second"
MODEL = "Modeled: 1 kHz pair rate, pairs generated one at a time, gate time ignored"


def link_info() -> dict:
    return {"pair_rate_hz": PAIR_RATE_HZ, "source": SOURCE, "note": NOTE}


def link_budget(pairs: int, raw_pairs: int, kept: float = 1.0, rate_hz: float = PAIR_RATE_HZ) -> dict:
    """Pairs consumed per shot and the shot rate the link allows.

    ``kept`` is the fraction of shots that survive distillation; the rate of
    useful shots is lower by that factor. A cut that needs no pairs is not
    limited by the link, so its rates are ``None``.
    """
    rate = rate_hz / raw_pairs if raw_pairs else None
    return {
        "pairs_per_shot": pairs,
        "raw_pairs_per_shot": raw_pairs,
        "shots_per_second": rate,
        "kept_shots_per_second": rate * kept if rate is not None else None,
        "model": MODEL,
    }
