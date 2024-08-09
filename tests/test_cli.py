import json
import os
import tempfile
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

import pytest

from eth_pretty_events import address_book
from eth_pretty_events.cli import (
    _env_globals,
    _env_int,
    _env_list,
    _events_from_alchemy_input,
    _setup_address_book,
    _setup_web3,
    load_events,
    main,
)

from . import factories

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"


def test_load_events():
    Params = namedtuple("Params", "paths")
    assert load_events(Params([])) == 0


# TODO test_setup_address_book


def test_main(capsys):
    """CLI Tests"""
    # capsys is a pytest fixture that allows asserts against stdout/stderr
    # https://docs.pytest.org/en/stable/capture.html
    main(["load_events", str(os.path.dirname(__file__) / Path("abis"))])
    captured = capsys.readouterr()
    assert "25 events found" in captured.out

    with pytest.raises(SystemExit):
        main(["foobar"])


def test_setup_web3_no_rpc_url():
    Params = namedtuple("Params", "rpc_url")
    args = Params(None)
    w3 = _setup_web3(args)
    assert w3 is None


def test_setup_address_book_addr_to_name():  # When done, use test_setup_address_book
    Params = namedtuple("Params", "address_book")

    mock_addr_data = {
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": "USDC",
        "0x0000000000000000000000000000000000000000": "ZeroAddress",
    }
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f.write(json.dumps(mock_addr_data))
        f.flush()
        args = Params(f.name)

        _setup_address_book(args, None)

        addr_book = address_book.get_default()

        assert isinstance(addr_book, address_book.AddrToNameAddressBook)

        assert addr_book.has_addr("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
        assert addr_book.addr_to_name("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174") == "USDC"


def test_setup_address_book_name_to_addr():  # When done, use test_setup_address_book
    Params = namedtuple("Params", "address_book")

    mock_addr_data = {
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "ZeroAddress": "0x0000000000000000000000000000000000000000",
    }

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f.write(json.dumps(mock_addr_data))
        f.flush()
        args = Params(f.name)

        _setup_address_book(args, None)

        addr_book = address_book.get_default()

        assert isinstance(addr_book, address_book.NameToAddrAddressBook)

        assert addr_book.has_addr("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
        assert addr_book.addr_to_name("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174") == "USDC"


@pytest.mark.parametrize(
    "bytes32_rainbow_data, expected_output",
    [
        ({"0x12345": "Hash1", "0x67890": "Hash2"}, {"0x12345": "Hash1", "0x67890": "Hash2"}),
        (None, {}),
    ],
)
def test_env_globals_bytes32_rainbow(bytes32_rainbow_data, expected_output):  # When done, use test_setup_address_book
    Params = namedtuple("Params", "bytes32_rainbow chain_id chains_file")

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        if bytes32_rainbow_data:
            f.write(json.dumps(bytes32_rainbow_data))
            f.flush()
            bytes32_rainbow_path = f.name
        else:
            bytes32_rainbow_path = None

        args = Params(bytes32_rainbow=bytes32_rainbow_path, chain_id="1", chains_file=None)

    ret = _env_globals(args, None)

    assert "b32_rainbow" in ret
    assert ret["b32_rainbow"] == expected_output


def test_events_from_alchemy_input_empty_logs():  # When done, use test_setup_address_book

    chain = factories.Chain(id=1, name="Ethereum")
    block = factories.Block(
        chain=chain,
        number=12345,
        hash=factories.Hash(),
        timestamp=1630468382,
    )

    alchemy_data = {
        "event": {
            "data": {
                "block": {
                    "number": block.number,
                    "hash": block.hash,
                    "timestamp": block.timestamp,
                    "logs": [],
                }
            }
        }
    }

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        json.dump(alchemy_data, f)
        f.flush()

        events = list(_events_from_alchemy_input(f.name, chain))

    assert len(events) == 0


def test_env_list_with_value():
    with patch.dict(os.environ, {"TEST_VAR": "value1 value2 value3"}):
        result = _env_list("TEST_VAR")
        assert result == ["value1", "value2", "value3"]

    with patch.dict(os.environ, {}, clear=True):
        result = _env_list("TEST_VAR")
        assert result is None


def test_env_int_with_value():
    with patch.dict(os.environ, {"TEST_INT": "123"}):
        result = _env_int("TEST_INT")
        assert result == 123

    with patch.dict(os.environ, {}, clear=True):
        result = _env_int("TEST_INT")
        assert result is None
