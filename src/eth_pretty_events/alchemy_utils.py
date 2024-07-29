"""Module with util functions to deal with Alchemy Webhooks"""

from eth_utils.address import to_checksum_address
from hexbytes import HexBytes
from web3.types import LogReceipt


def graphql_log_to_log_receipt(gql_log: dict, block: dict) -> LogReceipt:
    """Convert the data in the format of Alchemy webhooks into LogReceipt"""
    return {
        "transactionHash": HexBytes(gql_log["transaction"]["hash"]),
        "address": to_checksum_address(gql_log["account"]["address"]),
        "blockHash": HexBytes(block["hash"]),
        "blockNumber": block["number"],
        "data": gql_log["data"],
        "logIndex": gql_log["index"],
        "removed": False,
        "topics": [HexBytes(t) for t in gql_log["topics"]],
        "transactionIndex": gql_log["transaction"]["index"],
    }
