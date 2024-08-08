import pytest

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
