import argparse
import asyncio
import heapq
import itertools
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from operator import attrgetter
from typing import Any, Iterable, Iterator, List, Optional, Sequence, Tuple

import jinja2
import websockets
import yaml
from web3 import AsyncWeb3, Web3
from web3 import types as web3types
from web3._utils.encoding import Web3JsonEncoder
from web3.exceptions import ExtraDataLengthError
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.persistent import WebSocketProvider

from . import discord  # noqa - To load the discord output
from . import print_output  # noqa - To load the print output

try:
    from . import pubsub  # noqa - To load the pubsub output
except ImportError:
    pass
from . import __version__, address_book, decode_events, render
from .block_tree import BlockTree
from .event_filter import TemplateRule, read_template_rules
from .event_parser import EventDefinition
from .event_subscriptions import load_subscriptions
from .outputs import DecodedTxLogs, OutputBase
from .types import Address, Block, Chain, Hash, Tx

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
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
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


def _env_globals(args, w3_chain_id):
    ret = {}
    if args.bytes32_rainbow:
        ret["b32_rainbow"] = json.load(open(args.bytes32_rainbow))
        # TODO: process hashes or invert the dict
    else:
        ret["b32_rainbow"] = {}

    if args.chain_id:
        chain_id = ret["chain_id"] = int(args.chain_id)
        if w3_chain_id is not None and chain_id != w3_chain_id:
            raise argparse.ArgumentTypeError(
                f"--chain-id={chain_id} differs with the id of the RPC connection {w3_chain_id}"
            )
    elif w3_chain_id:
        chain_id = ret["chain_id"] = w3_chain_id
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
    env_globals = _env_globals(args, w3.eth.chain_id if w3 is not None else None)
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


async def _do_listen_events(
    w3: AsyncWeb3,
    block_tree: BlockTree,
    renv: RenderingEnv,
    subscriptions: list,
    raw_logs: asyncio.Queue[Tuple[Block, List[web3types.LogReceipt]]],
):
    block_headers_sub_id = await w3.eth.subscribe("newHeads")
    _logger.info(f"Block Headers Subscription: {block_headers_sub_id}")
    last_fork_number = None

    blocks_seen = 0

    log_subscriptions = {}
    for name, addresses, topics in subscriptions:
        log_subscriptions[name] = await w3.eth.subscribe(
            "logs",
            {
                "address": addresses,
                "topics": topics,
            },
        )
        _logger.info(f"Subscription for {name}: {log_subscriptions[name]}")

    waitlist_logs: dict[Block, List] = defaultdict(list)
    timestamp_cache: dict[Hash, int] = {}  # TODO: add some cleanup

    async for payload in w3.socket.process_subscriptions():
        if payload["subscription"] == block_headers_sub_id:
            blocks_seen += 1

            # Adds the block to the tree
            raw_block = payload["result"]
            block = Block(Hash(raw_block["hash"]), raw_block["timestamp"], raw_block["number"], renv.chain)
            timestamp_cache[block.hash] = block.timestamp
            parent_hash = Hash(raw_block["parentHash"])
            fork_number = block_tree.add_block(block.number, parent_hash, block.hash)
            if fork_number != last_fork_number:
                _logger.info(f"New fork found {block.number}: {parent_hash} => {block.hash}")
                last_fork_number = fork_number

            # Block tree cleanup, needed to release memory and to drop forked logs
            if blocks_seen % renv.args.block_tree_cleanup == 0:
                block_tree.clean(renv.args.block_tree_cleanup)

            # Pushes to the queue the logs that have enough confirmations
            for block in sorted(waitlist_logs.keys(), key=lambda x: x.number):
                confirmations = block_tree.confirmations(block.number, block.hash)
                if confirmations >= 0 and confirmations < renv.args.n_confirmations:
                    continue  # TODO: check if break would be better
                payloads = waitlist_logs.pop(block)
                if confirmations == -1:
                    # Drop logs, they were part of a deleted fork
                    _logger.info("Droping logs in non confirmed fork {block_number}: {block_hash}")
                    for pl in payloads:
                        print(json.dumps(pl, cls=Web3JsonEncoder, indent=2))
                else:  # confirmations >= renv.args.n_confirmations:
                    if block.timestamp is None:
                        block.timestamp = timestamp_cache[block.hash]
                    await raw_logs.put((block, [pl["result"] for pl in payloads]))
        else:
            raw_log: web3types.LogReceipt = payload["result"]
            block_hash = Hash(raw_log["blockHash"])
            timestamp = timestamp_cache.get(block_hash, None)
            block = Block(block_hash, timestamp, raw_log["blockNumber"], renv.chain)
            waitlist_logs[block].append(payload)

    assert w3.is_connected()


