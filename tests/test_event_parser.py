import json
import os
from pathlib import Path

from hexbytes import HexBytes

from eth_pretty_events.event_parser import EventDefinition

ABIS_PATH = os.path.dirname(__file__) / Path("abis")

TRANSFER_EVENT = """{
    "anonymous": false,
    "inputs": [
        {"indexed": true, "internalType": "address", "name": "from", "type": "address"},
        {"indexed": true, "internalType": "address", "name": "to", "type": "address"},
        {"indexed": false, "internalType": "uint256", "name": "value", "type": "uint256"}
    ],
    "name": "Transfer",
    "type": "event"
}"""

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

# LogReceipt as returned by RPC
transfer_dict_log = {
    "transactionHash": "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf",
    "address": "0x9aa7fec87ca69695dd1f879567ccf49f3ba417e2",
    "blockHash": 0x81145F3E891AB54554D964F901F122635BA4B00E22066157C6CABB647F959506,
    "blockNumber": "0x20ee3e9",
    "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
    "logIndex": "0x2",
    "removed": False,
    "topics": [
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        "0x000000000000000000000000d758af6bfc2f0908d7c5f89942be52c36a6b3cab",
        "0x0000000000000000000000008fca634a6edec7161def4478e94b930ea275a8a2",
    ],
    "transactionIndex": "0x1",
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

# NewPolicy log as returned by RPC
new_policy_dict_log = {
    "blockHash": "0x983aa40136fe2f90342b2fa23a7ad784c8e052b66b181b70a92fbe643534f01b",
    "address": "0xfe84d0393127919301b752824dd96d291d0e0841",
    "logIndex": "0x17",
    "data": "0x0d175cb042dd6997ac37588954fc5a7b8bab5615cbdf053c3f97cf9ccb8025080000000000000000000000000000000000000000000000000000000008786420000000000000000000000000000000000000000000000000000000000227f07400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000ad78a700000000000000000000000000000000000000000000000002c68af0bb14000000000000000000000000000000000000000000000000000000000000020869f300000000000000000000000000000000000000000000000000000000001f408e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000045f30000000000000000000000000d175cb042dd6997ac37588954fc5a7b8bab5615000000000000000000000000000000000000000000000000000000006629109000000000000000000000000000000000000000000000000000000000662cdab7",  # noqa
    "removed": False,
    "topics": [
        "0x38f420e3792044ba61536a1f83956eefc878b3fb09a7d4a28790f05b6a3eaf3b",
        "0x0000000000000000000000000d175cb042dd6997ac37588954fc5a7b8bab5615",
    ],
    "blockNumber": "0x58021d",
    "transactionIndex": "0xe",
    "transactionHash": "0x14b6eff233705f97b2e3d29e754a55697b03bea1ad61686e186d1b9b815ac136",
}


def test_transfer_event():
    global transfer_log
    global transfer_dict_log
    global gql_log
    global gql_block_log

    abi = json.loads(TRANSFER_EVENT)
    evt = EventDefinition.from_abi(abi)
    assert evt.name == "Transfer"

    log = evt.get_event_data(transfer_log)
    assert log["address"] == "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2"
    assert log["blockHash"] == HexBytes("0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506")
    assert log["blockNumber"] == 34530281
    assert log["args"] == {
        "from": "0xD758aF6BFC2f0908D7C5f89942be52C36a6b3cab",
        "to": "0x8fca634A6EDEc7161dEF4478e94B930Ea275A8a2",
        "value": 10000000000,
    }
    assert log["logIndex"] == 2
    assert log["event"] == "Transfer"
    assert log["transactionIndex"] == 1
    assert log["transactionHash"] == HexBytes("0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf")
    assert set(log.keys()) == {
        "address",
        "blockNumber",
        "blockHash",
        "args",
        "logIndex",
        "transactionHash",
        "transactionIndex",
        "event",
        "abi",
    }

    assert evt.graphql_log_to_log_receipt(graphql_log, gql_block_log) == transfer_log
    assert evt.dict_log_to_log_receipt(transfer_dict_log) == transfer_log

    assert evt.get_event_data(evt.graphql_log_to_log_receipt(graphql_log, gql_block_log)) == log
    assert evt.get_event_data(evt.dict_log_to_log_receipt(transfer_dict_log)) == log


def test_load_events():
    erc20 = json.load(open(ABIS_PATH / Path("ERC/IERC20.json")))
    events = EventDefinition.load_events(erc20["abi"])
    assert len(events) == 2

    names = set([evt.name for evt in events])

    assert len(names) == 2

    assert "Transfer" in names
    assert "Approval" in names


def test_load_all_events():
    all_events = EventDefinition.load_all_events([ABIS_PATH])
    assert len(all_events) >= 5


def test_load_all_events_then_reset():
    all_events = EventDefinition.load_all_events([ABIS_PATH])
    assert len(all_events) >= 5
    EventDefinition.reset_registry()
    all_events = EventDefinition.load_all_events([ABIS_PATH / Path("ERC")])
    assert len(all_events) == 5


def test_load_all_events_and_read_log_in_different_formats():
    EventDefinition.load_all_events([ABIS_PATH])

    log = EventDefinition.read_log(transfer_log)

    assert log is not None
    assert log["event"] == "Transfer"

    assert EventDefinition.read_dict_log(transfer_dict_log) == log
    assert EventDefinition.read_graphql_log(graphql_log, gql_block_log) == log

    # Test an event that has a struct in its arguments
    new_policy_log = EventDefinition.read_dict_log(new_policy_dict_log)
    assert isinstance(dict(new_policy_log["args"]["policy"]), dict)
    assert "ensuroCommission" in new_policy_log["args"]["policy"]
    assert "riskModule" in new_policy_log["args"]
