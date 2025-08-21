import argparse
import json
import os
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware import ExtraDataToPOAMiddleware

from eth_pretty_events import address_book
from eth_pretty_events.cli import (
    _env_alchemy_keys,
    _env_globals,
    _env_int,
    _env_list,
    _setup_address_book,
    _setup_web3,
    load_events,
    main,
)

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"


def _make_nt(**kwargs):
    nt_name = kwargs.pop("_name", "Unnamed")
    nt_type = namedtuple(nt_name, kwargs.keys())
    return nt_type(**kwargs)


@pytest.fixture
def mock_web3():
    with patch("eth_pretty_events.cli.Web3") as mock_web3:
        mock_instance = MagicMock()
        mock_web3.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_http_provider():
    with patch("eth_pretty_events.cli.Web3.HTTPProvider") as mock_http_provider:
        yield mock_http_provider


def test_load_events():
    Params = namedtuple("Params", "paths")
    assert load_events(Params([])) == 0


@pytest.fixture
def setup_address_book():
    args = _make_nt(address_book="samples/address-book.json")

    _setup_address_book(args, None)

    return address_book.get_default()


def test_main(capsys):
    """CLI Tests"""
    # capsys is a pytest fixture that allows asserts against stdout/stderr
    # https://docs.pytest.org/en/stable/capture.html
    main(["load_events", str(os.path.dirname(__file__) / Path("abis"))])
    captured = capsys.readouterr()
    assert "37 events found" in captured.out

    with pytest.raises(SystemExit):
        main(["foobar"])


def test_setup_web3_no_rpc_url():
    args = _make_nt(rpc_url=None)
    w3 = _setup_web3(args)
    assert w3 is None


def test_setup_web3_with_valid_rpc_url(mock_web3, mock_http_provider):
    args = _make_nt(rpc_url="https://example.com")
    mock_http_provider.return_value = Web3.HTTPProvider(args.rpc_url)
    mock_web3.is_connected.return_value = True

    result = _setup_web3(args)

    assert result == mock_web3
    mock_http_provider.assert_called_once_with(args.rpc_url)
    mock_web3.is_connected.assert_called_once()


def test_setup_web3_with_extra_data_length_error(mock_web3, mock_http_provider):
    args = _make_nt(rpc_url="https://example.com")

    mock_web3.eth.get_block.side_effect = ExtraDataLengthError
    mock_web3.is_connected.return_value = True

    result = _setup_web3(args)
    mock_web3.middleware_onion.inject.assert_called_once_with(ExtraDataToPOAMiddleware, layer=0)

    assert result == mock_web3


@pytest.mark.parametrize(
    "args_chain_id, w3_chain_id, expected_chain_id, should_raise_error, error_message",
    [
        (None, 137, 137, False, None),
        (
            None,
            None,
            None,
            True,
            "Either --chain-id or --rpc-url must be specified",
        ),
        (
            137,
            1,
            None,
            True,
            "differs with the id of the RPC connection",
        ),
    ],
)
def test_env_globals_chain_id(args_chain_id, w3_chain_id, expected_chain_id, should_raise_error, error_message):
    args = _make_nt(bytes32_rainbow=None, chain_id=args_chain_id, chains_file=None)

    if should_raise_error:
        with pytest.raises(argparse.ArgumentTypeError, match=error_message):
            _env_globals(args, w3_chain_id)
    else:
        result = _env_globals(args, w3_chain_id)
        assert result["chain_id"] == expected_chain_id
        assert result["chain"].id == expected_chain_id
        assert result["chain"].name == f"chain-{expected_chain_id}"


def test_setup_address_book(setup_address_book):
    with open("samples/address-book.json") as f:
        address_data = json.load(f)

    for address, name in address_data.items():
        assert setup_address_book.has_addr(address)
        assert setup_address_book.addr_to_name(address) == name
        assert setup_address_book.name_to_addr(name) == address


def test_setup_address_book_inverted():
    inverted_address_data = {
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "ZeroAddress": "0x0000000000000000000000000000000000000000",
    }
    with open("samples/inverted-address-book.json", "w") as f:
        json.dump(inverted_address_data, f)

    args = _make_nt(address_book="samples/inverted-address-book.json")
    _setup_address_book(args, None)

    inverted_book = address_book.get_default()

    for name, address in inverted_address_data.items():
        assert inverted_book.has_addr(address)
        assert inverted_book.addr_to_name(address) == name
        assert inverted_book.name_to_addr(name) == address


@pytest.mark.parametrize(
    "bytes32_rainbow_file, chains_file, expected_subset_b32, expected_subset_chains",
    [
        (
            "./samples/known-roles.json",
            "./samples/chains.json",
            {
                "0x55435dd261a4b9b3364963f7738a7a662ad9c84396d64be3365284bb7f0a5041": "GUARDIAN_ROLE",
                "0x499b8dbdbe4f7b12284c4a222a9951ce4488b43af4d09f42655d67f73b612fe1": "SWAP_ROLE",
            },
            {
                1: {"chainId": 1, "name": "Ethereum Mainnet"},
                10: {"chainId": 10, "name": "OP Mainnet"},
                56: {"chainId": 56, "name": "BNB Smart Chain Mainnet"},
                137: {"chainId": 137, "name": "Polygon Mainnet"},
            },
        ),
        (None, None, {}, {}),
    ],
)
def test_env_globals(bytes32_rainbow_file, chains_file, expected_subset_b32, expected_subset_chains):
    args = _make_nt(
        bytes32_rainbow=Path(bytes32_rainbow_file) if bytes32_rainbow_file else None,
        chains_file=Path(chains_file) if chains_file else None,
        chain_id="1",
    )

    ret = _env_globals(args, None)

    assert "b32_rainbow" in ret
    for key, value in expected_subset_b32.items():
        assert ret["b32_rainbow"].get(key) == value

    assert "chains" in ret
    for chain_id, expected_chain_data in expected_subset_chains.items():
        actual_chain_data = ret["chains"].get(chain_id)
        assert actual_chain_data is not None

        assert actual_chain_data.get("chainId") == expected_chain_data["chainId"]
        assert actual_chain_data.get("name") == expected_chain_data["name"]


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


def test_main_with_command(capsys):
    with patch("eth_pretty_events.cli.load_events") as mock_load_events, patch(
        "eth_pretty_events.cli.render_events"
    ) as mock_render_events, patch("eth_pretty_events.cli.setup_rendering_env") as mock_setup_rendering_env:

        mock_load_events.return_value = 25
        main(["load_events", str(os.path.dirname(__file__) / Path("abis"))])
        captured = capsys.readouterr()
        assert "25 events found" in captured.out
        mock_load_events.assert_called_once()

        mock_load_events.reset_mock()
        mock_render_events.reset_mock()

        mock_setup_rendering_env.return_value = _make_nt(abi_paths=[Path("abis")])

        main(["render_events", str(os.path.dirname(__file__) / Path("events"))])
        captured = capsys.readouterr()
        assert "events found" not in captured.out
        mock_render_events.assert_called_once()

        with pytest.raises(SystemExit):
            main(["invalid_command"])

        captured = capsys.readouterr()
        assert "Script ends here" not in captured.out


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
