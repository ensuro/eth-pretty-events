import asyncio
import json
import logging
import os
from typing import Iterable
from urllib.parse import ParseResult, parse_qs

import aiohttp
import requests

from .event_filter import find_template
from .outputs import DecodedTxLogs, OutputBase
from .render import render

_logger = logging.getLogger(__name__)


@OutputBase.register("discord")
class DiscordOutput(OutputBase):
    def __init__(self, url: ParseResult, renv):
        super().__init__(url)
        # Read the discord_url from an environment variable in the hostname
        query_params = parse_qs(url.query)
        if "from_env" in query_params:
            env_var = query_params["from_env"][0]
        else:
            env_var = "DISCORD_URL"
        discord_url = os.environ.get(env_var)
        if discord_url is None:
            raise RuntimeError(f"Must define the Discord URL in {env_var} env variable")
        self.discord_url = discord_url
        self.renv = renv

    async def run(self, queue: asyncio.Queue[DecodedTxLogs]):
        async with aiohttp.ClientSession() as session:
            session = session
            while True:
                log = await queue.get()
                messages = build_transaction_messages(self.renv, log.tx, log.decoded_logs, log.raw_logs)
                for message in messages:
                    async with session.post(self.discord_url, json=message) as response:
                        if response.status > 204:
                            _logger.warning(f"Unexpected result {response.status}")
                            _logger.warning("Discord response body: %s", await response.text())
                queue.task_done()

    def run_sync(self, logs: Iterable[DecodedTxLogs]):
        session = requests.Session()
        for log in logs:
            messages = build_transaction_messages(self.renv, log.tx, log.decoded_logs, log.raw_logs)
            for message in messages:
                response = session.post(self.discord_url, json=message)
                if response.status_code > 204:
                    _logger.warning(f"Unexpected result {response.status_code}")
                    _logger.warning("Discord response body: %s", response.content.decode("utf-8"))

    def send_to_output_sync(self, log: DecodedTxLogs):
        raise NotImplementedError()  # Shouldn't be called


def build_transaction_messages(renv, tx, tx_events, tx_raw_logs) -> Iterable[dict]:
    current_batch = []
    current_batch_size = 0
    for event, raw_event in zip(tx_events, tx_raw_logs):
        if event is None:
            _logger.warning(
                f"Unrecognized event tried to be rendered in tx: {tx.hash}, "
                f"index: {raw_event.logIndex}, block: {tx.block.number}"
            )
            continue
        template = find_template(renv.template_rules, event)
        if template is None:
            continue
        embed = {"description": render(renv.jinja_env, event, [template, renv.args.on_error_template])}
        embed_size = len(json.dumps(embed))

        if current_batch_size + embed_size > 5000 or len(current_batch) == 9:
            yield {"embeds": current_batch}
            current_batch = []
            current_batch_size = 0

        current_batch.append(embed)
        current_batch_size += embed_size

    if current_batch:
        yield {"embeds": current_batch}


_session = None


def post(url, payload):
    global _session
    if not _session:
        _session = requests.Session()
    return _session.post(url, json=payload)