async def parse_raw_events(
    renv: RenderingEnv, raw_logs: asyncio.Queue, processed_logs: List[asyncio.Queue[DecodedTxLogs]]
):
    """Processes the raw logs, enrichs them (decoding) and groups by TX"""
    while True:
        block: Block
        logs: List[web3types.LogReceipt]
        block, logs = await raw_logs.get()

        for tx_hash, tx_logs in itertools.groupby(logs, key=lambda x: x["transactionHash"]):
            tx_logs = list(tx_logs)
            tx = Tx(Hash(tx_hash), tx_logs[0]["transactionIndex"], block)
            decoded_events = list(decode_events.decode_events_from_raw_logs(block, tx, tx_logs))
            decoded_log = DecodedTxLogs(tx, tx_logs, decoded_events)
            for queue in processed_logs:
                await queue.put(decoded_log)
        raw_logs.task_done()


async def _websocket_loop(ws_url, do_stuff_fn):
    async for w3 in AsyncWeb3(WebSocketProvider(ws_url)):
        try:
            try:
                await w3.eth.get_block("latest")
            except ExtraDataLengthError:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            await do_stuff_fn(w3)
        except websockets.ConnectionClosed:
            try:
                await w3.subscription_manager.unsubscribe_all()
            except Exception as err:
                _logger.warning(f"Error unsubscribing: {err}")
            try:
                await w3.provider.disconnect()
            except Exception as err:
                _logger.warning(f"Error disconnecting: {err}")
            _logger.warning("WebSocket connection closed - Reconnecting")
            continue


def build_outputs(renv: RenderingEnv) -> List[OutputBase]:
    output_urls = renv.args.outputs or ["print://"]
    return [OutputBase.build_output(output_url, renv) for output_url in output_urls]


def setup_outputs(renv: RenderingEnv) -> Tuple[List[asyncio.Queue], List[asyncio.Task]]:
    outputs = build_outputs(renv)

    output_queues = []
    workers = []

    for output in outputs:
        output_queue: asyncio.Queue[DecodedTxLogs] = asyncio.Queue()
        output_queues.append(output_queue)
        workers.append(output.run(output_queue))

    return output_queues, workers


async def listen_events(args):
    if args.rpc_url is None:
        raise argparse.ArgumentTypeError("Missing --rpc-url argument")
    if args.rpc_url.startswith("https://"):
        ws_url = args.rpc_url.replace("https://", "wss://")
    else:
        ws_url = args.rpc_url

    renv = None
    block_tree = BlockTree()
    if not args.subscriptions:
        raise argparse.ArgumentTypeError("Missing --subscriptions argument")

    renv = setup_rendering_env(args)

    # Load Subscription list
    subscriptions_file = yaml.load(open(args.subscriptions), yaml.SafeLoader)
    ab = address_book.get_default()
    subscriptions = load_subscriptions(subscriptions_file.get("subscriptions", subscriptions_file.get("hooks", {})), ab)
    subscriptions = list(subscriptions)

    raw_logs = asyncio.Queue()
    output_queues, output_workers = setup_outputs(renv)

    parse_worker = parse_raw_events(renv, raw_logs, output_queues)
    listen_worker = _websocket_loop(ws_url, lambda w3: _do_listen_events(w3, block_tree, renv, subscriptions, raw_logs))
    await asyncio.gather(listen_worker, parse_worker, *output_workers)


def _block_to_int(w3: Web3, block: str) -> int:
    if block.isdigit():
        return int(block)
    if block.startswith("0x"):
        return int(block, 16)
    if block not in ["earliest", "latest", "finalized", "pending"]:
        raise argparse.ArgumentTypeError(f"Invalid block: '{block}'")
    return w3.eth.get_block(block).number


