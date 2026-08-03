import asyncio
import json
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

from eth_pretty_events.event_filter import EventFilter, TemplateRule
from eth_pretty_events.outputs import DecodedTxLogs
from eth_pretty_events.pubsub import (
    PrintToScreenPublisher,
    PubSubDecodedLogsOutput,
    PubSubRawLogsOutput,
)
from eth_pretty_events.types import (
    Block,
    Chain,
    DecodeEventError,
    Event,
    Hash,
    Tx,
    make_abi_namedtuple,
)


@pytest.fixture
def mock_future():
    class MockFuture:
        def result(self):
            return "mock-message-id"

    return MockFuture


@pytest.fixture
def dummy_queue():
    return asyncio.Queue()


@pytest.fixture
def dummy_renv():
    renv = MagicMock()
    renv.template_rules = []
    return renv


def _renv_with_rules(rules):
    renv = MagicMock()
    renv.template_rules = rules
    return renv


def _log_with_event(event_name):
    tx = Tx(
        hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
        index=0,
        block=Block(
            hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
            timestamp=1635600000,
            number=123456,
            chain=Chain(id=1, name="Ethereum Mainnet"),
        ),
    )
    log = DecodedTxLogs(tx=tx, raw_logs=[])
    log.decoded_logs = [
        Event(address="0x742d35cc6634c0532925a3b844bc454e4438f44e", args=None, tx=None, name=event_name, log_index=0)
    ]
    return log


def test_pubsub_output_tags_of_matching_rules_become_attributes(mock_future):
    renv = _renv_with_rules(
        [
            TemplateRule(template="x", match=EventFilter.from_config({"name": "Transfer"}), tags=["ETKActivity"]),
            TemplateRule(template="y", match=EventFilter.from_config({"name": "Transfer"}), tags=["LPActivity"]),
            TemplateRule(template="z", match=EventFilter.from_config({"name": "Approval"}), tags=["Unrelated"]),
        ]
    )
    url = urlparse("pubsubrawlogs://?project_id=test_project&topic=test_topic&dry_run=false")

    with patch("eth_pretty_events.pubsub.pubsub_v1.PublisherClient") as mock_publisher:
        mock_publisher_instance = mock_publisher.return_value
        mock_publisher_instance.topic_path.return_value = "projects/test_project/topics/test_topic"
        mock_publisher_instance.publish.return_value = mock_future()
        output = PubSubRawLogsOutput(url, renv)

        asyncio.run(output.send_to_output(_log_with_event("Transfer")))

        _, kwargs = mock_publisher_instance.publish.call_args
        assert kwargs == {"tag_ETKActivity": "true", "tag_LPActivity": "true"}


def test_pubsub_output_no_matching_rule_publishes_without_attributes(mock_future):
    renv = _renv_with_rules(
        [TemplateRule(template="z", match=EventFilter.from_config({"name": "Approval"}), tags=["Unrelated"])]
    )
    url = urlparse("pubsubrawlogs://?project_id=test_project&topic=test_topic&dry_run=false")

    with patch("eth_pretty_events.pubsub.pubsub_v1.PublisherClient") as mock_publisher:
        mock_publisher_instance = mock_publisher.return_value
        mock_publisher_instance.topic_path.return_value = "projects/test_project/topics/test_topic"
        mock_publisher_instance.publish.return_value = mock_future()
        output = PubSubRawLogsOutput(url, renv)

        asyncio.run(output.send_to_output(_log_with_event("Transfer")))

        _, kwargs = mock_publisher_instance.publish.call_args
        assert kwargs == {}


def test_pubsub_output_ignores_matching_rules_without_tags(mock_future):
    renv = _renv_with_rules([TemplateRule(template="z", match=EventFilter.from_config({"name": "Transfer"}), tags=[])])
    url = urlparse("pubsubrawlogs://?project_id=test_project&topic=test_topic&dry_run=false")

    with patch("eth_pretty_events.pubsub.pubsub_v1.PublisherClient") as mock_publisher:
        mock_publisher_instance = mock_publisher.return_value
        mock_publisher_instance.topic_path.return_value = "projects/test_project/topics/test_topic"
        mock_publisher_instance.publish.return_value = mock_future()
        output = PubSubRawLogsOutput(url, renv)

        asyncio.run(output.send_to_output(_log_with_event("Transfer")))

        _, kwargs = mock_publisher_instance.publish.call_args
        assert kwargs == {}


