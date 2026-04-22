from typing import Dict, Sequence, Union

from web3 import Web3
from web3 import types as web3types


class W3Cache:
    """Web3 wrapper with TX receipt and block caching."""

    def __init__(self, w3: Web3):
        self._w3 = w3
        self._receipt_cache: Dict[str, web3types.TxReceipt] = {}
        self._block_cache: Dict[int, web3types.BlockData] = {}

    @property
    def eth(self) -> "W3Cache":
        return self

    def is_connected(self) -> bool:
        return self._w3.is_connected

    def get_transaction_receipt(self, tx_hash: str) -> web3types.TxReceipt:
        tx_hash = tx_hash.lower()
        if tx_hash in self._receipt_cache:
            return self._receipt_cache[tx_hash]
        receipt = self._w3.eth.get_transaction_receipt(tx_hash)
        self._receipt_cache[tx_hash] = receipt
        return receipt

    def get_block(self, block_identifier: Union[int, str]) -> web3types.BlockData:
        if isinstance(block_identifier, int):
            if block_identifier in self._block_cache:
                return self._block_cache[block_identifier]
            block = self._w3.eth.get_block(block_identifier)
            self._block_cache[block_identifier] = block
            return block
        return self._w3.eth.get_block(block_identifier)

    def get_logs(self, filter_params: dict) -> Sequence[web3types.LogReceipt]:
        return self._w3.eth.get_logs(filter_params)

    def preload_receipts(self, tx_hashes: Sequence[str], batch_size: int = 50):
        """Pre-load TX receipts using batched RPC calls."""
        uncached = [h.lower() for h in tx_hashes if h.lower() not in self._receipt_cache]
        for i in range(0, len(uncached), batch_size):
            batch = self._w3.batch_requests()
            batch.add_mapping(
                {
                    self._w3.eth.get_transaction_receipt: uncached[i : i + batch_size],
                }
            )
            for receipt in batch.execute():
                self._receipt_cache[receipt.transactionHash.lower()] = receipt
