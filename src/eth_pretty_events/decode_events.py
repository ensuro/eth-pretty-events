import itertools
from typing import Iterable, List, Optional, Sequence

from web3 import Web3
from web3 import types as web3types

from .alchemy_utils import graphql_log_to_log_receipt
from .event_parser import EventDefinition
from .outputs import DecodedTxLogs
from .types import Block, Chain, Event, Hash, Tx


def decode_from_alchemy_input(alchemy_input: dict, chain: Chain) -> Iterable[DecodedTxLogs]:
    alchemy_block = alchemy_input["event"]["data"]["block"]
    block = Block(
        chain=chain,
        number=alchemy_block["number"],
        hash=Hash(alchemy_block["hash"]),
        timestamp=alchemy_block["timestamp"],
    )

    for (tx_hash, tx_index), alchemy_logs in itertools.groupby(
        alchemy_block["logs"], key=lambda log: (log["transaction"]["hash"], log["transaction"]["index"])
    ):
        tx = Tx(
            block=block,
            hash=Hash(tx_hash),
            index=tx_index,
        )
        raw_logs = [graphql_log_to_log_receipt(alchemy_log, alchemy_block) for alchemy_log in alchemy_logs]
        decoded_logs = decode_events_from_raw_logs(block, tx, raw_logs)

        yield DecodedTxLogs(tx=tx, raw_logs=raw_logs, decoded_logs=decoded_logs)


def decode_events_from_tx(tx_hash: str, w3: Web3, chain: Chain) -> DecodedTxLogs:
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    block = Block(
        chain=chain,
        hash=Hash(receipt.blockHash),
        number=receipt.blockNumber,
        timestamp=w3.eth.get_block(receipt.blockNumber).timestamp,
    )
    tx = Tx(block=block, hash=Hash(receipt.transactionHash), index=receipt.transactionIndex)
    return DecodedTxLogs(
        tx=tx, raw_logs=receipt.logs, decoded_logs=decode_events_from_raw_logs(block, tx, receipt.logs)
    )


def decode_events_from_raw_logs(block: Block, tx: Tx, logs: Sequence[web3types.LogReceipt]) -> List[Optional[Event]]:
    return [EventDefinition.read_log(log, block=block, tx=tx) for log in logs]


def decode_events_from_block(block_number: int, w3: Web3, chain: Chain) -> Iterable[DecodedTxLogs]:
    w3_block = w3.eth.get_block(block_number)
    block = Block(chain=chain, number=block_number, timestamp=w3_block["timestamp"], hash=Hash(w3_block["hash"]))

    for w3_tx in w3_block.transactions:
        tx_hash = Hash(w3_tx)
        receipt = w3.eth.get_transaction_receipt(w3_tx)
        tx = Tx(block=block, hash=tx_hash, index=receipt.transactionIndex)
        yield DecodedTxLogs(
            tx=tx, raw_logs=receipt.logs, decoded_logs=decode_events_from_raw_logs(block, tx, receipt.logs)
        )
