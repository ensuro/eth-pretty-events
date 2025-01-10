from decimal import Decimal

import pytest
from eth_utils import keccak, to_checksum_address
from web3.constants import ADDRESS_ZERO

from eth_pretty_events import address_book, event_filter
from eth_pretty_events.types import Address

from . import factories

ADDRESSES = {
    "USDC": Address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    "NATIVE_USDC": Address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
    "ENSURO": Address("0xD74A28274C4B1a116aDd9857FC0E8F5e8fAC2497"),
}


@pytest.fixture(autouse=True)
def addr_book():
    address_book.setup_default(address_book.NameToAddrAddressBook(ADDRESSES))


def test_shortcut_address():
    usdc_filter = event_filter.EventFilter.from_config(dict(address="USDC"))
    assert isinstance(usdc_filter, event_filter.AddressEventFilter)
    assert usdc_filter.value == Address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

    assert usdc_filter.filter(factories.Event(address=ADDRESSES["USDC"]))
    assert not usdc_filter.filter(factories.Event(address=ADDRESSES["NATIVE_USDC"]))


def test_shortcut_name():
    transfer_filter = event_filter.EventFilter.from_config(dict(name="Transfer"))
    assert isinstance(transfer_filter, event_filter.NameEventFilter)

    assert transfer_filter.filter(factories.Event(name="Transfer"))
    assert not transfer_filter.filter(factories.Event(name="OtherEvent"))


def test_str_to_addr_not_in_book():
    name = "not_found_name"
    with pytest.raises(RuntimeError, match=f"Name {name} not found"):
        event_filter._str_to_addr(name)


def test_known_address_book_filter_true():
    known_address_filter = event_filter.EventFilter.from_config(dict(filter_type="known_address", is_known=True))
    event = factories.Event(address=ADDRESSES["USDC"])

    assert known_address_filter.filter(event)


def test_known_address_book_filter_false():
    known_address_filter = event_filter.EventFilter.from_config(dict(filter_type="known_address", is_known=False))
    event = factories.Event(address=Address(ADDRESS_ZERO))
    assert known_address_filter.filter(event)


def test_arg_exists_event_filter():
    arg_exists_filter = event_filter.EventFilter.from_config(dict(filter_type="arg_exists", arg_name="existent"))
    event_with_arg = factories.Event(args={"existent": "value"})
    event_without_arg = factories.Event(args={})

    assert arg_exists_filter.filter(event_with_arg)
    assert not arg_exists_filter.filter(event_without_arg)


def test_read_template_rules():
    template_rules = {"rules": [{"template": "test_template", "match": [{"name": "Transfer"}, {"address": "USDC"}]}]}

    rules = event_filter.read_template_rules(template_rules)
    assert len(rules) == 1
    assert rules[0].template == "test_template"
    assert isinstance(rules[0].match, event_filter.AndEventFilter)

    template_rules_single_match = {
        "rules": [{"template": "test_template_single_match", "match": [{"name": "Transfer"}]}]
    }

    rules_single_match = event_filter.read_template_rules(template_rules_single_match)
    assert len(rules_single_match) == 1
    assert rules_single_match[0].template == "test_template_single_match"
    assert isinstance(rules_single_match[0].match, event_filter.NameEventFilter)


def test_find_template():
    template_rules = {"rules": [{"template": "test_template", "match": [{"name": "Transfer"}, {"address": "USDC"}]}]}

    rules = event_filter.read_template_rules(template_rules)
    transfer = factories.Event(name="Transfer", address=ADDRESSES["USDC"])
    template = event_filter.find_template(rules, transfer)
    assert template == "test_template"

    new_policy = factories.Event(name="NewPolicy", address=ADDRESSES["USDC"])
    template = event_filter.find_template(rules, new_policy)
    assert template is None


def test_read_template_rules_invalid_config():
    template_rules = {"rules": [{"template": "test_template", "match": [{}]}]}

    with pytest.raises(RuntimeError, match="Invalid filter config"):
        event_filter.read_template_rules(template_rules)


def test_and_filter():
    config = {"and": [{"name": "Transfer"}, {"address": "USDC"}]}
    and_filter = event_filter.EventFilter.from_config(config)
    assert isinstance(and_filter, event_filter.AndEventFilter)

    transfer_usdc_event = factories.Event(name="Transfer", address=ADDRESSES["USDC"])
    other_event = factories.Event(name="OtherEvent", address=ADDRESSES["USDC"])

    assert and_filter.filter(transfer_usdc_event)
    assert not and_filter.filter(other_event)


def test_or_filter():
    config = {"or": [{"name": "Transfer"}, {"address": "USDC"}]}
    or_filter = event_filter.EventFilter.from_config(config)
    assert isinstance(or_filter, event_filter.OrEventFilter)

    transfer_usdc_event = factories.Event(name="Transfer", address=ADDRESSES["USDC"])
    transfer_other_event = factories.Event(name="Transfer", address=ADDRESSES["NATIVE_USDC"])
    other_usdc_event = factories.Event(name="OtherEvent", address=ADDRESSES["USDC"])

    assert or_filter.filter(transfer_usdc_event)
    assert or_filter.filter(transfer_other_event)
    assert or_filter.filter(other_usdc_event)


def test_not_filter():
    config = {"not": {"name": "Transfer"}}
    not_filter = event_filter.EventFilter.from_config(config)
    assert isinstance(not_filter, event_filter.NotEventFilter)

    transfer_event = factories.Event(name="Transfer")
    other_event = factories.Event(name="OtherEvent")

    assert not not_filter.filter(transfer_event)
    assert not_filter.filter(other_event)


def test_invalid_filter_config():
    config = {"invalid": {}}
    with pytest.raises(RuntimeError, match=f"Invalid filter config {config}"):
        event_filter.EventFilter.from_config(config)


