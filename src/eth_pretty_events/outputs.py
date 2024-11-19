import asyncio
import pprint
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import ParseResult, urlparse

from web3 import types as web3types

from .types import Event, Tx


@dataclass
class DecodedTxLogs:
    tx: Tx
    raw_logs: List[web3types.LogReceipt]
    decoded_logs: List[Optional[Event]]


class OutputBase(ABC):
    OUTPUT_REGISTRY = {}

    def __init__(self, queue: asyncio.Queue[DecodedTxLogs], *args, **kwargs):
        self.queue = queue

    async def run(self):
        while True:
            log = await self.queue.get()
            await self.send_to_output(log)
            self.queue.task_done()

    @abstractmethod
    async def send_to_output(self, log: DecodedTxLogs): ...

    @classmethod
    def register(cls, type: str):
        def decorator(subclass):
            if type in cls.OUTPUT_REGISTRY:
                raise ValueError(f"Duplicate output type {type}")
            cls.OUTPUT_REGISTRY[type] = subclass
            return subclass

        return decorator

    @classmethod
    def build_output(cls, queue: asyncio.Queue[DecodedTxLogs], output_url: str, renv):
        parsed_url: ParseResult = urlparse(output_url)
        if parsed_url.scheme not in cls.OUTPUT_REGISTRY:
            raise RuntimeError(f"Unsupported output type {parsed_url.scheme}")
        subclass = cls.OUTPUT_REGISTRY[parsed_url.scheme]
        return subclass(queue, parsed_url, renv=renv)


@OutputBase.register("dummy")
class DummyOutput(OutputBase):
    async def send_to_output(self, log: DecodedTxLogs):
        pprint.pprint(log)
