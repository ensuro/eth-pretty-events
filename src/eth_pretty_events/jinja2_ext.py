from decimal import Decimal

from jinja2 import Environment, pass_environment

MAX_UINT = 2**256 - 1


def _address(env, value):
    if value in env.globals["address_book"]:
        return env.globals["address_book"][value]
    return value


@pass_environment
def address(env, value):
    return _address(env, value)


@pass_environment
def role(env, value):
    if value == (b"\x00" * 32):
        return "DEFAULT_ADMIN_ROLE"
    return unhash(env, value)


@pass_environment
def unhash(env, value):
    value = f"0x{value.hex()}"
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
def tx_link(env, value):
    value = value.hex()
    url = _explorer_url(env)
    return f"[{value}]({url}/tx/{value})"


@pass_environment
def block_link(env, value):
    url = _explorer_url(env)
    return f"[{value}]({url}/block/{value})"


@pass_environment
def address_link(env, address):
    address_text = _address(env, address)
    url = _explorer_url(env)
    return f"[{address_text}]({url}/address/{address})"


@pass_environment
def autoformat_arg(env, arg_value, abi, arg_name):
    arg_meta = next((x for x in abi["inputs"] if x["name"] == arg_name), None)
    if not arg_meta:
        return arg_name  # Shouldn't happend but I just return without any formating
    if arg_meta["type"] == "address":
        return address_link(env, arg_value)
    if arg_meta["type"] == "bytes32" and arg_name == "role":
        return role(env, arg_value)
    if arg_meta["type"] == "bytes32":
        return unhash(env, arg_value)
    if arg_meta["type"] == "uint256" and arg_name in ("value", "amount"):
        return amount(arg_value)
    return arg_name


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
