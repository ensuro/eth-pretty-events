import pytest
from eth_utils.crypto import keccak

from eth_pretty_events import address_book
from eth_pretty_events.event_subscriptions import TopicTransforms, load_subscriptions
from eth_pretty_events.types import Address, Hash

ADDRESSES = {
    "USDC": Address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    "NATIVE_USDC": Address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
    "ENSURO": Address("0xD74A28274C4B1a116aDd9857FC0E8F5e8fAC2497"),
}


@pytest.fixture
def addr_book():
    book = address_book.NameToAddrAddressBook(ADDRESSES)
    address_book.setup_default(book)
    return book


@pytest.fixture
def topic_transforms():
    return TopicTransforms()


def test_topic_sig(topic_transforms, addr_book):
    event = "Transfer"
    expected_hash = Hash(keccak(text=event))
    assert topic_transforms.topic_sig(event, addr_book) == expected_hash


def test_topic_sig_list(topic_transforms, addr_book):
    events = ["Deposit", "Withdraw"]
    expected_hashes = [Hash(keccak(text=v)) for v in events]
    assert topic_transforms.topic_sig_list(events, addr_book) == expected_hashes


def test_address_with_name(topic_transforms, addr_book):
    expected_address = Hash("0x" + "0" * 24 + ADDRESSES["USDC"][2:].lower())
    assert topic_transforms.address("USDC", addr_book) == expected_address


def test_address_with_name_not_found(topic_transforms, addr_book):
    name = "USDC_NATIVE"
    with pytest.raises(RuntimeError, match=f"Address not found for name {name}"):
        topic_transforms.address(name, addr_book)


def test_address_correct_addr(topic_transforms, addr_book):
    adresss = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    expected_address = Hash("0x" + "0" * 24 + adresss[2:].lower())
    assert topic_transforms.address("USDC", addr_book) == expected_address


def test_address_list(topic_transforms, addr_book):
    values = ["USDC", "NATIVE_USDC", "0xD74A28274C4B1a116aDd9857FC0E8F5e8fAC2497"]
    expected_hashes = [
        Hash("0x" + "0" * 24 + ADDRESSES["USDC"][2:].lower()),
        Hash("0x" + "0" * 24 + ADDRESSES["NATIVE_USDC"][2:].lower()),
        Hash("0x" + "0" * 24 + "0xD74A28274C4B1a116aDd9857FC0E8F5e8fAC2497"[2:].lower()),
    ]
    assert topic_transforms.address_list(values, addr_book) == expected_hashes


def test_do_transform(topic_transforms, addr_book):

    raw_value = {"transform": "topic_sig", "value": "Transfer"}
    expected_hash = Hash(keccak(text="Transfer"))
    assert topic_transforms.do_transform(raw_value, addr_book) == expected_hash

    adresss = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    raw_value = {"transform": "address", "value": adresss}
    expected_address = Hash("0x" + "0" * 24 + adresss[2:].lower())
    assert topic_transforms.do_transform(raw_value, addr_book) == expected_address

    raw_value = {"value": "Deposit"}
    result = topic_transforms.do_transform(raw_value, addr_book)
    assert result == "Deposit"


def test_load_subscriptions_empty(addr_book):
    subscriptions_config = {}
    subscriptions = list(load_subscriptions(subscriptions_config, addr_book))
    assert subscriptions == []


def test_load_subscriptions_valid(addr_book):
    subscriptions_config = {
        "subscription_topic_sig": {"addresses": ["USDC"], "topics": [{"transform": "topic_sig", "value": "Transfer"}]},
        "subscription_address": {
            "addresses": ["ENSURO"],
            "topics": [{"transform": "address", "value": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"}],
        },
        "subscription_without_transform": {"addresses": ["NATIVE_USDC"], "topics": [{"value": "Deposit"}]},
    }
    subscriptions = list(load_subscriptions(subscriptions_config, addr_book))

    expected_address_1 = [ADDRESSES["USDC"]]
    expected_topic_1 = Hash(keccak(text="Transfer"))
    expected_address_2 = [ADDRESSES["ENSURO"]]
    expected_address_transform = Hash("0x" + "0" * 24 + "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"[2:].lower())
    expected_address_3 = [ADDRESSES["NATIVE_USDC"]]
    expected_topic_3 = "Deposit"

    assert subscriptions == [
        ("subscription_topic_sig", expected_address_1, [expected_topic_1]),
        ("subscription_address", expected_address_2, [expected_address_transform]),
        ("subscription_without_transform", expected_address_3, [expected_topic_3]),
    ]


def test_load_subscriptions_unknown_address(addr_book):
    name = "non_existing"
    subscriptions_config = {
        "Subscription1": {"addresses": [name], "topics": [{"transform": "topic_sig", "value": "Transfer"}]}
    }
    with pytest.raises(RuntimeError, match=f"Address not found for name {name}"):
        list(load_subscriptions(subscriptions_config, addr_book))
