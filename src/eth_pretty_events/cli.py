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
import json
import logging
import sys
from typing import Optional

from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware.geth_poa import geth_poa_middleware

from eth_pretty_events import __version__, address_book, render
from eth_pretty_events.alchemy_utils import graphql_log_to_log_receipt
from eth_pretty_events.event_parser import EventDefinition
from eth_pretty_events.types import Address, Block, Chain, Hash, Tx

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


def _events_from_alchemy_input(alchemy_json: str, chain: Chain):
    alchemy_input = json.load(open(alchemy_json))
    alchemy_block = alchemy_input["event"]["data"]["block"]
    block = Block(
        chain=chain,
        number=alchemy_block["number"],
        hash=Hash(alchemy_block["hash"]),
        timestamp=alchemy_block["timestamp"],
    )
    for alchemy_log in alchemy_block["logs"]:
        log = graphql_log_to_log_receipt(alchemy_log, alchemy_block)
        yield EventDefinition.read_log(log, block=block)


def _events_from_tx(tx_hash: str, w3: Web3, chain: Chain):
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    block = Block(
        chain=chain,
        hash=Hash(receipt.blockHash),
        number=receipt.blockNumber,
        timestamp=w3.eth.get_block(receipt.blockNumber).timestamp,
    )
    tx = Tx(block=block, hash=Hash(receipt.transactionHash), index=receipt.transactionIndex)
    return (EventDefinition.read_log(log, block=block, tx=tx) for log in receipt.logs)


def _events_from_block(block_number: int, w3: Web3, chain: Chain):
    w3_block = w3.eth.get_block(block_number)
    block = Block(chain=chain, number=block_number, timestamp=w3_block["timestamp"], hash=Hash(w3_block["hash"]))
    for w3_tx in w3_block.transactions:
        receipt = w3.eth.get_transaction_receipt(w3_tx)
        tx = Tx(block=block, hash=Hash(receipt.transactionHash), index=receipt.transactionIndex)
        for log in receipt.logs:
            yield EventDefinition.read_log(log, tx=tx, block=block)


def render_events(args):
    """Renders the events found in a given input

    Returns:
      int: Number of events found
    """
    events_found = EventDefinition.load_all_events(args.abi_paths)
    w3 = _setup_web3(args)
    env_globals = _env_globals(args, w3)
    chain = env_globals["chain"]

    _setup_address_book(args, w3)

    env = render.init_environment(args.template_paths, env_globals)

    if args.input.endswith(".json"):
        events = _events_from_alchemy_input(args.input, chain)
    elif args.input.startswith("0x") and len(args.input) == 66:
        if w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a transaction hash
        events = _events_from_tx(args.input, w3, chain)
    elif args.input.isdigit():
        if w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a block number
        events = _events_from_block(int(args.input), w3, chain)
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
