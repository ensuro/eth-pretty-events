import json
import logging
import os
from dataclasses import dataclass
from typing import ClassVar, Dict, Optional, Sequence, Type

from eth_utils.abi import event_abi_to_log_topic
from eth_utils.address import to_checksum_address
from eth_utils.hexadecimal import add_0x_prefix
from hexbytes import HexBytes
from web3 import Web3
from web3._utils.events import get_event_data
from web3.exceptions import LogTopicError
from web3.types import LogReceipt

from .types import ArgsTuple, Block, Event, Tx, make_abi_namedtuple

logger = logging.getLogger(__name__)


def event_str(event: LogReceipt):
    return f"Event 0x{event.transactionHash.hex()}-{event.logIndex}"


@dataclass(frozen=True, kw_only=True)
class EventDefinition:
    topic: str
    abis: list
    args_types: Sequence[Type[ArgsTuple]]

    name: str

    _registry: ClassVar[Dict[str, "EventDefinition"]] = {}

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
        new_abis = [(abi, new.args_types[i]) for i, abi in enumerate(new.abis) if abi not in prev.abis]
        if not new_abis:
            return prev
        prev.abis.extend([abi for (abi, _) in new_abis])
        prev.args_types.extend([arg_type for (_, arg_type) in new_abis])
        return prev

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

    def get_event_data(self, log_entry: LogReceipt, block: Block, tx: Optional[Tx] = None) -> Optional[Event]:
        for i, abi in enumerate(self.abis):
            try:
                ret = get_event_data(self.abi_codec(), abi, log_entry)
            except LogTopicError:
                if i == len(self.abis) - 1:
                    logger.exception("Failed to decode event in log entry: %s", event_str(log_entry))
                    raise
            else:
                return Event.from_event_data(ret, self.args_types[i], tx=tx, block=block)

    @classmethod
    def read_log(cls, log_entry: LogReceipt, block: Block, tx: Optional[Tx] = None) -> Optional[Event]:
        if not log_entry["topics"]:
            return None  # Not an event
        topic = log_entry["topics"][0].to_0x_hex()
        if topic not in cls._registry:
            return None
        event = cls._registry[topic]
        try:
            return event.get_event_data(log_entry, block, tx)
        except RuntimeError as e:
            logger.exception("Failed to decode log for topic %s in log entry: %s, Error: %s", topic, log_entry, e)
            return None

    @classmethod
    def abi_codec(cls):
        return Web3().codec

    @classmethod
    def get_by_topic(cls, topic: str) -> "EventDefinition":
        return cls._registry[topic]

    @classmethod
    def from_abi(cls, abi):
        topic = add_0x_prefix(event_abi_to_log_topic(abi).hex())
        return cls(
            topic=topic, abis=[abi], name=abi["name"], args_types=[make_abi_namedtuple(abi["name"], abi["inputs"])]
        )

    @classmethod
    def load_events(cls, contract_abi):
        ret = []
        for evt in filter(lambda item: item["type"] == "event", contract_abi):
            try:
                ret.append(cls.from_abi(evt))
            except Exception as e:
                logger.exception("Failed to load event %s: %s", evt["name"], e)
        return ret

    @classmethod
    def load_all_events(cls, lookup_paths):
        ret = []
        for contracts_path in lookup_paths:
            for sub_path, _, files in os.walk(contracts_path):
                for filename in filter(lambda f: f.endswith(".json"), files):
                    with open(os.path.join(sub_path, filename)) as f:
                        contract_abi = json.load(f)
                    if "abi" not in contract_abi:
                        # Not all json files will be contract ABIs
                        continue
                    try:
                        ret.extend(cls.load_events(contract_abi["abi"]))
                    except Exception as e:
                        logger.exception("Failed to load events from %s: %s", filename, e)
        return ret
