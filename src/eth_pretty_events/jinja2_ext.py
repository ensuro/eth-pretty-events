from decimal import Decimal

from jinja2 import Environment, pass_environment

MAX_UINT = 2**256 - 1


@pass_environment
def address(env, value):
    if value in env.globals["address_book"]:
        return env.globals["address_book"][value]
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
    for fn in [amount, address, tx_link]:
        env.filters[fn.__name__] = fn
