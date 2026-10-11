"""The command line runs both circuits on the local simulator and prints a table."""

import pytest

from seam.__main__ import main


def test_cli_prints_the_comparison(capsys):
    assert main(["ghz", "--n", "4", "--q", "0.05", "--distill", "--shots", "400"]) == 0
    out = capsys.readouterr().out
    assert "cross gates 1  ->  pairs 1" in out
    assert "monolithic" in out and "distributed" in out
    rows = {line.split()[0]: line.split() for line in out.splitlines() if line.startswith(("mono", "dist"))}
    assert rows["monolithic"][1] == "4" and rows["distributed"][1] == "12"


def test_cli_reports_requests_that_do_not_fit(capsys):
    assert main(["qaoa_ring", "--n", "8", "--q", "0.1", "--distill"]) == 1
    assert "backend limit" in capsys.readouterr().err


def test_cli_rejects_unknown_algorithms():
    with pytest.raises(SystemExit):
        main(["nope"])
