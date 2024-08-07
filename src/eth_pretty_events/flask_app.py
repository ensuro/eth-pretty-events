from flask import Flask

from .decode_events import decode_events_from_tx
from .event_filter import find_template
from .render import render
from .types import Hash

app = Flask("eth-pretty-events")


@app.route("/alchemy-webhook/<webhook_id>/", methods=["POST"])
def alchemy_webhook(webhook_id: str):
    # TODO: I'm not sure if it's better to include the webhook_id in the URL, or always use the same URL
    # and get the webhook_id from the json input.
    pass


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
