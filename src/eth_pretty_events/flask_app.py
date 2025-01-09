import hashlib
import hmac
import json
import os
from functools import wraps
from typing import List

from flask import Flask, request

from .decode_events import decode_events_from_tx, decode_from_alchemy_input
from .outputs import OutputBase
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


def build_outputs(renv) -> List[OutputBase]:
    output_urls = renv.args.outputs or ["print://"]
    return [OutputBase.build_output(output_url, renv) for output_url in output_urls]


def send_to_outputs(outputs, decoded_tx_logs):
    ok_count = 0
    failed_count = 0

    for output in outputs:
        try:
            output.run_sync(decoded_tx_logs)
            ok_count += 1
        except Exception:
            app.logger.error(f"Failed to send logs to output {output}")
            failed_count += 1

    return ok_count, failed_count


@app.route("/alchemy-webhook/", methods=["POST"])
@check_alchemy_signature
def alchemy_webhook():
    renv = app.config["renv"]
    payload = request.json

    webhook_id = payload.get("webhookId")
    block_number = payload.get("event", {}).get("blockNumber")
    transactions = payload.get("event", {}).get("transactions", [])
    num_logs = sum(len(tx.get("logs", [])) for tx in transactions)

    app.logger.info(
        "Processing webhook_id: %s, block: %s, transactions: %s, logs: %s",
        webhook_id,
        block_number,
        len(transactions),
        num_logs,
    )
    if os.environ.get("ALCHEMY_VERBOSE_MODE", "False").lower() in ("true", "1"):
        app.logger.info("Alchemy webhook: %s", json.dumps(request.json))

    decoded_logs = decode_from_alchemy_input(payload, renv.chain)
    outputs = build_outputs(renv)
    ok_count, failed_count = send_to_outputs(outputs, decoded_logs)
    # TODO: do we want to fail if any of the messages fails? Probably not as it will cause a flood of repeated messages
    return {"status": "OK", "ok_count": ok_count, "failed_count": failed_count}


@app.route("/render/tx/<tx_hash>/", methods=["GET"])
def render_tx(tx_hash: str):
    hash = Hash(tx_hash)

    renv = app.config["renv"]

    decoded_logs = decode_events_from_tx(hash, renv.w3, renv.chain)
    outputs = build_outputs(renv)
    ok_count, failed_count = send_to_outputs(outputs, [decoded_logs])
    return {"status": "OK", "ok_count": ok_count, "failed_count": failed_count}


if __name__ == "__main__":
    raise RuntimeError("This isn't prepared to be called as a module")
