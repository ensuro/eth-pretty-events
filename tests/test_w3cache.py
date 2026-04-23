from unittest.mock import MagicMock

from eth_pretty_events.w3cache import W3Cache

TX_HASH_1 = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
TX_HASH_2 = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"


class TestW3Cache:
    def test_eth_property_returns_self(self):
        mock_w3 = MagicMock()
        cache = W3Cache(mock_w3)
        assert cache.eth is cache

    def test_is_connected(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected = True
        cache = W3Cache(mock_w3)
        assert cache.is_connected() is True

    def test_get_transaction_receipt_caches(self):
        mock_w3 = MagicMock()
        receipt = MagicMock(transactionHash=TX_HASH_1)
        mock_w3.eth.get_transaction_receipt.return_value = receipt

        cache = W3Cache(mock_w3)
        result = cache.get_transaction_receipt(TX_HASH_1)

        assert result is receipt
        assert mock_w3.eth.get_transaction_receipt.call_count == 1
        assert TX_HASH_1.lower() in cache._receipt_cache

        result_cached = cache.get_transaction_receipt(TX_HASH_1)
        assert result_cached is receipt
        assert mock_w3.eth.get_transaction_receipt.call_count == 1

    def test_get_transaction_receipt_normalizes_hash(self):
        mock_w3 = MagicMock()
        receipt = MagicMock(transactionHash=TX_HASH_1.lower())
        mock_w3.eth.get_transaction_receipt.return_value = receipt

        cache = W3Cache(mock_w3)
        cache.get_transaction_receipt(TX_HASH_1.upper())

        mock_w3.eth.get_transaction_receipt.assert_called_once()
        assert TX_HASH_1.lower() in cache._receipt_cache

    def test_get_block_by_number_caches(self):
        mock_w3 = MagicMock()
        block = {"number": 123, "timestamp": 999}
        mock_w3.eth.get_block.return_value = block

        cache = W3Cache(mock_w3)
        result = cache.get_block(123)

        assert result is block
        assert mock_w3.eth.get_block.call_count == 1
        assert 123 in cache._block_cache

        result_cached = cache.get_block(123)
        assert result_cached is block
        assert mock_w3.eth.get_block.call_count == 1

    def test_get_block_by_string_passthrough(self):
        mock_w3 = MagicMock()
        block = {"number": 123, "timestamp": 999}
        mock_w3.eth.get_block.return_value = block

        cache = W3Cache(mock_w3)
        result = cache.get_block("latest")

        assert result is block
        mock_w3.eth.get_block.assert_called_once_with("latest")
        assert 123 not in cache._block_cache

    def test_get_logs_forward(self):
        mock_w3 = MagicMock()
        logs = [MagicMock()]
        mock_w3.eth.get_logs.return_value = logs

        filter_params = {"address": "0x123"}
        cache = W3Cache(mock_w3)
        result = cache.get_logs(filter_params)

        assert result is logs
        mock_w3.eth.get_logs.assert_called_once_with(filter_params)

    def test_preload_receipts_with_batch_requests(self):
        mock_w3 = MagicMock()
        receipt1 = MagicMock(transactionHash=TX_HASH_1.lower())
        receipt1.blockNumber = 100
        receipt2 = MagicMock(transactionHash=TX_HASH_2.lower())
        receipt2.blockNumber = 101

        receipt_batch = MagicMock()
        receipt_batch.execute.return_value = [receipt1, receipt2]

        block1 = MagicMock()
        block1.number = 100
        block2 = MagicMock()
        block2.number = 101
        block_batch = MagicMock()
        block_batch.execute.return_value = [block1, block2]

        mock_w3.batch_requests.side_effect = [receipt_batch, block_batch]

        cache = W3Cache(mock_w3)
        cache.preload_receipts([TX_HASH_1, TX_HASH_2])

        assert mock_w3.batch_requests.call_count == 2
        assert TX_HASH_1.lower() in cache._receipt_cache
        assert TX_HASH_2.lower() in cache._receipt_cache
        assert 100 in cache._block_cache
        assert 101 in cache._block_cache

    def test_preload_receipts_skips_cached(self):
        mock_w3 = MagicMock()
        receipt1 = MagicMock(transactionHash=TX_HASH_1.lower())
        receipt1.blockNumber = 100
        receipt2 = MagicMock(transactionHash=TX_HASH_2.lower())
        receipt2.blockNumber = 101

        receipt_batch = MagicMock()
        receipt_batch.execute.return_value = [receipt2]

        block_batch = MagicMock()
        block_batch.execute.return_value = []

        mock_w3.batch_requests.side_effect = [receipt_batch, block_batch]

        cache = W3Cache(mock_w3)
        cache._receipt_cache[TX_HASH_1.lower()] = receipt1

        cache.preload_receipts([TX_HASH_1, TX_HASH_2])

        assert TX_HASH_2.lower() in cache._receipt_cache
        assert TX_HASH_1.lower() not in receipt_batch.add_mapping.call_args[0][0][mock_w3.eth.get_transaction_receipt]

    def test_preload_receipts_batching(self):
        mock_w3 = MagicMock()
        receipts = [MagicMock() for i in range(60)]
        for i, r in enumerate(receipts):
            r.transactionHash = f"0x{i:064d}"
            r.blockNumber = i % 3

        batches = []
        for i in range(0, 60, 50):
            batch = MagicMock()
            batch.execute.return_value = receipts[i : i + 50]
            batches.append(batch)

        mock_w3.batch_requests.side_effect = iter(batches)

        block_batches = []
        for i in range(0, 3, 50):
            block_batch = MagicMock()
            block_data = []
            for j in range(i, min(i + 50, 3)):
                b = MagicMock()
                b.number = j
                block_data.append(b)
            block_batch.execute.return_value = block_data
            block_batches.append(block_batch)

        mock_w3.batch_requests.side_effect = iter(batches + block_batches)

        cache = W3Cache(mock_w3)
        cache.preload_receipts([r.transactionHash for r in receipts])

        assert mock_w3.batch_requests.call_count == 3
