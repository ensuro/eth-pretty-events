import asyncio
import json
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
import requests
from aiohttp import web
from jinja2 import Environment, FunctionLoader

from eth_pretty_events.discord import DiscordOutput, build_transaction_messages, post
from eth_pretty_events.event_filter import read_template_rules
from eth_pretty_events.jinja2_ext import add_filters
from eth_pretty_events.outputs import DecodedTxLogs
from eth_pretty_events.types import Block, Chain, Event, Hash, Tx, make_abi_namedtuple


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
            # Example template for too long description event test
            "large-description-event.md.j2": "{{ evt.args.large_description }}",
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
                {
                    "match": [{"event": "LargeDescriptionEvent"}],
                    "template": "large-description-event.md.j2",
                },  # Example template rule for too long description event test
                {"match": [{"event": "TaggedTransfer"}], "template": "ERC20-transfer.md.j2", "tags": ["alerts"]},
            ]
        }
    )


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
def alchemy_sample_events(mock_tx):
    with open("samples/alchemy-sample.json") as f:
        samples = json.load(f)

    abi_components = [
        {"name": "from_", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
    ]
    Args = make_abi_namedtuple("Transfer", abi_components)

    return [
        Event(
            address=log["account"]["address"],
            args=Args(
                from_=log["topics"][1],
                to=log["topics"][2],
                value=int(log["data"], 16),
            ),
            tx=mock_tx,
            name="Transfer",
            log_index=log["index"],
        )
        for log in samples["event"]["data"]["block"]["logs"]
    ]


@pytest.fixture
async def setup_output(aiohttp_client, dummy_renv, template_rules, template_loader):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    async def webhook_handler(request):
        payload = await request.json()
        request.app["payloads"].append(payload)
        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app["payloads"] = []
    app["status_code"] = 200

    client = await aiohttp_client(app)
    webhook_url = client.make_url("/webhook")

    queue = asyncio.Queue()
    url = "discord://?from_env=DISCORD_URL&max_attempts=2&retry_time=1"
    with patch.dict("os.environ", {"DISCORD_URL": str(webhook_url)}):
        output = DiscordOutput(urlparse(url), dummy_renv)

    return output, queue, app


def test_discord_output_missing_env_var(dummy_renv):
    url = urlparse("discord://localhost")
    with pytest.raises(RuntimeError, match="Must define the Discord URL in DISCORD_URL env variable"):
        DiscordOutput(url, dummy_renv)


def test_discord_output_with_env_var(dummy_renv):
    with patch.dict("os.environ", {"DISCORD_URL": "https://discord.com/api/webhooks/test"}):
        url = urlparse("discord://localhost")
        output = DiscordOutput(url, dummy_renv)
        assert output.discord_url == "https://discord.com/api/webhooks/test"


def test_build_transaction_messages_limits(dummy_renv, template_rules, template_loader, mock_tx, alchemy_sample_events):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    tx_raw_logs = [{} for _ in alchemy_sample_events]
    messages = list(build_transaction_messages(dummy_renv, mock_tx, alchemy_sample_events, tx_raw_logs))

    assert len(messages) >= 1
    assert all(len(message["embeds"]) <= 9 for message in messages)
    assert all(sum(len(json.dumps(embed)) for embed in message["embeds"]) <= 5000 for message in messages)


@pytest.mark.asyncio
async def test_run_webhook_response(setup_output, alchemy_sample_events, mock_tx):
    output, queue, app = await setup_output
    raw_logs = [{} for _ in alchemy_sample_events]  # Not used in this test, just needs to be the same length
    decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=raw_logs, decoded_logs=alchemy_sample_events)
    task = asyncio.create_task(output.run(queue))
    await queue.put(decoded_logs)
    await asyncio.sleep(1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(app["payloads"]) > 0
    payload = app["payloads"][0]
    assert "embeds" in payload
    assert len(payload["embeds"]) > 0


def test_run_sync_with_valid_messages(dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)
    url = "discord://?from_env=DISCORD_URL"
    with patch("requests.Session.post", return_value=MagicMock(status_code=200)) as mock_post:

        with patch.dict("os.environ", {"DISCORD_URL": "https://discord.com/api/webhooks/test"}):
            output = DiscordOutput(urlparse(url), dummy_renv)

            decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=[], decoded_logs=alchemy_sample_events)

            output.run_sync([decoded_logs])

            assert mock_post.call_count == len(
                list(build_transaction_messages(dummy_renv, mock_tx, alchemy_sample_events, tx_raw_logs=[]))
            )