def test_pubsub_output_base_missing_project_id_or_topic(dummy_renv):
    url_without_project_id = urlparse("pubsubrawlogs://?topic=test_topic")
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubRawLogsOutput(url_without_project_id, dummy_renv)
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubDecodedLogsOutput(url_without_project_id, dummy_renv)

    url_without_topic = urlparse("pubsubrawlogs://?project_id=test_project")
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubRawLogsOutput(url_without_topic, dummy_renv)
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubDecodedLogsOutput(url_without_topic, dummy_renv)

    url_without_both = urlparse("pubsubrawlogs://")
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubRawLogsOutput(url_without_both, dummy_renv)
    with pytest.raises(RuntimeError, match="Both 'project_id' and 'topic' must be specified in the query string"):
        PubSubDecodedLogsOutput(url_without_both, dummy_renv)


def test_pubsub_raw_logs_output_with_dry_run(dummy_renv, caplog):
    url = urlparse("pubsubrawlogs://?project_id=test_project&topic=test_topic&dry_run=true")
    output = PubSubRawLogsOutput(url, dummy_renv)

    assert output.dry_run is True
    assert output.project_id == "test_project"
    assert output.topic == "test_topic"

    tx = Tx(
        hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
        index=0,
        block=Block(
            hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
            timestamp=1635600000,
            number=123456,
            chain=Chain(id=1, name="Ethereum Mainnet"),
        ),
    )
    raw_logs = [
        {
            "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
            "topics": ["0x8c5be1e5ebec7d5bd14f714f6a97220d02b17d3c8c9f32f4d7f7e0c2a9d2f22b"],
            "data": "0x0000000000000000000000000000000000000000000000000000000000000001",
            "logIndex": 0,
        }
    ]
    log = DecodedTxLogs(tx=tx, raw_logs=raw_logs)

    with caplog.at_level("INFO"):
        asyncio.run(output.send_to_output(log))

    expected_message = {
        "transactionHash": "0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f",
        "blockHash": "0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc",
        "blockNumber": 123456,
        "blockTimestamp": 1635600000,
        "chainId": 1,
        "transactionIndex": 0,
        "logs": [
            {
                "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                "topics": ["0x8c5be1e5ebec7d5bd14f714f6a97220d02b17d3c8c9f32f4d7f7e0c2a9d2f22b"],
                "data": "0x0000000000000000000000000000000000000000000000000000000000000001",
                "logIndex": 0,
            }
        ],
    }

    assert "[Dry Run] Publishing to" in caplog.text
    assert json.dumps(expected_message, indent=2) in caplog.text


def test_pubsub_raw_logs_output_production(dummy_renv, mock_future):
    url = urlparse("pubsubrawlogs://?project_id=test_project&topic=test_topic&dry_run=false")

    with patch("eth_pretty_events.pubsub.pubsub_v1.PublisherClient") as mock_publisher:
        mock_publisher_instance = mock_publisher.return_value
        mock_publisher_instance.topic_path.return_value = "projects/test_project/topics/test_topic"

        output = PubSubRawLogsOutput(url, dummy_renv)

        assert output.dry_run is False
        assert output.project_id == "test_project"
        assert output.topic == "test_topic"

        tx = Tx(
            hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
            index=0,
            block=Block(
                hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
                timestamp=1635600000,
                number=123456,
                chain=Chain(id=1, name="ETH Mainnet"),
            ),
        )
        raw_logs = [
            {
                "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                "topics": ["0x8c5be1e5ebec7d5bd14f714f6a97220d02b17d3c8c9f32f4d7f7e0c2a9d2f22b"],
                "data": "0x0000000000000000000000000000000000000000000000000000000000000001",
                "logIndex": 0,
            }
        ]
        log = DecodedTxLogs(tx=tx, raw_logs=raw_logs)

        mock_publisher_instance.publish.return_value = mock_future()

        asyncio.run(output.send_to_output(log))

        expected_message = {
            "transactionHash": "0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f",
            "blockHash": "0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc",
            "blockNumber": 123456,
            "blockTimestamp": 1635600000,
            "chainId": 1,
            "transactionIndex": 0,
            "logs": [
                {
                    "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                    "topics": ["0x8c5be1e5ebec7d5bd14f714f6a97220d02b17d3c8c9f32f4d7f7e0c2a9d2f22b"],
                    "data": "0x0000000000000000000000000000000000000000000000000000000000000001",
                    "logIndex": 0,
                }
            ],
        }

        mock_publisher_instance.publish.assert_called_once_with(
            "projects/test_project/topics/test_topic",
            json.dumps(expected_message).encode("utf-8"),
        )


