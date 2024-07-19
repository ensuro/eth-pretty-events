import json
import os
from dataclasses import dataclass

from eth_utils import add_0x_prefix, event_abi_to_log_topic, to_checksum_address
from hexbytes import HexBytes
from web3 import Web3
from web3._utils.events import get_event_data
from web3.datastructures import AttributeDict
from web3.exceptions import LogTopicError
from web3.types import ABIEvent, EventData, LogReceipt


class EventDataRich(EventData):
    """EventData that also has the ABI and perhaps some extra methods"""

    abi: ABIEvent


@dataclass(frozen=True, kw_only=True)
class EventDefinition:
    topic: str
    abis: list

    name: str

    _registry = {}

    def __post_init__(self):
        if self.topic in self._registry and self._registry[self.topic] != self:
            self._registry[self.topic] = self._merge_events(self.topic, self._registry[self.topic], self)
        else:
            self._registry[self.topic] = self

    @classmethod
    def reset_registry(cls):
        cls._registry = {}

    @classmethod
    def _merge_events(cls, topic, prev, new):
        """
        The 'indexed' isn't part of the topic, so we might have different ABIs that are applicable to the
        same event.

        For example ERC-20 vs ERC-721 Transfer signatures are:
        event Transfer(address indexed _from, address indexed _to, uint256 _value)
        event Transfer(address indexed _from, address indexed _to, uint256 indexed _tokenId);

        So, in some cases one signature will work and the other won't. We store both abis and when parsing
        it tries all.
        """
        new_abis = [abi for abi in new.abis if abi not in prev.abis]
        if not new_abis:
            return prev
        prev.abis.extend(new_abis)
        return prev

    @classmethod
    def graphql_log_to_log_receipt(cls, gql_log: dict, block: dict) -> LogReceipt:
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

    @classmethod
    def dict_log_to_log_receipt(cls, log: dict) -> LogReceipt:
        return {
            "transactionHash": HexBytes(log["transactionHash"]),
            "address": to_checksum_address(log["address"]),
            "blockHash": HexBytes(log["blockHash"]),
            "blockNumber": int(log["blockNumber"], 16),
            "data": log["data"],
            "logIndex": int(log["logIndex"], 16),
            "removed": log["removed"],
            "topics": [HexBytes(t) for t in log["topics"]],
            "transactionIndex": int(log["transactionIndex"], 16),
        }

    def get_event_data(self, log_entry: LogReceipt) -> EventDataRich:
        for i, abi in enumerate(self.abis):
            try:
                ret = get_event_data(self.abi_codec(), abi, log_entry)
            except LogTopicError:
                if i == len(self.abis) - 1:
                    raise
            else:
                # Adds "abi" attribute but keeps the same AttributeDict interface
                # that allows getting the values as dict keys and attributes
                return AttributeDict.recursive({"abi": abi} | dict(ret))

    @classmethod
    def read_graphql_log(cls, gql_log: dict, block: dict) -> EventDataRich:
        log_entry = cls.graphql_log_to_log_receipt(gql_log, block)
        return cls.read_log(log_entry)

    @classmethod
    def read_dict_log(cls, log: dict) -> EventData:
        log_entry = cls.dict_log_to_log_receipt(log)
        return cls.read_log(log_entry)

    @classmethod
    def read_log(cls, log_entry: LogReceipt) -> EventDataRich:
        if not log_entry["topics"]:
            return None  # Not an event
        topic = log_entry["topics"][0].hex()
        if topic not in cls._registry:
            return None
        event = cls._registry[topic]
        return event.get_event_data(log_entry)

    @classmethod
    def abi_codec(cls):
        return Web3().codec

    @classmethod
    def from_abi(cls, abi):
        topic = add_0x_prefix(event_abi_to_log_topic(abi).hex())
        return cls(topic=topic, abis=[abi], name=abi["name"])

    @classmethod
    def load_events(cls, contract_abi):
        return [cls.from_abi(evt) for evt in filter(lambda item: item["type"] == "event", contract_abi)]

    @classmethod
    def load_all_events(cls, lookup_paths):
        ret = []
        for contracts_path in lookup_paths:
            for sub_path, _, files in os.walk(contracts_path):
                for filename in filter(lambda f: f.endswith(".json"), files):
                    with open(os.path.join(sub_path, filename)) as f:
                        contract_abi = json.load(f)
                    ret.extend(cls.load_events(contract_abi["abi"]))
        return ret
