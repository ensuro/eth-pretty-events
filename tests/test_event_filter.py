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