def test_pubsub_decoded_logs_output_with_dry_run(dummy_renv, caplog):
    url = urlparse("pubsubdecodedlogs://?project_id=test_project&topic=test_topic&dry_run=true")
    output = PubSubDecodedLogsOutput(url, dummy_renv)

    assert output.dry_run is True
    assert output.project_id == "test_project"
    assert output.topic == "test_topic"

    abi_components = [
        {"name": "from_", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
    ]
    Args = make_abi_namedtuple("Transfer", abi_components)
    args = Args(
        from_="0x742d35cc6634c0532925a3b844bc454e4438f44e",
        to="0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
        value=1000,
    )

    decoded_event = Event(
        address="0x742d35cc6634c0532925a3b844bc454e4438f44e",
        args=args,
        tx=None,
        name="Transfer",
        log_index=10,
    )
    tx = Tx(
        hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
        index=0,
        block=Block(
            hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
            timestamp=1635600000,
            number=123456,
            chain=Chain(id=1, name="Ethereum Mainnet"),
        ),
    )
    log = DecodedTxLogs(tx=tx, raw_logs=[])
    log.decoded_logs = [decoded_event]

    with caplog.at_level("INFO"):
        asyncio.run(output.send_to_output(log))

        expected_message = {
            "transactionHash": "0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f",
            "blockHash": "0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc",
            "blockNumber": 123456,
            "blockTimestamp": 1635600000,
            "chainId": 1,
            "transactionIndex": 0,
            "decodedLogs": [
                {
                    "name": "Transfer",
                    "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                    "logIndex": 10,
                    "args": {
                        "from_": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                        "to": "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
                        "value": 1000,
                    },
                    "abi": [
                        {"name": "from_", "type": "address"},
                        {"name": "to", "type": "address"},
                        {"name": "value", "type": "uint256"},
                    ],
                }
            ],
        }

        assert "[Dry Run] Publishing to" in caplog.text
        assert json.dumps(expected_message, indent=2) in caplog.text


def test_pubsub_decoded_logs_output_production(dummy_renv, mock_future):
    url = urlparse("pubsubdecodedlogs://?project_id=test_project&topic=test_topic&dry_run=false")

    with patch("eth_pretty_events.pubsub.pubsub_v1.PublisherClient") as mock_publisher:
        mock_publisher_instance = mock_publisher.return_value
        mock_publisher_instance.topic_path.return_value = "projects/test_project/topics/test_topic"

        output = PubSubDecodedLogsOutput(url, dummy_renv)

        assert output.dry_run is False
        assert output.project_id == "test_project"
        assert output.topic == "test_topic"

        abi_components = [
            {"name": "from_", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ]
        Args = make_abi_namedtuple("Transfer", abi_components)
        args = Args(
            from_="0x742d35cc6634c0532925a3b844bc454e4438f44e",
            to="0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
            value=1000,
        )

        decoded_event = Event(
            address="0x742d35cc6634c0532925a3b844bc454e4438f44e",
            args=args,
            tx=None,
            name="Transfer",
            log_index=10,
        )
        tx = Tx(
            hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
            index=0,
            block=Block(
                hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
                timestamp=1635600000,
                number=123456,
                chain=Chain(id=1, name="Ethereum Mainnet"),
            ),
        )
        log = DecodedTxLogs(tx=tx, raw_logs=[])
        log.decoded_logs = [decoded_event]

        mock_publisher_instance.publish.return_value = mock_future()

        asyncio.run(output.send_to_output(log))

        expected_message = {
            "transactionHash": "0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f",
            "blockHash": "0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc",
            "blockNumber": 123456,
            "blockTimestamp": 1635600000,
            "chainId": 1,
            "transactionIndex": 0,
            "decodedLogs": [
                {
                    "name": "Transfer",
                    "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                    "logIndex": 10,
                    "args": {
                        "from_": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                        "to": "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
                        "value": 1000,
                    },
                    "abi": [
                        {"name": "from_", "type": "address"},
                        {"name": "to", "type": "address"},
                        {"name": "value", "type": "uint256"},
                    ],
                }
            ],
        }

        mock_publisher_instance.publish.assert_called_once_with(
            "projects/test_project/topics/test_topic",
            json.dumps(expected_message).encode("utf-8"),
        )


def test_print_to_screen_publisher_error(caplog):
    publisher = PrintToScreenPublisher(project_id="test_project", topic="test_topic")
    topic_path = "projects/test_project/topics/test_topic"

    invalid_bytes_message = b"invalid_json"
    with caplog.at_level("ERROR"):
        publisher.publish(topic_path, invalid_bytes_message)
        assert "Failed to decode message." in caplog.text


def test_print_to_screen_publisher_non_byte_message(caplog):
    publisher = PrintToScreenPublisher(project_id="test_project", topic="test_topic")
    topic_path = "projects/test_project/topics/test_topic"

    message = {"FOO": "BAR"}
    with caplog.at_level("INFO"):
        publisher.publish(topic_path, message)
        assert "Publishing to projects/test_project/topics/test_topic:" in caplog.text
        assert str(message) in caplog.text


def test_pubsub_decoded_logs_output_filters_decode_error(dummy_renv, caplog):
    url = urlparse("pubsubdecodedlogs://?project_id=test_project&topic=test_topic&dry_run=true")
    output = PubSubDecodedLogsOutput(url, dummy_renv)

    abi_components = [
        {"name": "from_", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
    ]
    Args = make_abi_namedtuple("Transfer", abi_components)
    args = Args(
        from_="0x742d35cc6634c0532925a3b844bc454e4438f44e",
        to="0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
        value=1000,
    )

    decoded_event = Event(
        address="0x742d35cc6634c0532925a3b844bc454e4438f44e",
        args=args,
        tx=None,
        name="Transfer",
        log_index=10,
    )

    tx = Tx(
        hash=Hash("0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f"),
        index=0,
        block=Block(
            hash=Hash("0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc"),
            timestamp=1635600000,
            number=123456,
            chain=Chain(id=1, name="Ethereum Mainnet"),
        ),
    )

    decode_error = DecodeEventError(
        topic="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        log_index=5,
        address="0x742d35cc6634c0532925a3b844bc454e4438f44e",
        tx=tx,
        error="LogTopicError: Unable to decode",
    )

    log = DecodedTxLogs(tx=tx, raw_logs=[])
    log.decoded_logs = [decoded_event, decode_error]

    with caplog.at_level("INFO"):
        asyncio.run(output.send_to_output(log))

    expected_message = {
        "transactionHash": "0x4c0883a6910395bae0f94c2e1d2c37bd2e8d6c5797b7c3f8d36dd05e5f13606f",
        "blockHash": "0x5d7c5e1ce2f3410de4c99f172ddfcb087a821440134d25e7ab8353ce57e770cc",
        "blockNumber": 123456,
        "blockTimestamp": 1635600000,
        "chainId": 1,
        "transactionIndex": 0,
        "decodedLogs": [
            {
                "name": "Transfer",
                "address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                "logIndex": 10,
                "args": {
                    "from_": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                    "to": "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
                    "value": 1000,
                },
                "abi": [
                    {"name": "from_", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                ],
            }
        ],
    }

    assert "[Dry Run] Publishing to" in caplog.text
    assert json.dumps(expected_message, indent=2) in caplog.text
