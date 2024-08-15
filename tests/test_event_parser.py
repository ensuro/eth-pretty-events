import json
import os
from pathlib import Path

import pytest
from hexbytes import HexBytes
from web3.types import LogReceipt

from eth_pretty_events.event_parser import EventDefinition
from eth_pretty_events.types import Address, Block, Chain

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

chain = Chain(id=137, name="Polygon")

block = Block(
    chain=chain,
    number=34530281,
    hash="0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
    timestamp=1666168181,
)

# LogReceipt as parsed and expected by Web3
transfer_log: LogReceipt = {
    "transactionHash": HexBytes("0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf"),
    "address": "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2",
    "blockHash": HexBytes(block.hash),
    "blockNumber": block.number,
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
    "hash": block.hash,
    "number": block.number,
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
    global block

    abi = json.loads(TRANSFER_EVENT)
    evt_def = EventDefinition.from_abi(abi)
    assert evt_def.name == "Transfer"

    evt = evt_def.get_event_data(transfer_log, block=block)
    assert evt is not None
    assert evt.address == "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2"
    assert evt.tx.index == 1
    assert evt.tx.hash == "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf"
    assert evt.tx.block.hash == "0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506"
    assert evt.args._fields == ("from_", "to", "value")
    addr_from = Address("0xd758af6bfc2f0908d7c5f89942be52c36a6b3cab")
    addr_to = Address("0x8fca634a6edec7161def4478e94b930ea275a8a2")
    assert evt.args["from"] == addr_from
    assert evt.args["to"] == addr_to
    assert evt.log_index == 2
    assert evt.name == "Transfer"

    assert evt_def.dict_log_to_log_receipt(transfer_dict_log) == transfer_log


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
    global block

    EventDefinition.load_all_events([ABIS_PATH])

    evt = EventDefinition.read_log(transfer_log, block=block)

    assert evt is not None
    assert evt.name == "Transfer"

    # Test an event that has a struct in its arguments
    new_policy_log = EventDefinition.dict_log_to_log_receipt(new_policy_dict_log)
    new_policy_evt = EventDefinition.read_log(new_policy_log, block=block)
    assert isinstance(new_policy_evt.args.policy, tuple)
    assert new_policy_evt.args.policy.ensuroCommission == 2048142
    assert new_policy_evt.args.policy.riskModule == "0x0d175CB042dd6997ac37588954Fc5A7b8bab5615"


def test_loads_when_multiple_abis_for_same_topic():
    EventDefinition.load_all_events([ABIS_PATH])

    transfer_evt_def = EventDefinition.get_by_topic(
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )
    assert len(transfer_evt_def.abis) == 2  # Has ERC20 Transfer and ERC721 Transfer
    assert len(transfer_evt_def.args_types) == 2  # Has ERC20 Transfer and ERC721 Transfer
    if transfer_evt_def.args_types[0]._fields == ("from_", "to", "value"):
        assert [i["name"] for i in transfer_evt_def.abis[0]["inputs"]] == ["from", "to", "value"]
        assert transfer_evt_def.args_types[1]._fields == ("from_", "to", "tokenId")
        assert [i["name"] for i in transfer_evt_def.abis[1]["inputs"]] == ["from", "to", "tokenId"]
    else:
        assert transfer_evt_def.args_types[0]._fields == ("from_", "to", "tokenId")
        assert [i["name"] for i in transfer_evt_def.abis[0]["inputs"]] == ["from", "to", "tokenId"]
        assert transfer_evt_def.args_types[1]._fields == ("from_", "to", "value")
        assert [i["name"] for i in transfer_evt_def.abis[1]["inputs"]] == ["from", "to", "value"]


@pytest.mark.parametrize(
    "log_entry, expected_result",
    [
        (
            {
                "transactionHash": "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf",
                "address": "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2",
                "blockHash": "0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
                "blockNumber": 34530281,
                "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
                "logIndex": 2,
                "removed": False,
                "topics": [],
                "transactionIndex": 1,
            },
            None,
        ),
        (
            {
                "transactionHash": "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf",
                "address": "0x9aa7fEc87CA69695Dd1f879567CcF49F3ba417E2",
                "blockHash": "0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
                "blockNumber": 34530281,
                "data": "0x00000000000000000000000000000000000000000000000000000002540be400",
                "logIndex": 2,
                "removed": False,
                "topics": [HexBytes("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")],
                "transactionIndex": 1,
            },
            None,
        ),
    ],
)
def test_read_log_return_none(log_entry, expected_result):
    chain = Chain(id=137, name="Polygon")
    block = Block(
        chain=chain,
        number=34530281,
        hash="0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
        timestamp=1666168181,
    )

    EventDefinition._registry = {}

    result = EventDefinition.read_log(log_entry, block)

    assert result == expected_result