def test_register_duplicate_filter_type():
    type_register = "test_register"
    event_filter.EventFilter.register(type_register)(event_filter.AddressEventFilter)

    # Here we try to register another filter with the same type
    with pytest.raises(ValueError, match=f"Duplicate filter type {type_register}"):
        event_filter.EventFilter.register(type_register)(event_filter.NameEventFilter)


def test_transform_amount():
    assert event_filter.transform_amount("1.5") == int(Decimal("1.5") * Decimal(10**6))
    assert event_filter.transform_amount("0") == 0
    assert event_filter.transform_amount("123456.789") == int(Decimal("123456.789") * Decimal(10**6))


def test_transform_wad():
    assert event_filter.transform_wad("1.5") == int(Decimal("1.5") * Decimal(10**18))
    assert event_filter.transform_wad("0") == 0
    assert event_filter.transform_wad("123456.789") == int(Decimal("123456.789") * Decimal(10**18))


def test_transform_keccak():
    assert event_filter.transform_keccak("example") == "0x" + keccak(text="example").hex()
    assert event_filter.transform_keccak("") == "0x" + keccak(text="").hex()
    assert event_filter.transform_keccak("another_string") == "0x" + keccak(text="another_string").hex()


def test_transform_address():

    result = event_filter.transform_address("USDC")
    expected_address = to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
    assert result == expected_address
    non_existing_name = "non_existing"
    with pytest.raises(RuntimeError, match=f"Address for name {non_existing_name} not found"):
        event_filter.transform_address(non_existing_name)


@pytest.mark.parametrize(
    "operator, arg_value, event_value, expected, transform, transform_fn",
    [
        ("eq", "1.5", "1.5", True, "amount", event_filter.transform_amount),
        ("ne", "1.5", "2.0", True, "wad", event_filter.transform_wad),
        ("lt", "1.5", "2.0", False, "amount", event_filter.transform_amount),
        ("le", "1.5", "1.5", True, "wad", event_filter.transform_wad),
        ("le", "1.5", "2.0", False, "amount", event_filter.transform_amount),
        ("gt", "1.5", "1.0", False, "wad", event_filter.transform_wad),
        ("ge", "1.5", "1.5", True, "amount", event_filter.transform_amount),
        ("ge", "1.5", "1.0", False, "wad", event_filter.transform_wad),
    ],
)
def test_arg_event_filter_with_transform(operator, arg_value, event_value, expected, transform, transform_fn):
    arg_filter = event_filter.EventFilter.from_config(
        dict(filter_type="arg", arg_name="value", arg_value=arg_value, operator=operator, transform=transform)
    )
    event = factories.Event(args={"value": transform_fn(event_value)})
    assert arg_filter.filter(event) == expected

    # Nested argument
    nested_arg_filter = event_filter.EventFilter.from_config(
        dict(filter_type="arg", arg_name="parent.child", arg_value=arg_value, operator=operator, transform=transform)
    )
    nested_event = factories.Event(args={"parent": {"child": transform_fn(event_value)}})
    assert nested_arg_filter.filter(nested_event) == expected


def test_arg_exists_event_filter_with_nested_args():
    arg_exists_filter = event_filter.EventFilter.from_config(dict(filter_type="arg_exists", arg_name="parent.child"))

    event_with_nested_arg = factories.Event(args={"parent": {"child": "value"}})
    assert arg_exists_filter.filter(event_with_nested_arg)

    event_without_nested_arg = factories.Event(args={"parent": {}})
    assert not arg_exists_filter.filter(event_without_nested_arg)

    event_with_arg = factories.Event(args={})
    assert not arg_exists_filter.filter(event_with_arg)

    event_with_different_nested_arg = factories.Event(args={"parent": {"other_child": "value"}})
    assert not arg_exists_filter.filter(event_with_different_nested_arg)


def test_known_address_book_arg_event_filter():
    in_addr_book_arg_filter = event_filter.EventFilter.from_config(
        dict(filter_type="known_address_arg", arg_name="user", arg_value=True)
    )

    assert isinstance(in_addr_book_arg_filter, event_filter.InAddressBookArgEventFilter)
    assert in_addr_book_arg_filter.arg_value is True

    event1 = factories.Event(args={"user": ADDRESSES["USDC"]})
    assert in_addr_book_arg_filter.filter(event1)

    event2 = factories.Event(args={"user": ADDRESS_ZERO})
    assert not in_addr_book_arg_filter.filter(event2)


def test_true_event_filter():
    true_filter = event_filter.EventFilter.from_config(dict(filter_type="true"))
    assert isinstance(true_filter, event_filter.TrueEventFilter)

    event1 = factories.Event(name="Event1", address=ADDRESSES["USDC"])
    event2 = factories.Event(name="Event2", address=ADDRESSES["NATIVE_USDC"])

    assert true_filter.filter(event1)
    assert true_filter.filter(event2)


def test_get_topic0_with_event():
    event_string = "Transfer(address from, address to, uint256 value)"
    topic_filter = event_filter.TopicEventFilter(event_string)

    event = factories.Event(name="Transfer")
    non_matching_event = factories.Event(name="NewPolicy")

    assert topic_filter.filter(event)
    assert not topic_filter.filter(non_matching_event)


def test_get_topic0_with_event_whitespaces():
    event_string = "Transfer(address   from,   address   to, uint256   value)"
    topic_filter = event_filter.TopicEventFilter(event_string)

    event = factories.Event(name="Transfer")

    assert topic_filter.filter(event)


def test_get_topic0_with_hash():
    event_string = "Transfer(address from, address to, uint256 value)"
    expected_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    assert event_filter.get_topic0(event_string) == expected_topic
