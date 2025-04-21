import asyncio
import json
import logging
import os
import time
from typing import Iterable, List
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

        self.max_attempts = int(query_params.get("max_attempts", [3])[0])
        self.retry_time = float(query_params.get("retry_time", [5])[0])

    async def run(self, queue: asyncio.Queue[DecodedTxLogs]):
        async with aiohttp.ClientSession() as session:
            session = session
            while True:
                log = await queue.get()
                messages = build_transaction_messages(self.renv, log.tx, log.decoded_logs, log.raw_logs, self.tags)
                for message in messages:
                    for attempt in range(self.max_attempts):
                        async with session.post(self.discord_url, json=message) as response:
                            if 200 <= response.status < 300:
                                break  # Everything OK
                            if 400 <= response.status < 500:
                                _logger.error(
                                    f"Unexpected result {response.status}. "
                                    f"Discord response body: {await response.text()} "
                                    f"- Payload: {json.dumps(message)}"
                                )
                                break
                            _logger.warning(f"Unexpected result {response.status}")
                            if attempt < self.max_attempts - 1:
                                _logger.warning(f"Retrying in {self.retry_time} seconds...")
                                await asyncio.sleep(self.retry_time)
                            else:
                                _logger.error(
                                    f"Discord response body: {await response.text()} "
                                    f"- Payload: {json.dumps(message)}"
                                )
                queue.task_done()

    def run_sync(self, logs: Iterable[DecodedTxLogs]):
        session = requests.Session()
        for log in logs:
            messages = build_transaction_messages(self.renv, log.tx, log.decoded_logs, log.raw_logs, self.tags)
            for message in messages:
                for attempt in range(self.max_attempts):
                    response = session.post(self.discord_url, json=message)
                    if 200 <= response.status_code < 300:
                        break  # Everything OK
                    if 400 <= response.status_code < 500:
                        _logger.warning(
                            f"Unexpected result {response.status_code}. "
                            f"Discord response body: {response.content.decode('utf-8')} "
                            f"- Payload: {json.dumps(message)}"
                        )
                        break
                    _logger.warning(f"Unexpected result {response.status_code}")
                    if attempt < self.max_attempts - 1:
                        _logger.warning(f"Retrying in {self.retry_time} seconds...")
                        time.sleep(self.retry_time)
                    else:
                        _logger.error(
                            f"Discord response body: {response.content.decode('utf-8')} "
                            f"- Payload: {json.dumps(message)}"
                        )

    def send_to_output_sync(self, log: DecodedTxLogs):
        raise NotImplementedError()  # Shouldn't be called


def build_transaction_messages(renv, tx, tx_events, tx_raw_logs, tags: List[str] = None) -> Iterable[dict]:
    current_batch = []
    current_batch_size = 0
    if tags is not None:
        template_rules = [tr for tr in renv.template_rules if any(tag in tr.tags for tag in tags)]
    else:
        template_rules = renv.template_rules
    for event, raw_event in zip(tx_events, tx_raw_logs):
        if event is None:
            _logger.warning(
                f"Unrecognized event tried to be rendered in tx: {tx.hash}, "
                f"index: {raw_event.logIndex}, block: {tx.block.number}"
            )
            continue
        template = find_template(template_rules, event)
        if template is None:
            continue
        description = render(renv.jinja_env, event, [template, renv.args.on_error_template])
        original_description_length = len(description)
        if original_description_length > 4096:
            description = description[
                : 4096 - 100
            ]  # Truncate description so it does not exceed 4096 Discord limit description.
            _logger.info(
                f"Truncated description for event in tx: {tx.hash}, index: {event.log_index} "
                f"(original length: {original_description_length}, new length: {len(description)})"
            )
        embed = {"description": description}
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
