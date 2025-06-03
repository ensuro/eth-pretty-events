from datetime import datetime, timezone
from decimal import Decimal

from jinja2 import Environment, pass_environment
from web3.constants import ADDRESS_ZERO

from .address_book import get_default as get_addr_book
from .types import ABITupleMixin, Address, Hash

MAX_UINT = 2**256 - 1


def _address(value: Address):
    return get_addr_book().addr_to_name(value)


def address(value: Address):
    return _address(value)


@pass_environment
def role(env, value: Hash):
    if value == "0x0000000000000000000000000000000000000000000000000000000000000000":
        return "DEFAULT_ADMIN_ROLE"
    return unhash(env, value)


@pass_environment
def unhash(env, value: Hash):
    if value in env.globals["b32_rainbow"]:
        unhashed = env.globals["b32_rainbow"][value]
        return (
            f"[{unhashed}](https://emn178.github.io/online-tools/keccak_256.html"
            f"?input={unhashed}&input_type=utf-8&output_type=hex)"
        )
    return value


def _explorer_url(env):
    chain_id = env.globals["chain_id"]
    try:
        chain = env.globals["chains"][chain_id]
    except KeyError:
        raise RuntimeError(f"Chain {chain_id} not found in chains")
    explorers = chain.get("explorers", [])
    if not explorers:
        return ""
    return explorers[0]["url"]


@pass_environment
def tx_explorer_link(env, value: Hash):
    url = _explorer_url(env)
    return f"{url}/tx/{value}"


@pass_environment
def block_explorer_link(env, value: int):
    url = _explorer_url(env)
    return f"{url}/block/{value}"


@pass_environment
def address_explorer_link(env, address: Address):
    url = _explorer_url(env)
    return f"{url}/address/{address}"


@pass_environment
def tx_link(env, value: Hash):
    link = tx_explorer_link(env, value)
    return f"[{value}]({link})"


@pass_environment
def block_link(env, value: int):
    link = block_explorer_link(env, value)
    return f"[{value}]({link})"


@pass_environment
def address_link(env, address: Address):
    if address == ADDRESS_ZERO:
        return "0x0"
    address_text = _address(address)
    if address_text == ADDRESS_ZERO:
        return f"[{address_text}]"
    link = address_explorer_link(env, address)
    return f"[{address_text}]({link})"


def is_struct(value):
    return isinstance(value, ABITupleMixin)


@pass_environment
def autoformat_arg(env, arg_value, arg_abi):
    if not arg_abi:
        return arg_value

    field_name = arg_abi.get("name", "")

    if arg_abi["type"] == "address":
        return address_link(env, arg_value)
    if arg_abi["type"] == "bytes32" and field_name == "role":
        return role(env, arg_value)
    if arg_abi["type"] == "bytes32":
        return unhash(env, arg_value)
    if arg_abi["type"] in ("uint256") and field_name in ("amount"):
        return amount(arg_value)
    if arg_abi["type"] in ("uint40"):
        return timestamp(arg_value)
    return arg_value


def ratio_wad(value):
    return str(Decimal(value) / Decimal(10**18))


def timestamp(value):
    dt = datetime.fromtimestamp(int(value), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def amount(value, decimals="auto"):
    if decimals == "auto":
        if value < 10**14:
            decimals = 6
        else:
            decimals = 18
    else:
        decimals = int(decimals)
    if value == MAX_UINT:
        return "infinite"
    return str(Decimal(value) / Decimal(10**decimals))


def add_filters(env: Environment):
    for fn in [
        amount,
        address,
        tx_link,
        block_link,
        address_link,
        autoformat_arg,
        unhash,
        role,
        timestamp,
        ratio_wad,
        tx_explorer_link,
        block_explorer_link,
        address_explorer_link,
    ]:
        env.filters[fn.__name__] = fn


def add_tests(env: Environment):
    for test_name, fn in {"struct": is_struct}.items():
        env.tests[test_name] = fn
