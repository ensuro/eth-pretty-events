"""
This is a skeleton file that can serve as a starting point for a Python
console script. To run this script uncomment the following lines in the
``[options.entry_points]`` section in ``setup.cfg``::

    console_scripts =
         fibonacci = eth_pretty_events.skeleton:run

Then run ``pip install .`` (or ``pip install -e .`` for editable mode)
which will install the command ``fibonacci`` inside your current environment.

Besides console scripts, the header (i.e. until ``_logger``...) of this file can
also be used as template for Python modules.

Note:
    This file can be renamed depending on your needs or safely removed if not needed.

References:
    - https://setuptools.pypa.io/en/latest/userguide/entry_point.html
    - https://pip.pypa.io/en/stable/reference/pip_install
"""

import argparse
import itertools
import json
import logging
import sys

from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware.geth_poa import geth_poa_middleware

from eth_pretty_events import __version__, render
from eth_pretty_events.event_parser import EventDefinition

__author__ = "Guillermo M. Narvaja"
__copyright__ = "Guillermo M. Narvaja"
__license__ = "MIT"

_logger = logging.getLogger(__name__)


# ---- Python API ----
# The functions defined in this section can be imported by users in their
# Python scripts/interactive interpreter, e.g. via
# `from eth_pretty_events.skeleton import fib`,
# when using this Python module as a library.


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


def _setup_web3(args):
    w3 = Web3(Web3.HTTPProvider(args.rpc_url))
    assert w3.is_connected()
    try:
        w3.eth.get_block("latest")
    except ExtraDataLengthError:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3


def _env_globals(args):
    ret = {}
    if args.bytes32_rainbow:
        ret["b32_rainbow"] = json.load(open(args.bytes32_rainbow))
        # TODO: process hashes or invert the dict
    else:
        ret["b32_rainbow"] = {}
    if args.address_book:
        ret["address_book"] = json.load(open(args.address_book))
    else:
        ret["address_book"] = {}
    if args.chain_id:
        ret["chain_id"] = int(args.chain_id)
    elif args.rpc_url:
        w3 = _setup_web3(args)
        ret["chain_id"] = w3.eth.chain_id

    if args.chains_file:
        # https://chainid.network/chains.json like file
        chains = json.load(open(args.chains_file))
        ret["chains"] = dict((c["chainId"], c) for c in chains)

    return ret


def render_events(args):
    """Renders the events found in a given input

    Returns:
      int: Number of events found
    """
    events_found = EventDefinition.load_all_events(args.abi_paths)
    env_globals = _env_globals(args)
    env = render.init_environment(args.template_paths, env_globals)

    if args.input.endswith(".json"):
        alchemy_input = json.load(open(args.input))
        block = alchemy_input["event"]["data"]["block"]
        events = (EventDefinition.read_graphql_log(log, block) for log in block["logs"])
    elif args.input.startswith("0x") and len(args.input) == 66:
        # It's a transaction hash
        w3 = _setup_web3(args)
        receipt = w3.eth.get_transaction_receipt(args.input)
        events = (EventDefinition.read_log(log) for log in receipt.logs)
    elif args.input.isdigit():
        # It's a block number
        w3 = _setup_web3(args)
        block = w3.eth.get_block(int(args.input))
        events = itertools.chain.from_iterable(
            map(EventDefinition.read_log, w3.eth.get_transaction_receipt(tx).logs) for tx in block.transactions
        )
    else:
        print(f"Unknown input '{args.input}'", file=sys.stderr)
        sys.exit(1)

    for event in events:
        if not event:
            continue
        print(render.render(env, event, args.template_name))
        print("--------------------------")
    return len(events_found)


# ---- CLI ----
# The functions defined in this section are wrappers around the main Python
# API allowing them to be called directly from the terminal as a CLI
# executable/script.


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
    subparsers = parser.add_subparsers(dest="command", required=True, help="sub-command to run")

    load_events = subparsers.add_parser("load_events")

    load_events.add_argument("paths", metavar="N", type=str, nargs="+", help="a list of strings")

    render_events = subparsers.add_parser("render_events")
    render_events.add_argument("--abi-paths", type=str, nargs="+", help="search path to load ABIs")
    render_events.add_argument("--template-paths", type=str, nargs="+", help="search path to load templates")
    render_events.add_argument("--rpc-url", type=str, help="The RPC endpoint")
    render_events.add_argument("--chain-id", type=int, help="The ID of the chain")
    render_events.add_argument("--chains-file", type=str, help="File like https://chainid.network/chains.json")
    render_events.add_argument(
        "--address-book", type=str, help="JSON file with mapping of addresses (name to address or address to name)"
    )
    render_events.add_argument(
        "--bytes32-rainbow",
        type=str,
        help="JSON file with mapping of hashes (b32 to name or name to b32 or list of names)",
    )
    render_events.add_argument(
        "input",
        metavar="<alchemy-input-json|txhash>",
        type=str,
        help="Alchemy JSON file or TX Transaction",
    )
    render_events.add_argument(
        "template_name", metavar="<template_name>", type=str, help="The name of the template to render"
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
    """Wrapper allowing :func:`fib` to be called with string arguments in a CLI fashion

    Instead of returning the value from :func:`fib`, it prints the result to the
    ``stdout`` in a nicely formatted message.

    Args:
      args (List[str]): command line parameters as list of strings
          (for example  ``["--verbose", "42"]``).
    """
    args = parse_args(args)
    setup_logging(args.loglevel)
    if args.command == "load_events":
        print(f"{load_events(args)} events found")
    elif args.command == "render_events":
        render_events(args)
    _logger.debug(args)
    _logger.info("Script ends here")


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
    #     python -m eth_pretty_events.skeleton 42
    #
    run()
