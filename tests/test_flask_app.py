import json
import os
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pytest
from jinja2 import Environment, FunctionLoader
from web3.datastructures import ReadableAttributeDict

from eth_pretty_events import jinja2_ext
from eth_pretty_events.address_book import AddrToNameAddressBook
from eth_pretty_events.address_book import setup_default as setup_addr_book
from eth_pretty_events.cli import RenderingEnv
from eth_pretty_events.event_filter import read_template_rules
from eth_pretty_events.event_parser import EventDefinition
from eth_pretty_events.flask_app import app

from . import factories

ALCHEMY_SAMPLE_SIGNATURE = "f8ac2edf5261684722c7e1af055be74d95583b52b53fc5f86590928a750a79aa"


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
                        {
                            "or": [
                                {"filter_type": "known_address_arg", "arg_name": "to", "arg_value": True},
                                {"filter_type": "known_address_arg", "arg_name": "from", "arg_value": True},
                            ]
                        },
                    ],
                    "template": "ERC20-transfer.md.j2",
                },
                {"match": [{"event": "PolicyResolved"}], "template": "policy-resolved.md.j2"},
            ]
        }
    )


@pytest.fixture
def w3_mock():
    from eth_utils import apply_formatter_if
    from web3._utils.method_formatters import is_not_null, receipt_formatter

    w3 = MagicMock()
    w3.eth.get_transaction_receipt.return_value = ReadableAttributeDict.recursive(
        apply_formatter_if(is_not_null, receipt_formatter, json.load(open("samples/tx-receipt.json")))
    )
    return w3


@pytest.fixture
def test_client(template_loader, template_rules, w3_mock):
    """Creates a test client and activates the app context for it"""

    with app.test_client() as testing_client:
        with app.app_context():
            jinja_env = Environment(loader=FunctionLoader(template_loader))
            jinja2_ext.add_filters(jinja_env)
            app.config["renv"] = RenderingEnv(
                jinja_env=jinja_env,
                template_rules=template_rules,
                chain=factories.Chain(),
                w3=w3_mock,
                args=None,
            )
            app.config["discord_url"] = "http://example.org/discord-webhook"
            app.config["alchemy_keys"] = {"wh_6kmi7uom6hn97voi": "T0pS3cr3t"}
            yield testing_client


@pytest.fixture(autouse=True)
def event_definitions():
    abis_path = os.path.dirname(__file__) / Path("abis")
    yield EventDefinition.load_all_events([abis_path])
    EventDefinition.reset_registry()


@pytest.fixture(autouse=True)
def address_book():
    setup_addr_book(
        AddrToNameAddressBook(
            {
                "0xf6b7a278afFbc905b407E01893B287D516016ce0": "CFL",
                "0xc1A74eaC52a195E54E0cd672A9dAB023292C6100": "PA",
                "0x88928fF265a144Aef2c5e228D536D9E477A68CFC": "SOME_WHALE",
            }
        )
    )


@pytest.fixture
def discord_mock():
    with mock.patch("eth_pretty_events.discord.post") as discord_post:
        discord_post.return_value = MagicMock(status_code=200)
        yield discord_post


def test_render_tx_endpoint(test_client):
    tx = factories.Tx()
    response = test_client.get(f"/render/tx/{tx.hash}/")
    assert response.status_code == 200
    assert response.json == [
        "Transfer 212 from PA to CFL",
        "Policy 28346159186922404940890606216407517056979643723175576033330501230939569004948 resolved for 212",
    ]


def test_alchemy_webhook_happy(test_client, discord_mock, caplog):
    caplog.set_level("INFO")
    with open("samples/alchemy-sample.json") as f:
        payload = f.read()

    response = test_client.post(
        "/alchemy-webhook/",
        data=payload,
        headers={"x-alchemy-signature": ALCHEMY_SAMPLE_SIGNATURE, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json == {"status": "ok", "ok_count": 1, "failed_count": 0}

    discord_mock.assert_called_once_with(
        "http://example.org/discord-webhook",
        {
            "embeds": [
                {"description": "Transfer 240.072021 from SOME_WHALE to 0xBA12222222228d8Ba445958a75a0704d566BF2C8"}
            ]
        },
    )

    assert "INFO" in [record.levelname for record in caplog.records]
    assert any("Result: ok" in record.message for record in caplog.records)
    assert any("ok_count: 1, failed_count: 0" in record.message for record in caplog.records)


def test_alchemy_webhook_unknown_webhook_id(test_client, discord_mock):

    response = test_client.post(
        "/alchemy-webhook/",
        json={"webhookId": "wh_madeupid"},
        headers={"x-alchemy-signature": "DOES NOT MATTER"},
    )
    assert response.status_code == 200
    assert response.json == {}


def test_alchemy_webhook_invalid_signature(test_client, discord_mock):
    with open("samples/alchemy-sample.json") as f:
        payload = f.read()

    response = test_client.post(
        "/alchemy-webhook/",
        data=payload,
        headers={"x-alchemy-signature": "invalid", "content-type": "application/json"},
    )
    assert response.status_code == 403
    assert response.json == {"error": "Forbidden"}

    response = test_client.post(
        "/alchemy-webhook/",
        json={},
    )


def test_alchemy_webhook_with_failed_messages(test_client, discord_mock, caplog):
    caplog.set_level("ERROR")

    discord_mock.return_value = MagicMock(status_code=404, content=b"Webhook not found")

    with open("samples/alchemy-sample.json") as f:
        payload = f.read()

    response = test_client.post(
        "/alchemy-webhook/",
        data=payload,
        headers={"x-alchemy-signature": ALCHEMY_SAMPLE_SIGNATURE, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json == {"status": "error", "ok_count": 0, "failed_count": 1}
    assert discord_mock.call_count == 1

    assert any(record.levelname == "ERROR" for record in caplog.records)
    assert any("Result: error" in record.message for record in caplog.records)
    assert any("ok_count: 0, failed_count: 1" in record.message for record in caplog.records)
