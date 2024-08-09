import pytest
from jinja2 import Environment
from web3.constants import ADDRESS_ZERO

from eth_pretty_events.address_book import AddrToNameAddressBook, setup_default
from eth_pretty_events.jinja2_ext import (
    _explorer_url,
    add_filters,
    address,
    address_link,
    autoformat_arg,
    block_link,
    role,
    tx_link,
)

from . import factories

EMN178 = "https://emn178.github.io/online-tools/keccak_256.html?input=example_role&input_type=utf-8&output_type=hex"


def test_address():
    addr_book = AddrToNameAddressBook({"0x1234567890abcdef1234567890abcdef12345678": "Mocked Name Address"})
    setup_default(addr_book)

    result = address("0x1234567890abcdef1234567890abcdef12345678")
    assert result == "Mocked Name Address"


def test_role_default_admin():
    env = Environment()
    value = factories.Hash(value="0x0000000000000000000000000000000000000000000000000000000000000000")
    assert role(env, value) == "DEFAULT_ADMIN_ROLE"


def test_role_unhash():
    env = Environment()
    env.globals["b32_rainbow"] = {"0xabc1230000000000000000000000000000000000000000000000000000000000": "example_role"}
    value = factories.Hash(value="0xabc1230000000000000000000000000000000000000000000000000000000000")

    assert role(env, value) == f"[example_role]({EMN178})"


def test_role_without_unhash():
    env = Environment()
    env.globals["b32_rainbow"] = {}
    value = factories.Hash(value="0xdef4560000000000000000000000000000000000000000000000000000000000")
    assert role(env, value) == value


@pytest.mark.parametrize(
    "link_function, value, chain_id, chains_data, expected_suffix, exception_expected",
    [
        (
            tx_link,
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            "/tx/0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            False,
        ),
        (
            block_link,
            12345,
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            "/block/12345",
            False,
        ),
        (
            tx_link,
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            2,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            None,
            True,
        ),
        (block_link, 12345, 1, {1: {"name": "Ethereum", "explorers": []}}, "/block/12345", False),
    ],
)
def test_link_functions(link_function, value, chain_id, chains_data, expected_suffix, exception_expected):
    env = Environment()
    env.globals["chain_id"] = chain_id
    env.globals["chains"] = chains_data

    if exception_expected:
        with pytest.raises(RuntimeError, match=f"Chain {chain_id} not found in chains"):
            link_function(env, value)
    else:
        result = link_function(env, value)
        base_url = chains_data[chain_id]["explorers"][0]["url"] if chains_data[chain_id]["explorers"] else ""
        expected_result = f"[{value}]({base_url}{expected_suffix})"
        assert result == expected_result


@pytest.mark.parametrize(
    "address, chain_id, chains, expected_output, expected_exception",
    [
        (
            "0x1234567890abcdef1234567890abcdef12345678",
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            "[Mocked Name](https://etherscan.io/address/0x1234567890abcdef1234567890abcdef12345678)",
            None,
        ),
        (
            ADDRESS_ZERO,
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            f"[{ADDRESS_ZERO}]",
            None,
        ),
        (
            "0x1234567890abcdef1234567890abcdef12345678",
            2,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            None,
            RuntimeError,
        ),
    ],
)
def test_address_link(address, chain_id, chains, expected_output, expected_exception):
    env = Environment()
    env.globals["chain_id"] = chain_id
    env.globals["chains"] = chains

    addr_book = AddrToNameAddressBook({address: "Mocked Name"})
    setup_default(addr_book)

    if expected_exception:
        with pytest.raises(expected_exception):
            address_link(env, address)
    else:
        result = address_link(env, address)
        assert result == expected_output


"""
Consultar si dejar este test especifico de la funcion _exporer_url
ya que se testea con las funciónes de arriba
"""


