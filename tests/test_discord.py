import asyncio
import json
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
from jinja2 import Environment, FunctionLoader

from eth_pretty_events.discord import (
    DiscordOutput,
    build_and_send_messages,
    build_transaction_messages,
)
from eth_pretty_events.event_filter import read_template_rules
from eth_pretty_events.jinja2_ext import add_filters
from eth_pretty_events.types import Block, Chain, Event, Hash, Tx


@pytest.fixture
def dummy_queue():
    return asyncio.Queue()


@pytest.fixture
def dummy_renv():
    return MagicMock()


class TemplateLoader:
    def __init__(self):
        self.templates = {
            "ERC20-transfer.md.j2": (
                "Transfer {{ evt.args.value | amount }} "
                "from {{ evt.args.from  | address }} to {{ evt.args.to  | address }}"
            ),
            "policy-resolved.md.j2": "Policy {{ evt.args.policyId }} resolved for {{ evt.args.payout | amount }}",
        }

    def __call__(self, name):
        return self.templates.get(name)


@pytest.fixture
def template_loader():
    return TemplateLoader()


@pytest.fixture(scope="session")
def template_rules():
    return read_template_rules(
        {
            "rules": [
                {
                    "match": [
                        {"event": "Transfer"},
                        {"filter_type": "arg_exists", "arg_name": "value"},
                    ],
                    "template": "ERC20-transfer.md.j2",
                },
                {"match": [{"event": "PolicyResolved"}], "template": "policy-resolved.md.j2"},
            ]
        }
    )


@pytest.fixture
def sample_tx_and_events():
    tx = Tx(
        block=Block(
            hash=Hash("0x578e4e045d37a7485bfcb634e514f6dbdca62ea1e29e8180d15de940046858eb"),
            number=123456,
            timestamp=1635600000,
            chain=Chain(id=1, name="Ethereum Testnet"),
        ),
        hash=Hash("0x578e4e045d37a7485bfcb634e514f6dbdca62ea1e29e8180d15de940046858eb"),
        index=1,
    )

    with open("samples/alchemy-sample.json") as f:
        samples = json.load(f)

    tx_events = [
        Event(
            address=log["account"]["address"],
            args={
                "from": log["topics"][1],
                "to": log["topics"][2],
                "value": int(log["data"], 16),
            },
            tx=tx,
            name="Transfer",
            log_index=log["index"],
        )
        for log in samples["event"]["data"]["block"]["logs"]
    ]

    return tx, tx_events


def test_discord_output_missing_env_var(dummy_queue, dummy_renv):
    url = urlparse("discord://localhost")
    with pytest.raises(RuntimeError, match="Must define the Discord URL in DISCORD_URL env variable"):
        DiscordOutput(dummy_queue, url, dummy_renv)


def test_discord_output_with_env_var(dummy_queue, dummy_renv):
    with patch.dict("os.environ", {"DISCORD_URL": "https://discord.com/api/webhooks/test"}):
        url = urlparse("discord://localhost")
        output = DiscordOutput(dummy_queue, url, dummy_renv)
        assert output.discord_url == "https://discord.com/api/webhooks/test"


def test_build_transaction_messages_limits(dummy_renv, template_rules, template_loader, sample_tx_and_events):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    tx, tx_events = sample_tx_and_events

    messages = list(build_transaction_messages(dummy_renv, tx, tx_events))

    assert len(messages) >= 1
    assert all(len(message["embeds"]) <= 9 for message in messages)
    assert all(sum(len(json.dumps(embed)) for embed in message["embeds"]) <= 5000 for message in messages)


def test_build_and_send_messages(dummy_renv, template_rules, template_loader, sample_tx_and_events):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    tx, tx_events = sample_tx_and_events

    with patch("eth_pretty_events.discord.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)

        discord_url = "https://discord.com/api/webhooks/test"

        responses = build_and_send_messages(discord_url, dummy_renv, tx_events)

        assert mock_post.call_count == len(responses), f"Expected {len(responses)} calls, got {mock_post.call_count}"
