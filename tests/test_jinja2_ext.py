import json

import pytest
from jinja2 import Environment
from web3.constants import ADDRESS_ZERO

from eth_pretty_events.address_book import AddrToNameAddressBook, setup_default
from eth_pretty_events.jinja2_ext import (
    _explorer_url,
    address,
    address_explorer_link,
    address_link,
    autoformat_arg,
    block_explorer_link,
    block_link,
    is_struct,
    ratio_wad,
    role,
    tx_explorer_link,
    tx_link,
)
from eth_pretty_events.types import Hash

from . import factories


@pytest.fixture
def setup_environment():
    env = Environment()

    with open("./samples/known-roles.json") as f:
        known_roles = json.load(f)

    with open("./samples/chains.json") as f:
        chains = json.load(f)

    env.globals["b32_rainbow"] = known_roles
    env.globals["chain_id"] = 0
    env.globals["chains"] = chains

    return env


def test_address():
    addr_book = AddrToNameAddressBook({"0x1234567890abcdef1234567890abcdef12345678": "Mocked Name Address"})
    setup_default(addr_book)

    result = address("0x1234567890abcdef1234567890abcdef12345678")
    assert result == "Mocked Name Address"


def test_role_default_admin(setup_environment):
    env = setup_environment
    value = Hash(value="0x0000000000000000000000000000000000000000000000000000000000000000")
    assert role(env, value) == "DEFAULT_ADMIN_ROLE"


def test_role_unhash(setup_environment):
    env = setup_environment
    hash = next(iter(env.globals["b32_rainbow"]))
    name = env.globals["b32_rainbow"][hash]
    value = Hash(value=hash)
    assert role(env, value) == (
        f"[{name}](https://emn178.github.io/online-tools/keccak_256.html"
        f"?input={name}&input_type=utf-8&output_type=hex)"
    )


def test_role_without_unhash():
    env = Environment()
    env.globals["b32_rainbow"] = {}
    value = Hash(value="0xdef4560000000000000000000000000000000000000000000000000000000000")
    assert role(env, value) == value


@pytest.mark.parametrize(
    "link_function, value, expected_suffix",
    [
        (tx_link, "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd", "/tx/0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"),
        (block_link, 12345, "/block/12345"),
    ],
)
def test_link_functions(setup_environment, link_function, value, expected_suffix):
    env = setup_environment
    chain_id = env.globals["chain_id"]
    chains_data = env.globals["chains"]
    result = link_function(env, value)
    base_url = chains_data[chain_id]["explorers"][0]["url"] if chains_data[chain_id]["explorers"] else ""
    expected_result = f"[{value}]({base_url}{expected_suffix})"
    assert result == expected_result


@pytest.mark.parametrize(
    "address, expected_output",
    [
        (
            ADDRESS_ZERO,
            "0x0",
        ),
        (
            "0x1234567890abcdef1234567890abcdef12345678",
            "[Mocked Name](https://etherscan.io/address/0x1234567890abcdef1234567890abcdef12345678)",
        ),
    ],
)
def test_address_link(setup_environment, address, expected_output):
    env = setup_environment

    addr_book = AddrToNameAddressBook({address: "Mocked Name"})
    setup_default(addr_book)

    result = address_link(env, address)
    assert result == expected_output


@pytest.mark.parametrize(
    "link_function, value, expected_result",
    [
        (
            tx_explorer_link,
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            "https://etherscan.io/tx/0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        ),
        (block_explorer_link, 12345, "https://etherscan.io/block/12345"),
        (
            address_explorer_link,
            "0x1234567890abcdef1234567890abcdef12345678",
            "https://etherscan.io/address/0x1234567890abcdef1234567890abcdef12345678",
        ),
    ],
)
def test_explorer_links(setup_environment, link_function, value, expected_result):
    env = setup_environment
    result = link_function(env, value)
    assert result == expected_result


@pytest.mark.parametrize(
    "chain_id, chains_data, expected_result",
    [
        (
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            "https://etherscan.io",
        ),
        (
            1,
            {1: {"name": "Ethereum", "explorers": []}},
            "",
        ),
    ],
)
def test_explorer_url(chain_id, chains_data, expected_result):
    env = Environment()
    env.globals["chain_id"] = chain_id
    env.globals["chains"] = chains_data
    result = _explorer_url(env)
    assert result == expected_result


def test_explorer_url_chain_not_found():
    chain_id = 1
    env = Environment()
    env.globals["chain_id"] = chain_id
    env.globals["chains"] = {}

    with pytest.raises(RuntimeError, match=f"Chain {chain_id} not found in chains"):
        _explorer_url(env)


@pytest.mark.parametrize(
    "input_value, expected_output",
    [
        (factories.NewPolicyArgs().policy, True),
        ((1, 2, 3), False),
        ([1, 2, 3], False),
        ("string", False),
        ({"key": "value"}, False),
        (123, False),
        (None, False),
    ],
)
def test_is_struct(input_value, expected_output):
    result = is_struct(input_value)
    assert result == expected_output


@pytest.mark.parametrize(
    "arg_value, arg_abi, expected_output",
    [
        (
            "0x1234567890abcdef1234567890abcdef12345678",
            {"type": "address"},
            "[Mocked Name](https://etherscan.io/address/0x1234567890abcdef1234567890abcdef12345678)",
        ),
        (
            "0x0000000000000000000000000000000000000000000000000000000000000000",
            {"type": "bytes32", "name": "role"},
            "DEFAULT_ADMIN_ROLE",
        ),
        (
            "0xabc1230000000000000000000000000000000000000000000000000000000000",
            {"type": "bytes32", "name": "example_role"},
            "0xabc1230000000000000000000000000000000000000000000000000000000000",
        ),
        (1234567890, {"type": "uint256", "name": "amount"}, "1234.56789"),
        (289254654977, {"type": "uint256", "name": "amount"}, "289254.654977"),
        (2**256 - 1, {"type": "uint256", "name": "amount"}, "infinite"),
        (1234567890, {"type": "uint40", "name": "timestamp"}, "2009-02-13T23:31:30Z"),
        (1723044031, {"type": "uint40", "name": "start"}, "2024-08-07T15:20:31Z"),
        (1723189500, {"type": "uint40", "name": "expiration"}, "2024-08-09T07:45:00Z"),
        ("arbitrary_value", {"type": "unknown"}, "arbitrary_value"),
        ("no_format_should_not_happen", None, "no_format_should_not_happen"),
    ],
)
def test_autoformat_arg(setup_environment, arg_value, arg_abi, expected_output):
    env = setup_environment
    result = autoformat_arg(env, arg_value, arg_abi)
    assert result == expected_output


@pytest.mark.parametrize(
    "input_value, expected_output",
    [
        (1, "1E-18"),
        (10**18, "1"),
        (5 * 10**17, "0.5"),
        (123456789012345678, "0.123456789012345678"),
        (0, "0"),
    ],
)
def test_ratio_wad(input_value, expected_output):
    assert ratio_wad(input_value) == expected_output
