import json
import os
from pathlib import Path

import pytest
from hexbytes import HexBytes

from eth_pretty_events import types

ABIS_PATH = os.path.dirname(__file__) / Path("abis")

IERC20_ABI = json.load(open(ABIS_PATH / "ERC/IERC20.json"))["abi"]
POLICYPOOL_ABI = json.load(open(ABIS_PATH / "ensuro/PolicyPool.json"))["abi"]
AM_ABI = json.load(open(ABIS_PATH / "openzeppelin/IAccessManager.json"))["abi"]

USDC_ADDR = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
OTHER_ADDR = "0x3898a4ff6B65D1F8fA89372CfE250d03BE0b2D84"
SOME_HASH = "0x37a50ac80e26cbf0005469713177e3885800188d80b92134f150685e931aa4bf"

TRANSFER_WITH_UNDERSCORE = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "_from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "_to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "_value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]


def _get_event(abi, event_name):
    return next(evt for evt in abi if evt["type"] == "event" and evt["name"] == event_name)


def test_hash_type():
    assert SOME_HASH == types.Hash(SOME_HASH)
    assert SOME_HASH == types.Hash(SOME_HASH.upper())
    assert SOME_HASH == types.Hash(HexBytes(0x37A50AC80E26CBF0005469713177E3885800188D80B92134F150685E931AA4BF))
    with pytest.raises(ValueError, match="is not a valid hash"):
        types.Hash(HexBytes(0x2791BCA))
    with pytest.raises(ValueError, match="is not a valid hash"):
        types.Hash("0x2791BCA")
    with pytest.raises(ValueError, match="Only HexBytes, bytes or str"):
        types.Hash(0x37A50AC80E26CBF0005469713177E3885800188D80B92134F150685E931AA4BF)


def test_address_type():
    assert USDC_ADDR == types.Address(USDC_ADDR)
    assert USDC_ADDR == types.Address(USDC_ADDR.lower())
    assert USDC_ADDR == types.Address(HexBytes(0x2791BCA1F2DE4661ED88A30C99A7A9449AA84174))
    with pytest.raises(ValueError):
        types.Address(HexBytes(0x2791BCA))
    with pytest.raises(ValueError):
        types.Address("0x2791Bca1f2de4661ED88A30C99A7" + "a9449Aa84174".lower())


