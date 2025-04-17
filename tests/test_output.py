import asyncio
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from web3 import types as web3types

from eth_pretty_events.outputs import DecodedTxLogs, DummyOutput, OutputBase
from eth_pretty_events.types import Hash, Tx


@pytest.fixture
def queue():
    return asyncio.Queue()


@pytest.fixture
def dummy_output(queue):
    return DummyOutput(urlparse("dummy://url"))


def test_outputbase_register(dummy_output):
    assert "dummy" in OutputBase.OUTPUT_REGISTRY
    assert OutputBase.OUTPUT_REGISTRY["dummy"] == type(dummy_output)


def test_outputbase_build_output(queue):
    output_instance = OutputBase.build_output("dummy://url", renv={})
    assert isinstance(output_instance, DummyOutput)


def test_outputbase_build_output_unsupported(queue):
    with pytest.raises(RuntimeError, match="Unsupported output type unsupported"):
        OutputBase.build_output("unsupported://url", renv={})


def test_dummyoutput_send_to_output(dummy_output):
    tx = Tx(block=None, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a"), index=1)
    raw_logs = [
        web3types.LogReceipt(
            {
                "data": "log_data",
                "topics": [],
                "address": "0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a",
            }
        )
    ]
    decoded_logs = ["decoded_event"]
    decoded_tx_logs = DecodedTxLogs(tx=tx, raw_logs=raw_logs, decoded_logs=decoded_logs)

    with patch("pprint.pprint") as mock_pprint:
        asyncio.run(dummy_output.send_to_output(decoded_tx_logs))
        mock_pprint.assert_called_once_with(decoded_tx_logs)


def test_dummyoutput_send_to_output_sync(dummy_output):
    tx = Tx(block=None, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a"), index=1)
    raw_logs = [
        web3types.LogReceipt(
            {
                "data": "log_data",
                "topics": [],
                "address": "0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a",
            }
        )
    ]
    decoded_logs = ["decoded_event"]
    decoded_tx_logs = DecodedTxLogs(tx=tx, raw_logs=raw_logs, decoded_logs=decoded_logs)

    with patch("pprint.pprint") as mock_pprint:
        dummy_output.send_to_output_sync(decoded_tx_logs)
        mock_pprint.assert_called_once_with(decoded_tx_logs)


def test_outputbase_run(dummy_output, queue):
    tx1 = Tx(block=None, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a"), index=1)
    decoded_tx_logs1 = DecodedTxLogs(tx=tx1, raw_logs=[], decoded_logs=[])
    tx2 = Tx(block=None, hash=Hash("0x4a76712bb2be112fd59f3a4f285dbc3c4b39914f557e5e336cf95b3cf4545328"), index=2)
    decoded_tx_logs2 = DecodedTxLogs(tx=tx2, raw_logs=[], decoded_logs=[])

    asyncio.run(queue.put(decoded_tx_logs1))
    asyncio.run(queue.put(decoded_tx_logs2))

    with patch.object(dummy_output, "send_to_output", new_callable=AsyncMock) as mock_send_to_output:

        async def run_output():
            task = asyncio.create_task(dummy_output.run(queue))
            await asyncio.sleep(0.1)
            task.cancel()

        asyncio.run(run_output())

        mock_send_to_output.assert_any_call(decoded_tx_logs1)
        mock_send_to_output.assert_any_call(decoded_tx_logs2)
        assert mock_send_to_output.call_count == 2
        assert queue.empty()


def test_outputbase_run_sync(dummy_output):
    tx1 = Tx(block=None, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a"), index=1)
    decoded_tx_logs1 = DecodedTxLogs(tx=tx1, raw_logs=[], decoded_logs=[])
    tx2 = Tx(block=None, hash=Hash("0x4a76712bb2be112fd59f3a4f285dbc3c4b39914f557e5e336cf95b3cf4545328"), index=2)
    decoded_tx_logs2 = DecodedTxLogs(tx=tx2, raw_logs=[], decoded_logs=[])

    logs = [decoded_tx_logs1, decoded_tx_logs2]

    with patch.object(dummy_output, "send_to_output_sync") as mock_send_to_output_sync:
        dummy_output.run_sync(logs)

        mock_send_to_output_sync.assert_any_call(decoded_tx_logs1)
        mock_send_to_output_sync.assert_any_call(decoded_tx_logs2)
        assert mock_send_to_output_sync.call_count == 2


def test_outputbase_register_duplicate_type():
    type = "dummy"
    with pytest.raises(ValueError, match=f"Duplicate output type {type}"):
        OutputBase.register(type)(DummyOutput)


def test_outputbase_tags():
    output = DummyOutput(urlparse("dummy://localhost?tags=foo,bar,baz"))
    assert output.tags == ["foo", "bar", "baz"]


def test_outputbase_tags_none():
    output = DummyOutput(urlparse("dummy://localhost"))
    assert output.tags is None
