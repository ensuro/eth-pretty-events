import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from web3.datastructures import ReadableAttributeDict

import pytest
import yaml
from jinja2 import Environment, FunctionLoader

from eth_pretty_events.cli import RenderingEnv, _env_globals
from eth_pretty_events.event_filter import read_template_rules
from eth_pretty_events.event_parser import EventDefinition
from eth_pretty_events.address_book import AddrToNameAddressBook, setup_default as setup_addr_book
from eth_pretty_events import jinja2_ext

from . import factories


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
                    "match": [{"event": "Transfer"}, {"filter_type": "arg_exists", "arg_name": "value"}],
                    "template": "ERC20-transfer.md.j2",
                },
                {"match": [{"event": "PolicyResolved"}], "template": "policy-resolved.md.j2"},
            ]
        }
    )


@pytest.fixture
def w3_mock():
    from eth_utils import apply_formatter_if
    from web3._utils.method_formatters import receipt_formatter, is_not_null

    w3 = MagicMock()
    w3.eth.get_transaction_receipt.return_value = ReadableAttributeDict.recursive(
        apply_formatter_if(is_not_null, receipt_formatter, json.load(open("samples/tx-receipt.json")))
    )
    return w3


@pytest.fixture
def test_client(template_loader, template_rules, w3_mock):
    """Creates a test client and activates the app context for it"""
    from eth_pretty_events.flask_app import app

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
            }
        )
    )


def test_render_tx_endpoint(test_client):
    tx = factories.Tx()
    response = test_client.get(f"/render/tx/{tx.hash}/")
    assert response.status_code == 200
    assert response.json == [
        "Transfer 212 from PA to CFL",
        "Policy 28346159186922404940890606216407517056979643723175576033330501230939569004948 resolved for 212",
    ]