def test_args_registry():
    assert types.arg_from_solidity_type("bool") is bool
    assert types.arg_from_solidity_type("int123") is int
    assert types.arg_from_solidity_type("uint123") is int
    assert types.arg_from_solidity_type("bytes32") is types.Hash
    assert types.arg_from_solidity_type("address") is types.Address
    bytes_ = b"\x12\x34\x56"
    assert types.arg_from_solidity_type("bytes")(bytes_) == bytes_.hex()
    address_array = ["0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "0x625E7708f30cA75bfd92586e17077590C60eb4cD"]
    assert types.arg_from_solidity_type("address[]")(address_array) == address_array
    int_array = [1, 2, 3, 4, 5]
    assert types.arg_from_solidity_type("uint256[]")(int_array) == int_array
    with pytest.raises(RuntimeError, match="Unsupported type unknown_type"):
        types.arg_from_solidity_type("unknown_type")


def test_make_abi_namedtuple():
    transfer = _get_event(IERC20_ABI, "Transfer")
    transfer_nt_type = types.make_abi_namedtuple("Transfer", transfer["inputs"])
    assert transfer_nt_type._fields == ("from_", "to", "value")
    transfer_nt = transfer_nt_type.from_args({"from": USDC_ADDR, "to": OTHER_ADDR, "value": 1000000})
    assert len(transfer_nt) == 3
    assert isinstance(transfer_nt, tuple)
    assert transfer_nt["from"] == USDC_ADDR
    assert transfer_nt["from_"] == USDC_ADDR
    assert transfer_nt.from_ == USDC_ADDR
    assert transfer_nt[0] == USDC_ADDR
    assert transfer_nt.to == OTHER_ADDR
    assert isinstance(transfer_nt.to, types.Address)
    assert transfer_nt.value == 1000000

    new_policy = _get_event(POLICYPOOL_ABI, "NewPolicy")
    new_policy_nt_type = types.make_abi_namedtuple("NewPolicy", new_policy["inputs"])
    assert new_policy_nt_type._fields == ("riskModule", "policy")
    assert new_policy_nt_type._tuple_components["policy"]._fields == (
        "id",
        "payout",
        "premium",
        "jrScr",
        "srScr",
        "lossProb",
        "purePremium",
        "ensuroCommission",
        "partnerCommission",
        "jrCoc",
        "srCoc",
        "riskModule",
        "start",
        "expiration",
    )

    with pytest.raises(TypeError):
        new_policy_nt = new_policy_nt_type.from_args({"riskModule": USDC_ADDR, "policy": 1})
    with pytest.raises(IndexError):
        new_policy_nt = new_policy_nt_type.from_args({"riskModule": USDC_ADDR, "policy": (1, 2, 3)})
    with pytest.raises(IndexError):
        new_policy_nt = new_policy_nt_type.from_args({"riskModule": USDC_ADDR, "policy": (1, 2, 3)})
    new_policy_nt = new_policy_nt_type.from_args(
        {
            "riskModule": USDC_ADDR,
            "policy": (
                1,  # id
                2,  # payout
                3,  # premium
                4,  # jrScr
                5,  # srScr
                6,  # lossProb
                7,  # purePremium
                8,  # ensuroCommission
                9,  # partnerCommission
                10,  # jrCoc
                11,  # srCoc
                OTHER_ADDR,  # riskModule
                13,  # start
                14,  # expiration
            ),
        }
    )
    assert new_policy_nt.policy.jrCoc == 10


def test_make_abi_namedtuple_with_underscore():
    transfer = _get_event(TRANSFER_WITH_UNDERSCORE, "Transfer")
    transfer_nt_type = types.make_abi_namedtuple("Transfer", transfer["inputs"])
    assert transfer_nt_type._fields == ("from_", "to", "value")
    transfer_nt = transfer_nt_type.from_args({"_from": USDC_ADDR, "_to": OTHER_ADDR, "_value": 1000000})
    assert len(transfer_nt) == 3
    assert isinstance(transfer_nt, tuple)
    assert transfer_nt["_from"] == USDC_ADDR
    assert transfer_nt["from_"] == USDC_ADDR
    assert transfer_nt.from_ == USDC_ADDR
    assert transfer_nt[0] == USDC_ADDR
    assert transfer_nt.to == OTHER_ADDR
    assert isinstance(transfer_nt.to, types.Address)
    assert transfer_nt.value == 1000000


def test_event_from_evt_data():
    transfer = _get_event(IERC20_ABI, "Transfer")
    transfer_nt_type = types.make_abi_namedtuple("Transfer", transfer["inputs"])
    chain = types.Chain(id=137, name="Polygon")

    block = types.Block(
        chain=chain,
        number=34530281,
        hash="0x81145f3e891ab54554d964f901f122635ba4b00e22066157c6cabb647f959506",
        timestamp=1666168181,
    )

    evt_data = {
        "transactionHash": HexBytes(SOME_HASH),
        "transactionIndex": 1,
        "address": HexBytes(USDC_ADDR),
        "logIndex": 123,
        "event": "Transfer",
        "args": {"from": USDC_ADDR, "to": OTHER_ADDR, "value": 12345},
    }
    evt = types.Event.from_event_data(evt_data, transfer_nt_type, block)
    assert evt.args.from_ == USDC_ADDR
    assert evt.args.to == OTHER_ADDR
    assert evt.args.value == 12345

    bad_tx = types.Tx(block=block, hash=SOME_HASH.replace("9", "6"), index=123)
    with pytest.raises(AssertionError):
        evt = types.Event.from_event_data(evt_data, transfer_nt_type, block, tx=bad_tx)

    good_tx = types.Tx(block=block, hash=SOME_HASH, index=123)
    other_evt = types.Event.from_event_data(evt_data, transfer_nt_type, block, tx=good_tx)
    assert other_evt.tx is good_tx


def test_event_with_string():
    role_label_evt = _get_event(AM_ABI, "RoleLabel")
    label_nt_type = types.make_abi_namedtuple("RoleLabel", role_label_evt["inputs"])
    chain = types.Chain(id=137, name="Polygon")

    block = types.Block(
        chain=chain,
        number=63995699,
        hash="0x65c9551dd699d24b8a927b2c41a4e9dece9e4de6e9a620d26701c0b1ea999eb0",
        timestamp=1730986025,
    )

    evt_data = {
        "transactionHash": HexBytes("0x1fb23d4c22a61b82c5f38479ae2f8e3b09f69ce9531aaa855968c307b2830d59"),
        "transactionIndex": 37,
        "address": HexBytes("0x52050109459781DaF99C2a63c6ED15D5ABDbc4c0"),
        "logIndex": 233,
        "event": "RoleLabel",
        "args": {"roleId": 201, "label": "SPO_BRIDGE23"},
    }

    evt = types.Event.from_event_data(evt_data, label_nt_type, block)
    assert evt.args.roleId == 201
    assert evt.args.label == "SPO_BRIDGE23"
