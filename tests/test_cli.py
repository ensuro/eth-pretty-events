import argparse
import json
import os
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware.geth_poa import geth_poa_middleware

from eth_pretty_events import address_book
from eth_pretty_events.cli import (
    _env_globals,
    _env_int,
    _env_list,
    _events_from_alchemy_input,
    _events_from_tx,
    _setup_address_book,
    _setup_web3,
    load_events,
    main,
)
from eth_pretty_events.types import Event

from . import factories

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"


@pytest.fixture
def mock_web3():
    with patch("eth_pretty_events.cli.Web3") as mock_web3:
        mock_instance = MagicMock()
        mock_web3.return_value = mock_instance
        yield mock_web3, mock_instance


@pytest.fixture
def mock_http_provider():
    with patch("eth_pretty_events.cli.Web3.HTTPProvider") as mock_http_provider:
        yield mock_http_provider


def test_load_events():
    Params = namedtuple("Params", "paths")
    assert load_events(Params([])) == 0


@pytest.fixture
def setup_address_book():
    args = MagicMock()
    args.address_book = "samples/address-book.json"

    # Llama a _setup_address_book
    _setup_address_book(args, None)

    # Devuelve el address book configurado
    return address_book.get_default()


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


def test_setup_web3_with_valid_rpc_url(mock_web3, mock_http_provider):
    args = MagicMock(rpc_url="https://example.com")

    mock_http_provider.return_value = Web3.HTTPProvider(args.rpc_url)
    mock_web3_instance = mock_web3[1]
    mock_web3_instance.is_connected.return_value = True

    result = _setup_web3(args)

    assert result == mock_web3_instance
    mock_http_provider.assert_called_once_with(args.rpc_url)
    mock_web3[0].assert_called_once_with(mock_http_provider.return_value)
    mock_web3_instance.is_connected.assert_called_once()


def test_setup_web3_with_extra_data_length_error(mock_web3, mock_http_provider):
    args = MagicMock(rpc_url="https://example.com")

    mock_web3_instance = mock_web3[1]
    mock_web3_instance.eth.get_block.side_effect = ExtraDataLengthError
    mock_web3_instance.is_connected.return_value = True

    result = _setup_web3(args)
    mock_web3_instance.middleware_onion.inject.assert_called_once_with(geth_poa_middleware, layer=0)

    assert result == mock_web3_instance


@pytest.mark.parametrize(
    "args_chain_id, w3_chain_id, expected_chain_id, should_raise_error, error_message",
    [
        (None, 137, 137, False, None),  # Caso cuando `args.chain_id` es None y se usa el `chain_id` de `w3`
        (
            None,
            None,
            None,
            True,
            "Either --chain-id or --rpc-url must be specified",
        ),  # Caso cuando ambos `args.chain_id` y `w3` son None, debería lanzar error
        (
            137,
            1,
            None,
            True,
            "differs with the id of the RPC connection",
        ),  # Caso cuando `args.chain_id` y `w3.eth.chain_id` no coinciden, debería lanzar error
    ],
)
def test_env_globals_chain_id(args_chain_id, w3_chain_id, expected_chain_id, should_raise_error, error_message):
    args = MagicMock()
    args.bytes32_rainbow = None
    args.chain_id = args_chain_id
    args.chains_file = None

    if w3_chain_id is not None:
        w3 = MagicMock()
        w3.eth.chain_id = w3_chain_id
    else:
        w3 = None

    if should_raise_error:
        with pytest.raises(argparse.ArgumentTypeError, match=error_message):
            _env_globals(args, w3)
    else:
        result = _env_globals(args, w3)
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

    args = MagicMock()
    args.address_book = "samples/inverted-address-book.json"

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
            "samples/knownRoles.json",
            "samples/chains.json",
            {
                "0x55435dd261a4b9b3364963f7738a7a662ad9c84396d64be3365284bb7f0a5041": "GUARDIAN_ROLE",
                "0x499b8dbdbe4f7b12284c4a222a9951ce4488b43af4d09f42655d67f73b612fe1": "SWAP_ROLE",
            },
            {
                1: {"chainId": 1, "name": "Ethereum Mainnet"},
                2: {"chainId": 2, "name": "Expanse Network"},
                3: {"chainId": 3, "name": "Ropsten"},
            },
        ),
        (None, None, {}, {}),
    ],
)
def test_env_globals(bytes32_rainbow_file, chains_file, expected_subset_b32, expected_subset_chains):
    args = MagicMock()

    if bytes32_rainbow_file:
        args.bytes32_rainbow = Path(bytes32_rainbow_file)
    else:
        args.bytes32_rainbow = None

    if chains_file:
        args.chains_file = Path(chains_file)
    else:
        args.chains_file = None

    args.chain_id = "1"

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


def test_events_from_alchemy_input():
    chain = factories.Chain(id=1, name="Ethereum")
    events = list(_events_from_alchemy_input("samples/alchemy-sample.json", chain))
    assert len(events) > 0


def test_events_from_tx(mock_web3):
    mock_web3, mock_instance = mock_web3

    mock_receipt = MagicMock()
    mock_receipt.blockHash = HexBytes("0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506")
    mock_receipt.blockNumber = 34530281
    mock_receipt.transactionHash = HexBytes("0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf")
    mock_receipt.transactionIndex = 1
    mock_receipt.logs = [
        {
            "address": "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2",
            "topics": [
                HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"),
                HexBytes("0x000000000000000000000000d758af6bfc2f0908d7c5f89942be52c36a6b3cab"),
                HexBytes("0x0000000000000000000000008fca634a6edec7161def4478e94b930ea275a8a2"),
            ],
            "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
            "logIndex": 2,
            "transactionIndex": 1,
            "transactionHash": mock_receipt.transactionHash,
            "blockHash": mock_receipt.blockHash,
            "blockNumber": mock_receipt.blockNumber,
        }
    ]

    mock_instance.eth.get_transaction_receipt.return_value = mock_receipt
    mock_instance.eth.get_block.return_value.timestamp = 1625798789

    chain = factories.Chain()

    result = list(
        _events_from_tx("0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf", mock_instance, chain)
    )

    assert len(result) == len(mock_receipt.logs)
    for event in result:
        assert isinstance(event, Event)
        assert event.tx.block.hash == mock_receipt.blockHash.hex()
        assert event.tx.hash == mock_receipt.transactionHash.hex()


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
