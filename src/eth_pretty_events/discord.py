import asyncio
import json
import logging
import os
from itertools import groupby
from typing import Iterable
from urllib.parse import ParseResult, parse_qs

import aiohttp
import requests

from .event_filter import find_template
from .outputs import DecodedTxLogs, OutputBase
from .render import render
from .types import Event

_logger = logging.getLogger(__name__)


@OutputBase.register("discord")
class DiscordOutput(OutputBase):
    def __init__(self, queue: asyncio.Queue, url: ParseResult, renv):
        super().__init__(queue, url)
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

    async def run(self):
        async with aiohttp.ClientSession() as session:
            self.session = session
            await super().run()
        delattr(self, "session")

    async def send_to_output(self, log: DecodedTxLogs):
        messages = build_transaction_messages(self.renv, log.tx, log.decoded_logs)
        if messages is None:
            return

        for message in messages:
            async with self.session.post(self.discord_url, json=message) as response:
                if response.status > 204:
                    _logger.warning(f"Unexpected result {response.status}")
                    _logger.warning("Discord response body: %s", await response.text())


def build_transaction_messages(renv, tx, tx_events):
    current_batch = []
    current_batch_size = 0

    for event in tx_events:
        if event is None:
            continue
        template = find_template(renv.template_rules, event)
        if template is None:
            continue
        embed = {"description": render(renv.jinja_env, event, template)}
        embed_size = len(json.dumps(embed))

        if current_batch_size + embed_size > 5000 or len(current_batch) == 9:
            yield {"embeds": current_batch}
            current_batch = []
            current_batch_size = 0

        current_batch.append(embed)
        current_batch_size += embed_size

    if current_batch:
        yield {"embeds": current_batch}


def build_and_send_messages(discord_url: str, renv, events: Iterable[Event]):
    grouped_events = groupby(
        sorted(
            events,
            key=lambda event: (
                event.tx.block.number,
                event.tx.index,
                event.log_index,
            ),  # TODO: move this to the dunder methods on types.py?
        ),
        key=lambda event: event.tx,
    )

    responses = []
    for tx, tx_events in grouped_events:
        for message in build_transaction_messages(renv, tx, tx_events):
            if message is None:
                continue
            response = post(discord_url, message)
            responses.append(response)

    return responses


_session = None


def post(url, payload):
    global _session
    if not _session:
        _session = requests.Session()
    return _session.post(url, json=payload)
