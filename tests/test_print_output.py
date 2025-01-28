from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest
from jinja2 import Environment, FunctionLoader

from eth_pretty_events.event_filter import read_template_rules
from eth_pretty_events.outputs import DecodedTxLogs
from eth_pretty_events.print_output import PrintOutput
from eth_pretty_events.types import Block, Chain, Event, Hash, Tx


class PrintTemplateLoader:
    def __init__(self):
        self.templates = {
            "ERC20-transfer.md.j2": ("Transfer {{ evt.args.value }} from {{ evt.args.from }} to {{ evt.args.to }}"),
            "generic-event-on-error.md.j2": (
                "## {{ evt.name }}\n\n"
                "**TX:** {{ evt.tx.hash }}\n"
                "**Block:** {{ evt.tx.block.number }}\n"
                "**Contract:** {{ evt.address }}\n"
                "**Log Index:** {{ evt.log_index }}"
            ),
        }

    def __call__(self, name):
        return self.templates.get(name)


# Fixtures
@pytest.fixture
def template_loader():
    return PrintTemplateLoader()


@pytest.fixture(scope="session")
def template_rules():
    return read_template_rules(
        {
            "rules": [
                {
                    "match": [
                        {"event": "Transfer"},
                    ],
                    "template": "ERC20-transfer.md.j2",
                },
                {"match": [{"event": "PolicyResolved"}], "template": "policy-resolved.md.j2"},
            ]
        }
    )


@pytest.fixture
def dummy_renv():
    return MagicMock()


@pytest.fixture
def mock_tx():
    return Tx(
        block=Block(
            hash=Hash("0x578e4e045d37a7485bfcb634e514f6dbdca62ea1e29e8180d15de940046858eb"),
            number=123456,
            timestamp=1635600000,
            chain=Chain(id=1, name="Ethereum Testnet"),
        ),
        hash=Hash("0x578e4e045d37a7485bfcb634e514f6dbdca62ea1e29e8180d15de940046858eb"),
        index=1,
    )


@pytest.fixture
def mock_event(mock_tx):
    return Event(
        tx=mock_tx,
        address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        args={
            "value": 1000,
            "from": "0xabcdef1234567890abcdef123456789012345678",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
        },
        name="Transfer",
        log_index=1,
    )


class MockRawLog:
    def __init__(self, logIndex):
        self.logIndex = logIndex


@pytest.fixture
def mock_raw_log():
    return MockRawLog(logIndex=1)


def test_printoutput_unrecognized_event(dummy_renv, mock_tx, mock_raw_log, caplog):
    url = urlparse("print://")
    output = PrintOutput(url, dummy_renv)

    decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=[mock_raw_log], decoded_logs=[None])
    with caplog.at_level("WARNING"):
        output.send_to_output_sync(decoded_logs)

    assert "Unrecognized event tried to be rendered in tx" in caplog.text


def test_printoutput_prints_event(
    dummy_renv, template_rules, template_loader, mock_tx, mock_event, mock_raw_log, capfd
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    url = urlparse("print://")
    output = PrintOutput(url, dummy_renv)

    decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=[mock_raw_log], decoded_logs=[mock_event])
    output.send_to_output_sync(decoded_logs)

    captured = capfd.readouterr()
    output_value = captured.out
    assert (
        "Transfer 1000 from 0xabcdef1234567890abcdef123456789012345678 to 0x1234567890abcdef1234567890abcdef12345678"
        in output_value
    )
    assert "--------------------------" in output_value


def test_printoutput_no_printing_event(dummy_renv, template_loader, mock_tx, mock_event, capfd):
    dummy_renv.template_rules = []
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))

    url = urlparse("print://")
    output = PrintOutput(url, dummy_renv)

    decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=[], decoded_logs=[mock_event])
    output.send_to_output_sync(decoded_logs)

    captured = capfd.readouterr()
    output_value = captured.out

    assert output_value == ""