def merge_decoded_logs(same_tx_group: Iterable[DecodedTxLogs]) -> DecodedTxLogs:
    tx_logs_list = list(same_tx_group)
    if not tx_logs_list:
        raise ValueError("merge_decoded_logs() received an empty group")

    base = tx_logs_list[0]
    by_log_index: dict[int, tuple[object, object]] = {}

    for tx_logs in tx_logs_list:
        if len(tx_logs.raw_logs) != len(tx_logs.decoded_logs):
            raise ValueError("raw_logs and decoded_logs must have the same length")
        for raw, dec in zip(tx_logs.raw_logs, tx_logs.decoded_logs):
            idx = raw["logIndex"]
            by_log_index.setdefault(idx, (raw, dec))

    ordered = [by_log_index[i] for i in sorted(by_log_index)]
    if ordered:
        raw, dec = zip(*ordered)
        return DecodedTxLogs(tx=base.tx, raw_logs=list(raw), decoded_logs=list(dec))
    return DecodedTxLogs(tx=base.tx, raw_logs=[], decoded_logs=[])


def _consolidate_logs(decoded_logs_for_sub: Iterable[Iterable[DecodedTxLogs]]) -> Iterator[DecodedTxLogs]:
    """
    Takes a list of generators of DecodedTxLogs and consolidates them in a new generator of DecodedTxLogs
    that is ordered by block and transaction index and that has the found logs merged.
    """
    key_fn = attrgetter("tx.block.number", "tx.index")
    merged = heapq.merge(*decoded_logs_for_sub, key=key_fn)
    for _, tx_group in itertools.groupby(merged, key=key_fn):
        yield merge_decoded_logs(tx_group)


def render_events(renv: RenderingEnv, input: str):
    """Renders the events found in a given input

    Returns:
      int: Number of events found
    """
    outputs = build_outputs(renv)

    if renv.args.subscriptions_resume_file:
        resume = ResumeFile(renv.args.subscriptions_resume_file)
    else:
        resume = None

    if input.endswith(".json"):
        decoded_tx_logs = decode_events.decode_from_alchemy_input(json.load(open(input)), renv.chain)
    elif input.endswith(".yaml"):
        # Load Subscription list
        subscriptions_file = yaml.load(open(input), yaml.SafeLoader)
        ab = address_book.get_default()
        subscriptions = load_subscriptions(
            subscriptions_file.get("subscriptions", subscriptions_file.get("hooks", {})), ab
        )
        block_from = _block_to_int(renv.w3, renv.args.subscriptions_block_from)
        if resume is not None:
            block_from = resume.get(block_from)
        decoded_tx_logs = _consolidate_logs(
            (
                decode_events.decode_events_from_subscription(
                    sub,
                    renv.w3,
                    renv.chain,
                    block_from,
                    _block_to_int(renv.w3, renv.args.subscriptions_block_to),
                )
                for sub in subscriptions
            )
        )
    elif input.startswith("0x") and len(input) == 66:
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a transaction hash
        decoded_tx_logs = [decode_events.decode_events_from_tx(input, renv.w3, renv.chain)]
    elif input.isdigit():
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        # It's a block number
        decoded_tx_logs = decode_events.decode_events_from_block(int(input), renv.w3, renv.chain)
    elif input.replace("-", "").isdigit():
        # It's a block range
        if renv.w3 is None:
            raise argparse.ArgumentTypeError("Missing --rpc-url parameter")
        block_from, block_to = input.split("-")
        decoded_tx_logs = []
        block_from = _block_to_int(renv.w3, block_from)
        block_to = _block_to_int(renv.w3, block_to)
        if resume is not None:
            block_from = resume.get(block_from)
        for block_number in range(block_from, block_to + 1):
            decoded_tx_logs.extend(decode_events.decode_events_from_block(block_number, renv.w3, renv.chain))
    else:
        raise argparse.ArgumentTypeError(f"Unknown input '{input}'")

    for output in outputs:
        if resume is None:
            output.run_sync(decoded_tx_logs)
        else:
            output.run_sync(resume.wrap(decoded_tx_logs))


