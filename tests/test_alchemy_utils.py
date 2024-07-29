from hexbytes import HexBytes

from eth_pretty_events.alchemy_utils import graphql_log_to_log_receipt

# LogReceipt as parsed and expected by Web3
transfer_log = {
    "transactionHash": HexBytes("0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf"),
    "address": "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2",
    "blockHash": HexBytes("0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506"),
    "blockNumber": 34530281,
    "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
    "logIndex": 2,
    "removed": False,
    "topics": [
        HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"),
        HexBytes("0x000000000000000000000000d758af6bfc2f0908d7c5f89942be52c36a6b3cab"),
        HexBytes("0x0000000000000000000000008fca634a6edec7161def4478e94b930ea275a8a2"),
    ],
    "transactionIndex": 1,
}

# Log in GraphQL format
graphql_log = {
    "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
    "topics": [
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        "0x000000000000000000000000d758af6bfc2f0908d7c5f89942be52c36a6b3cab",
        "0x0000000000000000000000008fca634a6edec7161def4478e94b930ea275a8a2",
    ],
    "index": 2,
    "account": {"address": "0x9aa7fec87ca69695dd1f879567ccf49f3ba417e2"},
    "transaction": {
        "hash": "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf",
        "index": 1,
    },
}

# Block in GraphQL format (only the fields relevant for event parsing)
gql_block_log = {
    "hash": "0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
    "number": 34530281,
}


def test_graphql_log_to_log_receipt():
    assert graphql_log_to_log_receipt(graphql_log, gql_block_log) == transfer_log
