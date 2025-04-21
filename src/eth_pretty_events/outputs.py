import asyncio
import pprint
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import ParseResult, parse_qs, urlparse

from web3 import types as web3types

from .types import Event, Tx


@dataclass
class DecodedTxLogs:
    tx: Tx
    raw_logs: List[web3types.LogReceipt]
    decoded_logs: List[Optional[Event]]


class OutputBase(ABC):
    OUTPUT_REGISTRY = {}

    def __init__(self, url: ParseResult):
        query_params = parse_qs(url.query)
        tags = query_params.get("tags", [None])[0]
        self.tags: Optional[List[str]] = [tag.strip() for tag in tags.split(",")] if tags else None

    def run_sync(self, logs: Iterable[DecodedTxLogs]):
        for log in logs:
            self.send_to_output_sync(log)

    async def run(self, queue: asyncio.Queue[DecodedTxLogs]):
        while True:
            log = await queue.get()
            await self.send_to_output(log)
            queue.task_done()

    @abstractmethod
    def send_to_output_sync(self, log: DecodedTxLogs): ...

    async def send_to_output(self, log: DecodedTxLogs):
        return self.send_to_output_sync(log)

    @classmethod
    def register(cls, type: str):
        def decorator(subclass):
            if type in cls.OUTPUT_REGISTRY:
                raise ValueError(f"Duplicate output type {type}")
            cls.OUTPUT_REGISTRY[type] = subclass
            return subclass

        return decorator

    @classmethod
    def build_output(cls, output_url: str, renv):
        parsed_url: ParseResult = urlparse(output_url)
        if parsed_url.scheme not in cls.OUTPUT_REGISTRY:
            raise RuntimeError(f"Unsupported output type {parsed_url.scheme}")
        subclass = cls.OUTPUT_REGISTRY[parsed_url.scheme]
        return subclass(parsed_url, renv=renv)


@OutputBase.register("dummy")
class DummyOutput(OutputBase):
    def __init__(self, url: ParseResult, renv=None):
        super().__init__(url)

    def send_to_output_sync(self, log: DecodedTxLogs):
        pprint.pprint(log)
