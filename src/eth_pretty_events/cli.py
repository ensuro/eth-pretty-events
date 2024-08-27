import argparse
import itertools
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import jinja2
import yaml
from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware.geth_poa import geth_poa_middleware

from eth_pretty_events import __version__, address_book, decode_events, render
from eth_pretty_events.event_filter import (
    TemplateRule,
    find_template,
    read_template_rules,
)
from eth_pretty_events.event_parser import EventDefinition
from eth_pretty_events.types import Address, Chain

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"

_logger = logging.getLogger(__name__)


def load_events(args):
    """Loads all the events found in .json in the provided paths

    Args:
      paths (list<str>): list of paths to walk to read the ABIs

    Returns:
      int: Number of events found
    """
    events_found = EventDefinition.load_all_events(args.paths)
    for evt in events_found:
        _logger.info(evt)
    return len(events_found)


@dataclass
class RenderingEnv:
    jinja_env: "jinja2.Environment"
    w3: Optional[Web3]
    chain: Chain
    template_rules: Sequence[TemplateRule]
    args: Any


def _setup_web3(args) -> Optional[Web3]:
    if args.rpc_url is None:
        return None
    w3 = Web3(Web3.HTTPProvider(args.rpc_url))
    assert w3.is_connected()
    try:
        w3.eth.get_block("latest")
    except ExtraDataLengthError:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3


def _setup_address_book(args, _: Optional[Web3]):
    if args.address_book:
        addr_data = json.load(open(args.address_book))
        try:
            addr_data = dict((Address(k), v) for (k, v) in addr_data.items())
            class_ = address_book.AddrToNameAddressBook
        except ValueError:
            addr_data = dict((k, Address(v)) for (k, v) in addr_data.items())
            class_ = address_book.NameToAddrAddressBook
        address_book.setup_default(class_(addr_data))


def _env_globals(args, w3):
    ret = {}
    if args.bytes32_rainbow:
        ret["b32_rainbow"] = json.load(open(args.bytes32_rainbow))
        # TODO: process hashes or invert the dict
    else:
        ret["b32_rainbow"] = {}

    if args.chain_id:
        chain_id = ret["chain_id"] = int(args.chain_id)
        if w3 and chain_id != w3.eth.chain_id:
            raise argparse.ArgumentTypeError(
                f"--chain-id={chain_id} differs with the id of the RPC connection {w3.eth.chain_id}"
            )
    elif w3:
        chain_id = ret["chain_id"] = w3.eth.chain_id
    else:
        raise argparse.ArgumentTypeError("Either --chain-id or --rpc-url must be specified")

    if args.chains_file:
        # https://chainid.network/chains.json like file
        chains = json.load(open(args.chains_file))
        chains = ret["chains"] = dict((c["chainId"], c) for c in chains)
    else:
        chains = ret["chains"] = {}

    ret["chain"] = Chain(
        id=chain_id,
        name=chains.get(chain_id, {"name": f"chain-{chain_id}"})["name"],
        metadata=chains.get(chain_id, None),
    )

    return ret


def setup_rendering_env(args) -> RenderingEnv:
    """Sets up the rendering environment"""
    EventDefinition.load_all_events(args.abi_paths)
    w3 = _setup_web3(args)
    env_globals = _env_globals(args, w3)
    chain = env_globals["chain"]

    _setup_address_book(args, w3)

    jinja_env = render.init_environment(args.template_paths, env_globals)

    template_rules = read_template_rules(yaml.load(open(args.template_rules), yaml.SafeLoader))
    return RenderingEnv(
        w3=w3,
        jinja_env=jinja_env,
        template_rules=template_rules,
        chain=chain,
        args=args,
    )


def render_events(renv: RenderingEnv, input: str):
    """Renders the events found in a given input

    Returns:
      int: Number of events found
    """

    if input.endswith(".json"):
        events = decode_events.decode_from_alchemy_input(json.load(open(input)), renv.chain)
    elif input.startswith("0x") and len(input) == 66:
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a transaction hash
        events = decode_events.decode_events_from_tx(input, renv.w3, renv.chain)
    elif input.isdigit():
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a block number
        events = decode_events.decode_events_from_block(int(input), renv.w3, renv.chain)
    elif input.replace("-", "").isdigit():
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        block_from, block_to = input.split("-")
        blocks = range(int(block_from), int(block_to) + 1)
        events = itertools.chain.from_iterable(
            decode_events.decode_events_from_block(block, renv.w3, renv.chain) for block in blocks
        )
    else:
        raise argparse.ArgumentTypeError(f"Unknown input '{input}'")

    for event in events:
        if not event:
            continue
        template_name = find_template(renv.template_rules, event)
        if template_name is None:
            continue
        print(render.render(renv.jinja_env, event, template_name))
        print("--------------------------")


# ---- CLI ----
# The functions defined in this section are wrappers around the main Python
# API allowing them to be called directly from the terminal as a CLI
# executable/script.


def _env_list(env_var) -> Optional[Sequence[str]]:
    value = os.environ.get(env_var)
    if value is not None:
        return value.split()
    return None


