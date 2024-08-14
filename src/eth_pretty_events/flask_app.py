from flask import Flask, request

from . import discord
from .decode_events import decode_events_from_tx, decode_from_alchemy_input
from .event_filter import find_template
from .render import render
from .types import Hash

app = Flask("eth-pretty-events")


@app.route("/alchemy-webhook/", methods=["POST"])
def alchemy_webhook():
    # TODO: validate signature
    discord_url = app.config["discord_url"]
    renv = app.config["renv"]
    payload = request.json

    responses = discord.build_and_send_messages(discord_url, renv, decode_from_alchemy_input(payload, renv.chain))

    ok_messages = sum(1 for response in responses if response.status_code == 200)
    failed_messages = len(responses) - ok_messages
    status_description = "ok" if failed_messages == 0 else "error"

    # TODO: do we want to fail if any of the messages fails? Probably not as it will cause a flood of repeated messages
    return {"status": status_description, "ok_count": ok_messages, "failed_count": failed_messages}


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
