import os
from collections import namedtuple
from pathlib import Path

import pytest

from eth_pretty_events.cli import _env_alchemy_keys, load_events, main

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"


def test_load_events():
    Params = namedtuple("Params", "paths")
    assert load_events(Params([])) == 0


def test_main(capsys):
    """CLI Tests"""
    # capsys is a pytest fixture that allows asserts against stdout/stderr
    # https://docs.pytest.org/en/stable/capture.html
    main(["load_events", str(os.path.dirname(__file__) / Path("abis"))])
    captured = capsys.readouterr()
    assert "25 events found" in captured.out

    with pytest.raises(SystemExit):
        main(["foobar"])


def test_load_alchemy_keys():
    assert _env_alchemy_keys(
        {
            "ALCHEMY_WEBHOOK_MYKEY1_ID": "wh_6kmi7uom6hn97voi",
            "ALCHEMY_WEBHOOK_MYKEY1_KEY": "T0pS3cr3t",
            "ALCHEMY_WEBHOOK_SECONDARY_ID": "wh_b43898b52bbd",
            "ALCHEMY_WEBHOOK_SECONDARY_KEY": "supersafe",
            "ANOTHER_VARIABLE": "foobar",
        }
    ) == {
        "wh_6kmi7uom6hn97voi": "T0pS3cr3t",
        "wh_b43898b52bbd": "supersafe",
    }

    with pytest.raises(ValueError, match="Missing key for ALCHEMY_WEBHOOK_MYKEY1_ID"):
        _env_alchemy_keys({"ALCHEMY_WEBHOOK_MYKEY1_ID": "wh_6kmi7uom6hn97voi"})

    assert _env_alchemy_keys({"SOME_VARIABLE": "foobar"}) == {}
