from eth_utils.crypto import keccak

from .types import Address, Hash


class TopicTransforms:
    @classmethod
    def topic_sig(cls, value, address_book):
        return Hash(keccak(text=value))

    @classmethod
    def topic_sig_list(cls, value, address_book):
        return [cls.topic_sig(v, address_book) for v in value]

    @classmethod
    def _address(cls, value, address_book) -> Address:
        try:
            return Address(value)  # In case is already an address
        except ValueError:
            address = address_book.name_to_addr(value)
            if address is None:
                raise RuntimeError(f"Address not found for name {value}")
            return address

    @classmethod
    def address(cls, value, address_book) -> Hash:
        addr: Address = cls._address(value, address_book)
        return Hash("0x" + "0" * 24 + addr[2:].lower())

    @classmethod
    def address_list(cls, value, address_book):
        return [cls.address(v, address_book) for v in value]

    @classmethod
    def do_transform(cls, raw_value, address_book):
        if "transform" not in raw_value:
            return raw_value["value"]
        transform = getattr(cls, raw_value["transform"])
        return transform(raw_value["value"], address_book)


def load_subscriptions(subscriptions_config, address_book):
    for name, filters in subscriptions_config.items():
        addresses = [address_book.name_to_addr(name) for name in filters.get("addresses", [])]
        try:
            unknown_address = addresses.index(None)
            raise RuntimeError(f"Address not found for name {filters['addresses'][unknown_address]}")
        except ValueError:
            pass  # All good, none is None

        topics = [TopicTransforms.do_transform(v, address_book) for v in filters.get("topics", [])]
        yield name, addresses, topics
