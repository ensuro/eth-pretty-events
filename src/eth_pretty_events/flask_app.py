import os
from itertools import groupby

import requests
from flask import Flask, request

from .decode_events import decode_events_from_tx, decode_from_alchemy_input
from .event_filter import find_template
from .render import render
from .types import Hash

app = Flask("eth-pretty-events")


@app.route("/alchemy-webhook/", methods=["POST"])
def alchemy_webhook():
    # TODO: validate signature
    renv = app.config["renv"]
    discord_url = os.environ["DISCORD_WEBHOOK_URL"]  # TODO: get this from app.config
    payload = request.json

    events = groupby(
        sorted(
            filter(lambda x: x is not None, decode_from_alchemy_input(payload, renv.chain)),
            key=lambda x: (x.tx.hash, x.log_index),
        ),
        key=lambda x: x.tx.hash,
    )

    message_count = 0
    for _, tx_events in events:
        # TODO: encapsulate discord-specific behaviour
        message = {
            "embeds": [
                {
                    "description": render(renv.jinja_env, event, find_template(renv.template_rules, event)),
                }
                for event in tx_events
            ]
        }
        requests.post(discord_url, json=message)
        message_count += 1

    return {"status": "ok", "detail": f"Sent {message_count} messages"}


@app.route("/render/tx/<tx_hash>/", methods=["GET"])
def render_tx(tx_hash: str):
    hash = Hash(tx_hash)

    renv = app.config["renv"]

    events = decode_events_from_tx(hash, renv.w3, renv.chain)

    ret = []

    for event in events:
        if not event:
            continue
        template_name = find_template(renv.template_rules, event)
        if template_name is None:
            continue
        ret.append(render(renv.jinja_env, event, template_name))

    return ret


if __name__ == "__main__":
    raise RuntimeError("This isn't prepared to be called as a module")
