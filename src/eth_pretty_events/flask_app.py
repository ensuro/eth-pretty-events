import hashlib
import hmac
from functools import wraps

from flask import Flask, request

from . import discord
from .decode_events import decode_events_from_tx, decode_from_alchemy_input
from .event_filter import find_template
from .render import render
from .types import Hash

app = Flask("eth-pretty-events")


def check_alchemy_signature(wrapped):
    @wraps(wrapped)
    def wrapper(*args, **kwargs):
        webhook_id = request.json.get("webhookId")
        if webhook_id is None:
            return {"error": "Bad request"}, 400

        signing_key = app.config["alchemy_keys"].get(webhook_id)
        if signing_key is None:
            app.logger.warning("Ignoring request %s for unknown webhook id %s", request.json.get("id"), webhook_id)
            return {}

        signature = request.headers.get("x-alchemy-signature", None)
        if signature is None:
            return {"error": "Unauthorized"}, 401

        raw_body = request.get_data()
        digest = hmac.new(bytes(signing_key, "utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, digest):
            return {"error": "Forbidden"}, 403

        return wrapped(*args, **kwargs)

    return wrapper


@app.route("/alchemy-webhook/", methods=["POST"])
@check_alchemy_signature
def alchemy_webhook():
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