@pytest.mark.parametrize(
    "chain_id, chains_data, expected_result, expected_exception",
    [
        (
            1,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            "https://etherscan.io",
            None,
        ),
        (
            2,
            {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}},
            None,
            RuntimeError,
        ),
        (
            1,
            {1: {"name": "Ethereum", "explorers": []}},
            "",
            None,
        ),
        (
            1,
            {},
            None,
            RuntimeError,
        ),
    ],
)
def test_explorer_url(chain_id, chains_data, expected_result, expected_exception):
    env = Environment()
    env.globals["chain_id"] = chain_id
    env.globals["chains"] = chains_data

    if expected_exception:
        with pytest.raises(expected_exception, match=f"Chain {chain_id} not found in chains"):
            _explorer_url(env)
    else:
        result = _explorer_url(env)
        assert result == expected_result


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
            f"[example_role]({EMN178})",
        ),
        (1234567890, {"type": "uint256", "name": "amount"}, "1234.56789"),
        (289254654977, {"type": "uint256", "name": "amount"}, "2.89254654977E-7"),
        (2**256 - 1, {"type": "uint256", "name": "amount"}, "infinite"),
        (1234567890, {"type": "uint256", "name": "timestamp"}, "2009-02-13T23:31:30Z"),
        (10**18, {"type": "uint256", "name": "loss_prob"}, "1"),
        ("arbitrary_value", {"type": "unknown"}, "arbitrary_value"),
        ("no_format_should_not_happen", None, "no_format_should_not_happen"),
    ],
)
def test_autoformat_arg(arg_value, arg_abi, expected_output):
    env = Environment()
    env.globals["b32_rainbow"] = {"0xabc1230000000000000000000000000000000000000000000000000000000000": "example_role"}
    env.globals["chain_id"] = 1
    env.globals["chains"] = {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}}
    addr_book = AddrToNameAddressBook({"0x1234567890abcdef1234567890abcdef12345678": "Mocked Name"})
    setup_default(addr_book)

    result = autoformat_arg(env, arg_value, arg_abi)
    assert result == expected_output


def test_add_filters():
    env = Environment()
    add_filters(env)
    addr = "0xabc1230000000000000000000000000000000000000000000000000000000000"
    expected_filters = [
        "amount",
        "address",
        "tx_link",
        "block_link",
        "address_link",
        "autoformat_arg",
        "unhash",
        "role",
        "timestamp",
        "loss_prob",
    ]

    addr_book = AddrToNameAddressBook({"0x1234567890abcdef1234567890abcdef12345678": "Mocked Name"})
    setup_default(addr_book)
    env.globals["b32_rainbow"] = {addr: "example_role"}
    env.globals["chain_id"] = 1
    env.globals["chains"] = {1: {"name": "Ethereum", "explorers": [{"url": "https://etherscan.io"}]}}

    for filter_name in expected_filters:
        assert filter_name in env.filters
        assert callable(env.filters[filter_name])

    template = env.from_string("{{ 1234567890 | amount }}")
    rendered = template.render()
    assert rendered == "1234.56789"

    template = env.from_string("{{ '0x1234567890abcdef1234567890abcdef12345678' | address }}")
    rendered = template.render()
    assert rendered == "Mocked Name"

    template = env.from_string(f"{{{{ '{addr}' | tx_link }}}}")
    rendered = template.render()
    assert rendered == f"[{addr}](https://etherscan.io/tx/{addr})"

    template = env.from_string("{{ 123456 | block_link }}")
    rendered = template.render()
    assert rendered == "[123456](https://etherscan.io/block/123456)"

    template = env.from_string("{{ '0x1234567890abcdef1234567890abcdef12345678' | address_link }}")
    rendered = template.render()
    assert rendered == "[Mocked Name](https://etherscan.io/address/0x1234567890abcdef1234567890abcdef12345678)"

    template = env.from_string("{{ 1234567890 | autoformat_arg({'type': 'uint256', 'name': 'amount'}) }}")
    rendered = template.render()
    assert rendered == "1234.56789"

    template = env.from_string(f"{{{{ '{addr}' | unhash }}}}")
    rendered = template.render()
    assert rendered == f"[example_role]({EMN178})"

    template = env.from_string(f"{{{{ '{addr}' | role }}}}")
    rendered = template.render()
    assert rendered == f"[example_role]({EMN178})"

    template = env.from_string("{{ 1234567890 | timestamp }}")
    rendered = template.render()
    assert rendered == "2009-02-13T23:31:30Z"

    template = env.from_string("{{ 1000000000000000000 | loss_prob }}")
    rendered = template.render()
    assert rendered == "1"