class ResumeFile:
    def __init__(self, filename: str):
        self.filename = filename

    def get(self, fallback: int) -> int:
        if not os.path.exists(self.filename):
            return fallback
        with open(self.filename, "r") as f:
            return int(f.read().strip())

    def set(self, block_number: int):
        with open(self.filename, "w") as f:
            f.write(f"{block_number + 1}\n")

    def wrap(self, logs: Iterable[DecodedTxLogs]) -> Iterator[DecodedTxLogs]:
        last_block = None
        for log in logs:
            yield log
            if log.tx.block.number != last_block:
                self.set(log.tx.block.number)
            last_block = log.tx.block.number


# ---- CLI ----
# The functions defined in this section are wrappers around the main Python
# API allowing them to be called directly from the terminal as a CLI
# executable/script.


def _env_list(env_var) -> Optional[Sequence[str]]:
    value = os.environ.get(env_var)
    if value is not None:
        return value.split()
    return None


def _env_int(env_var, default=None) -> Optional[int]:
    value = os.environ.get(env_var)
    if value is not None:
        return int(value)
    return default


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

    parser.add_argument(
        "--on-error-template",
        type=str,
        help="URL to send discord messages",
        default=os.environ.get("ON_ERROR_TEMPLATE"),
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="sub-command to run")

    load_events = subparsers.add_parser("load_events")

    load_events.add_argument("paths", metavar="N", type=str, nargs="+", help="a list of strings")

    render_events = subparsers.add_parser("render_events")
    render_events.add_argument(
        "input",
        metavar="<alchemy-input-json|txhash|subscription_yaml|block|block_range>",
        type=str,
        help="Alchemy JSON file or TX Transaction",
    )

    render_events.add_argument(
        "outputs",
        type=str,
        nargs="*",
        help="A list of strings with the different outputs where the logs will be sent",
    )
    render_events.add_argument(
        "--subscriptions-block-from",
        type=str,
        help="Block range start (when doing eth_getLogs filter)",
        default="earliest",
    )
    render_events.add_argument(
        "--subscriptions-block-to", type=str, help="Block range end (when doing eth_getLogs filter)", default="latest"
    )
    render_events.add_argument(
        "--subscriptions-block-limit",
        type=int,
        help="Block batch size (when doing eth_getLogs filter)",
        default=_env_int("GET_LOGS_BLOCK_LIMIT", 500),
    )
    render_events.add_argument(
        "--subscriptions-resume-file",
        type=str,
        help="File with block to resume from",
        default=None,
    )

    flask_dev = subparsers.add_parser("flask_dev")
    flask_dev.add_argument("--port", type=int, help="Port to start flask dev server", default=8000)
    flask_dev.add_argument("--host", type=str, help="Host to start flask dev server", default=None)

    flask_dev.add_argument(
        "outputs",
        type=str,
        nargs="*",
        help="A list of strings with the different outputs where the logs will be sent",
    )

    flask_gunicorn = subparsers.add_parser("flask_gunicorn")
    flask_gunicorn.add_argument(
        "--rollbar-token", type=str, help="Token to send errors to rollbar", default=os.environ.get("ROLLBAR_TOKEN")
    )
    flask_gunicorn.add_argument(
        "--rollbar-env", type=str, help="Name of the rollbar environment", default=os.environ.get("ROLLBAR_ENVIRONMENT")
    )

    flask_gunicorn.add_argument(
        "outputs",
        type=str,
        nargs="*",
        help="A list of strings with the different outputs where the logs will be sent",
    )

    listen_events = subparsers.add_parser("listen_events")
    listen_events.add_argument(
        "--n-confirmations",
        type=int,
        help="Number of confirmations required to consider a block finalized",
        default=_env_int("N_CONFIRMATIONS", 32),
    )

    listen_events.add_argument(
        "--block-tree-cleanup",
        type=int,
        help="Number of blocks to store in the block tree",
        default=_env_int("BLOCK_TREE_CLEANUP", 64),
    )

    listen_events.add_argument(
        "--subscriptions",
        type=str,
        help="Yaml file with the address and topics to subscribe to",
        default=os.environ.get("SUBSCRIPTIONS"),
    )
    listen_events.add_argument(
        "outputs",
        type=str,
        nargs="+",
        help="A list of strings with the different outputs where the logs will be sent",
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
    elif args.command == "listen_events":
        asyncio.run(listen_events(args))
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
