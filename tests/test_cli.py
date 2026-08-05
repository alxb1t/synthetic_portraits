"""CLI skeleton (Phase 1: bare entry point; real flags land in Phase 2)."""

from __future__ import annotations

import pytest

from synthetic_portraits import cli


def test_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "prompt" in capsys.readouterr().out.lower()


def test_generate_entry_point_delegates_to_cli_main():
    # generate.py is a thin wrapper around cli.main; importing must not run it.
    import generate

    assert generate.main is cli.main