def test_build_transaction_messages_with_tag_filter(
    dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    tagged_event = Event(
        tx=mock_tx,
        address="0xabc123",
        args={"from_": "0xabc", "to": "0xdef", "value": 123},
        name="TaggedTransfer",
        log_index=0,
    )

    all_events = alchemy_sample_events + [tagged_event]  # al the sample events + the event to be filtered.
    tx_raw_logs = [{"logIndex": e.log_index} for e in all_events]

    messages = list(build_transaction_messages(dummy_renv, mock_tx, all_events, tx_raw_logs, tags=["alerts"]))

    assert len(messages) == 1


@pytest.mark.asyncio
async def test_run_warning_logs(
    aiohttp_client, dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    async def webhook_handler(request):
        return web.Response(status=500, text="Internal Server Error")

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app["payloads"] = []

    client = await aiohttp_client(app)
    webhook_url = client.make_url("/webhook")

    queue = asyncio.Queue()
    url = "discord://?from_env=DISCORD_URL&max_attempts=2&retry_time=1"
    with patch.dict("os.environ", {"DISCORD_URL": str(webhook_url)}):
        output = DiscordOutput(urlparse(url), dummy_renv)
        raw_logs = [{} for _ in alchemy_sample_events]  # Not used in this test, just needs to be the same length
        decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=raw_logs, decoded_logs=alchemy_sample_events)

        with caplog.at_level("WARNING"):
            task = asyncio.create_task(output.run(queue))
            await queue.put(decoded_logs)
            await asyncio.sleep(2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert "Unexpected result 500" in caplog.text
        assert "Retrying in 1.0 seconds..." in caplog.text
        assert "Discord response body: Internal Server Error" in caplog.text


@pytest.mark.asyncio
async def test_run_warning_logs_400(
    aiohttp_client, dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    async def webhook_handler(request):
        return web.Response(status=400, text="Bad Request")

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app["payloads"] = []

    client = await aiohttp_client(app)
    webhook_url = client.make_url("/webhook")

    queue = asyncio.Queue()
    url = "discord://?from_env=DISCORD_URL&max_attempts=2&retry_time=1"
    with patch.dict("os.environ", {"DISCORD_URL": str(webhook_url)}):
        output = DiscordOutput(urlparse(url), dummy_renv)
        raw_logs = [{} for _ in alchemy_sample_events]
        decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=raw_logs, decoded_logs=alchemy_sample_events)

        with caplog.at_level("WARNING"):
            task = asyncio.create_task(output.run(queue))
            await queue.put(decoded_logs)
            await asyncio.sleep(1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert "Unexpected result 400" in caplog.text
        assert "Discord response body: Bad Request" in caplog.text


def test_run_sync_with_warning_logs(
    dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)
    url = "discord://?from_env=DISCORD_URL&max_attempts=2&retry_time=1"
    with patch("requests.Session.post", return_value=MagicMock(status_code=500, content=b"Internal Server Error")):

        with patch.dict("os.environ", {"DISCORD_URL": "https://discord.com/api/webhooks/test"}):
            output = DiscordOutput(urlparse(url), dummy_renv)
            raw_logs = [{} for _ in alchemy_sample_events]  # Not used in this test, just needs to be the same length
            decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=raw_logs, decoded_logs=alchemy_sample_events)

            with caplog.at_level("WARNING"):
                output.run_sync([decoded_logs])

            assert "Unexpected result 500" in caplog.text
            assert "Retrying in 1.0 seconds..." in caplog.text
            assert "Discord response body: Internal Server Error" in caplog.text


def test_run_sync_with_warning_logs_400(
    dummy_renv, template_rules, template_loader, alchemy_sample_events, mock_tx, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)
    url = "discord://?from_env=DISCORD_URL&max_attempts=2&retry_time=1"

    with patch("requests.Session.post", return_value=MagicMock(status_code=400, content=b"Bad Request")):
        with patch.dict("os.environ", {"DISCORD_URL": "https://discord.com/api/webhooks/test"}):
            output = DiscordOutput(urlparse(url), dummy_renv)
            raw_logs = [{} for _ in alchemy_sample_events]
            decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=raw_logs, decoded_logs=alchemy_sample_events)

            with caplog.at_level("WARNING"):
                output.run_sync([decoded_logs])

            assert "Unexpected result 400" in caplog.text
            assert "Discord response body: Bad Request" in caplog.text


def test_build_transaction_messages_none_events(dummy_renv, mock_tx):
    dummy_renv.template_rules = []
    events = [None, Event(tx=mock_tx, address="0x0", args={}, name="TestEvent", log_index=0)]
    messages = list(build_transaction_messages(dummy_renv, mock_tx, events, tx_raw_logs=[]))
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_send_to_output_sync_not_implemented(setup_output, mock_tx):
    output, queue, _ = await setup_output

    decoded_logs = DecodedTxLogs(tx=mock_tx, raw_logs=[], decoded_logs=[])

    await queue.put(decoded_logs)
    with pytest.raises(NotImplementedError):
        await output.send_to_output_sync(decoded_logs)


def test_post_initializes_session():
    global _session
    _session = None

    with patch("requests.Session", autospec=True) as mock_session_class:
        mock_session_instance = mock_session_class.return_value
        mock_post = mock_session_instance.post
        mock_post.return_value = MagicMock(status_code=200)

        url = "https://discord.com/api/webhooks/test"
        payload = {"key": "value"}
        response = post(url, payload)

        _session = mock_session_instance

        assert _session is mock_session_instance

        mock_session_class.assert_called_once()

        mock_post.assert_called_once_with(url, json=payload)

        assert response.status_code == 200


def test_posting_not_itializes_session():
    global _session
    _session = requests.Session()

    with patch.object(_session, "post", return_value=MagicMock(status_code=200)) as mock_post:
        with patch("eth_pretty_events.discord._session", _session):
            url = "https://discord.com/api/webhooks/test"
            payload = {"key": "value"}
            response = post(url, payload)

            mock_post.assert_called_once_with(url, json=payload)

            assert response.status_code == 200


def test_build_transaction_large_description_truncation_one_event(
    dummy_renv, template_rules, template_loader, mock_tx, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    long_description = "FOO" * 1500  # To ensure the description length exceed the 4096 discord limit
    large_event = Event(
        tx=mock_tx,
        address="0x0",
        args={"large_description": long_description},
        name="LargeDescriptionEvent",
        log_index=1,
    )

    tx_raw_logs = [{"logIndex": large_event.log_index}]

    with caplog.at_level("INFO"):
        messages = list(build_transaction_messages(dummy_renv, mock_tx, [large_event], tx_raw_logs))

    assert len(messages) == 1
    assert "embeds" in messages[0]

    truncated_description = messages[0]["embeds"][0]["description"]
    assert len(truncated_description) == 4096 - 100

    expected_log = (
        f"Truncated description for event in tx: {mock_tx.hash}, index: {large_event.log_index} "
        f"(original length: {len(long_description)}, new length: 3996)"
    )
    assert expected_log in caplog.text


def test_build_transaction_first_event_large_description_truncates_in_multiple_events(
    dummy_renv, template_rules, template_loader, mock_tx, alchemy_sample_events, caplog
):
    dummy_renv.template_rules = template_rules
    dummy_renv.jinja_env = Environment(loader=FunctionLoader(template_loader))
    add_filters(dummy_renv.jinja_env)

    long_description = "FOO" * 1500  # To ensure the description length exceed the 4096 discord limit
    large_event = Event(
        tx=mock_tx,
        address="0x0",
        args={"large_description": long_description},
        name="LargeDescriptionEvent",
        log_index=1,
    )

    tx_events = [large_event] + alchemy_sample_events
    tx_raw_logs = [{"logIndex": event.log_index} for event in tx_events]

    with caplog.at_level("INFO"):
        messages = list(build_transaction_messages(dummy_renv, mock_tx, tx_events, tx_raw_logs))

    assert all(len(message["embeds"]) <= 9 for message in messages)
    assert all(sum(len(json.dumps(embed)) for embed in message["embeds"]) <= 5000 for message in messages)

    assert len(messages[0]["embeds"]) != 0
    truncated_description = messages[0]["embeds"][0]["description"]
    assert len(truncated_description) == 4096 - 100

    expected_log = (
        f"Truncated description for event in tx: {mock_tx.hash}, index: {large_event.log_index} "
        f"(original length: {len(long_description)}, new length: 3996)"
    )
    assert expected_log in caplog.text
    assert caplog.text.count("Truncated description for event") == 1
