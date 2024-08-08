from itertools import groupby
from typing import Iterable

import requests

from .decode_events import decode_from_alchemy_input
from .event_filter import find_template
from .render import render
from .types import Event


def build_transaction_message(renv, tx_hash, tx_events):
    return {
        "embeds": [
            {
                "description": render(renv.jinja_env, event, find_template(renv.template_rules, event)),
            }
            for event in tx_events
        ]
    }


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

    messages = [build_transaction_message(renv, tx_hash, tx_events) for tx_hash, tx_events in events]

    responses = []
    for message in messages:
        response = requests.post(discord_url, json=message)
        responses.append(response)

    return responses