def _env_int(env_var) -> Optional[int]:
    value = os.environ.get(env_var)
    if value is not None:
        return int(value)
    return None


def _env_alchemy_keys(env) -> dict:
    keys = {}
    for var, value in env.items():
        if var.startswith("ALCHEMY_WEBHOOK_") and var.endswith("_ID"):
            try:
                key = env[f"{var[:-len('_ID')]}_KEY"]
            except KeyError:
                raise ValueError(f"Missing key for {var}")
            keys[value] = key
    return keys


def parse_args(args):
    """Parse command line parameters

    Args:
      args (List[str]): command line parameters as list of strings
          (for example  ``["--help"]``).

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(description="Different commands to execute eth-pretty-events from command line")
    parser.add_argument(
        "--version",
        action="version",
        version=f"eth-pretty-events {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        help="set loglevel to INFO",
        action="store_const",
        const=logging.INFO,
    )
    parser.add_argument(
        "-vv",
        "--very-verbose",
        dest="loglevel",
        help="set loglevel to DEBUG",
        action="store_const",
        const=logging.DEBUG,
    )
    parser.add_argument(
        "--abi-paths", type=str, nargs="+", help="search path to load ABIs", default=_env_list("ABI_PATHS")
    )
    parser.add_argument(
        "--template-paths",
        type=str,
        nargs="+",
        help="search path to load templates",
        default=_env_list("TEMPLATE_PATHS"),
    )
    parser.add_argument("--rpc-url", type=str, help="The RPC endpoint", default=os.environ.get("RPC_URL"))
    parser.add_argument("--chain-id", type=int, help="The ID of the chain", default=_env_int("CHAIN_ID"))
    parser.add_argument(
        "--chains-file",
        type=str,
        help="File like https://chainid.network/chains.json",
        default=os.environ.get("CHAINS_FILE"),
    )
    parser.add_argument(
        "--address-book",
        type=str,
        help="JSON file with mapping of addresses (name to address or address to name)",
        default=os.environ.get("ADDRESS_BOOK"),
    )
    parser.add_argument(
        "--bytes32-rainbow",
        type=str,
        help="JSON file with mapping of hashes (b32 to name or name to b32 or list of names)",
        default=os.environ.get("BYTES32_RAINBOW"),
    )
    parser.add_argument(
        "--template-rules",
        metavar="<template_rules>",
        type=str,
        help="Yaml file with the rules that map the events to templates",
        default=os.environ.get("TEMPLATE_RULES"),
    )
    parser.add_argument(
        "--discord-url",
        type=str,
        help="URL to send discord messages",
        default=os.environ.get("DISCORD_URL"),
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="sub-command to run")

    load_events = subparsers.add_parser("load_events")

    load_events.add_argument("paths", metavar="N", type=str, nargs="+", help="a list of strings")

    render_events = subparsers.add_parser("render_events")
    render_events.add_argument(
        "input",
        metavar="<alchemy-input-json|txhash>",
        type=str,
        help="Alchemy JSON file or TX Transaction",
    )

    flask_dev = subparsers.add_parser("flask_dev")
    flask_dev.add_argument("--port", type=int, help="Port to start flask dev server", default=8000)
    flask_dev.add_argument("--host", type=str, help="Host to start flask dev server", default=None)

    flask_gunicorn = subparsers.add_parser("flask_gunicorn")
    flask_gunicorn.add_argument(
        "--rollbar-token", type=str, help="Token to send errors to rollbar", default=os.environ.get("ROLLBAR_TOKEN")
    )
    flask_gunicorn.add_argument(
        "--rollbar-env", type=str, help="Name of the rollbar environment", default=os.environ.get("ROLLBAR_ENVIRONMENT")
    )
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout, format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def main(args):
    args = parse_args(args)
    setup_logging(args.loglevel)
    if args.command == "load_events":
        print(f"{load_events(args)} events found")
    elif args.command == "render_events":
        renv = setup_rendering_env(args)
        render_events(renv, args.input)
    elif args.command in ("flask_dev", "flask_gunicorn"):
        from . import flask_app

        renv = setup_rendering_env(args)
        # TODO: rollbar setup?
        flask_app.app.config["renv"] = renv
        flask_app.app.config["discord_url"] = args.discord_url
        flask_app.app.config["alchemy_keys"] = _env_alchemy_keys(os.environ)
        if args.command == "flask_dev":
            flask_app.app.run(port=args.port)
        else:
            return flask_app.app


def run():
    """Calls :func:`main` passing the CLI arguments extracted from :obj:`sys.argv`

    This function can be used as entry point to create console scripts with setuptools.
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    # ^  This is a guard statement that will prevent the following code from
    #    being executed in the case someone imports this file instead of
    #    executing it as a script.
    #    https://docs.python.org/3/library/__main__.html

    # After installing your project with pip, users can also run your Python
    # modules as scripts via the ``-m`` flag, as defined in PEP 338::
    #
    #     python -m eth_pretty_events.cli ...
    #
    run()
