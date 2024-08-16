from itertools import groupby
from typing import Iterable

import requests

from .event_filter import find_template
from .render import render
from .types import Event


def build_transaction_message(renv, tx_hash, tx_events):
    embeds = []
    for event in tx_events:
        template = find_template(renv.template_rules, event)
        if template is None:
            continue
        embeds.append({"description": render(renv.jinja_env, event, template)})

    if embeds:
        # TODO: add main content with the tx hash and a link to explorer
        return {"embeds": embeds}

    return None


def build_and_send_messages(discord_url: str, renv, events: Iterable[Event]):
    events = groupby(
        sorted(
            events,
            key=lambda event: (
                event.tx.block.number,
                event.tx.index,
                event.log_index,
            ),  # TODO: move this to the dunder methods on types.py?
        ),
        key=lambda event: event.tx.hash,
    )

    responses = []
    for tx_hash, tx_events in events:
        message = build_transaction_message(renv, tx_hash, tx_events)
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
