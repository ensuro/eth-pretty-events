import os
from pathlib import Path

import pytest

from eth_pretty_events.cli import load_events, main

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"


def test_load_events():
    assert load_events([]) == 0


def test_main(capsys):
    """CLI Tests"""
    # capsys is a pytest fixture that allows asserts against stdout/stderr
    # https://docs.pytest.org/en/stable/capture.html
    main(["load_events", str(os.path.dirname(__file__) / Path("abis"))])
    captured = capsys.readouterr()
    assert "18 events found" in captured.out

    with pytest.raises(SystemExit):
        main(["foobar"])
