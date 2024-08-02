from decimal import Decimal

from jinja2 import Environment, pass_environment

from .address_book import get_default as get_addr_book
from .types import Address, Hash

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
def tx_link(env, value: Hash):
    url = _explorer_url(env)
    return f"[{value}]({url}/tx/{value})"


@pass_environment
def block_link(env, value: int):
    url = _explorer_url(env)
    return f"[{value}]({url}/block/{value})"


@pass_environment
def address_link(env, address: Address):
    address_text = _address(address)
    url = _explorer_url(env)
    return f"[{address_text}]({url}/address/{address})"


@pass_environment
def autoformat_arg(env, arg_value, arb_abi):
    if not arb_abi:
        return arg_value  # Shouldn't happend but I just return without any formating
    if arb_abi["type"] == "address":
        return address_link(env, arg_value)
    if arb_abi["type"] == "bytes32" and arb_abi["name"] == "role":
        return role(env, arg_value)
    if arb_abi["type"] == "bytes32":
        return unhash(env, arg_value)
    if arb_abi["type"] == "uint256" and arb_abi["name"] in ("value", "amount"):
        return amount(arg_value)
    return arg_value


def amount(value, decimals="auto"):
    if decimals == "auto":
        if value < 14**10:
            decimals = 6
        else:
            decimals = 18
    else:
        decimals = int(decimals)
    if value == MAX_UINT:
        return "infinite"
    return str(Decimal(value) / Decimal(10**decimals))


def add_filters(env: Environment):
    for fn in [amount, address, tx_link, block_link, address_link, autoformat_arg, unhash, role]:
        env.filters[fn.__name__] = fn
