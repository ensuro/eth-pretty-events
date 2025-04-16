import operator
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, List, Optional

from eth_utils import keccak

from eth_pretty_events.address_book import get_default as get_addr_book
from eth_pretty_events.types import Address, Event, Hash


class EventFilter(ABC):
    FILTER_REGISTRY = {}
    use_address_book = False

    @abstractmethod
    def filter(self, evt: Event) -> bool: ...

    @classmethod
    def from_config(cls, config: dict) -> "EventFilter":
        if "filter_type" in config:
            config = dict(config)
            filter_type = config.pop("filter_type")
            filter_cls = cls.FILTER_REGISTRY[filter_type]
            return filter_cls(**config)
        elif len(config) == 1:
            # Shortcut for some common filters
            key = next(iter(config))
            if key == "address":
                return AddressEventFilter(config[key])
            elif key in ("name", "event"):
                return NameEventFilter(config[key])
            elif key in ("or", "and"):
                filters: Sequence[EventFilter] = [cls.from_config(f) for f in config[key]]
                return (AndEventFilter if key == "and" else OrEventFilter)(filters)
            elif key in ("not"):
                return NotEventFilter(cls.from_config(config[key]))
            else:
                raise RuntimeError(f"Invalid filter config {config}")
        else:
            raise RuntimeError(
                f"Invalid filter config {config} must include 'filter_type' of use some of the shortcuts"
            )

    @classmethod
    def register(cls, type: str):
        def decorator(subclass):
            if type in cls.FILTER_REGISTRY:
                raise ValueError(f"Duplicate filter type {type}")
            cls.FILTER_REGISTRY[type] = subclass
            return subclass

        return decorator


def _str_to_addr(value: str) -> Address:
    try:
        return Address(value)
    except ValueError:
        # is not an address, it's a name
        address_value = get_addr_book().name_to_addr(value)
        if address_value is None:
            raise RuntimeError(f"Name {value} not found")
        else:
            return address_value


def transform_amount(val):
    return int(Decimal(val) * Decimal(10**6))


def transform_wad(val):
    return int(Decimal(val) * Decimal(10**18))


def transform_keccak(val: str) -> str:
    return "0x" + keccak(text=val).hex()


def transform_address(val: str) -> Address:
    address = get_addr_book().name_to_addr(val)
    if address is None:
        raise RuntimeError(f"Address for name {val} not found")
    return address


def get_topic0(event_string: str) -> str:
    # Remove parameter names
    normalized = re.sub(r"(indexed\s+)?([a-zA-Z0-9\[\]]+)\s+[a-zA-Z0-9_]+(?=[,)])", r"\2", event_string)

    # Remove whitespace
    normalized = re.sub(r"\s+", "", normalized)

    # WARNING: doesn't work with struct arguments unless normalized
    # get_topic0("NewPolicy(address, (uint256, uint256, uint256, uint256, uint256, uint256,
    #                                 uint256, uint256, uint256, uint256, uint256, address, uint40, uint40)
    #                      )") == "0x38f420e3792044ba61536a1f83956eefc878b3fb09a7d4a28790f05b6a3eaf3b"

    return transform_keccak(normalized)


TRANSFORMS = {
    "amount": transform_amount,
    "wad": transform_wad,
    "keccak": transform_keccak,
    "address": transform_address,
}


@EventFilter.register("address")
class AddressEventFilter(EventFilter):
    value: Address

    def __init__(self, value: str):
        self.value = _str_to_addr(value)

    def filter(self, evt: Event) -> bool:
        return evt.address == self.value


@EventFilter.register("known_address")
class InAddressBookEventFilter(EventFilter):
    is_known: bool

    def __init__(self, is_known: bool):
        self.is_known = is_known

    def filter(self, evt: Event) -> bool:
        return get_addr_book().has_addr(evt.address) == self.is_known


@EventFilter.register("name")
class NameEventFilter(EventFilter):
    value: str

    def __init__(self, value: str):
        self.value = value

    def filter(self, evt: Event) -> bool:
        return evt.name == self.value


@EventFilter.register("topic")
class TopicEventFilter(EventFilter):
    value: Hash

    def __init__(self, value: str):
        try:
            self.value = Hash(value)
        except ValueError:
            # The value is
            self.value = Hash(get_topic0(value))

    def filter(self, evt: Event) -> bool:
        return evt.topic == self.value


@EventFilter.register("arg")
class ArgEventFilter(EventFilter):
    OPERATORS = {
        "eq": operator.eq,
        "lt": operator.lt,
        "gt": operator.gt,
        "le": operator.le,
        "ge": operator.ge,
        "ne": operator.ne,
    }

    def __init__(self, arg_name: str, arg_value: Any = None, operator: str = "eq", transform: str = None):
        self.arg_name = arg_name
        self.arg_value = TRANSFORMS[transform](arg_value) if transform is not None else arg_value
        self.operator = self.OPERATORS[operator]

    def _get_arg(self, evt: Event):
        arg_path = self.arg_name.split(".")
        ret = evt.args[arg_path[0]]
        for arg_step in arg_path[1:]:
            ret = ret[arg_step]
        return ret

    def filter(self, evt: Event) -> bool:
        arg_value = self._get_arg(evt)
        return self.operator(arg_value, self.arg_value)


@EventFilter.register("arg_exists")
class ArgExistsEventFilter(EventFilter):
    def __init__(self, arg_name: str):
        self.arg_name = arg_name

    def _get_arg(self, evt: Event):
        arg_path = self.arg_name.split(".")
        try:
            ret = evt.args[arg_path[0]]
        except KeyError:
            return None
        for arg_step in arg_path[1:]:
            try:
                ret = ret[arg_step]
            except KeyError:
                return None
        return ret

    def filter(self, evt: Event) -> bool:
        return self._get_arg(evt) is not None


@EventFilter.register("known_address_arg")
class InAddressBookArgEventFilter(ArgEventFilter):
    def filter(self, evt: Event) -> bool:
        return get_addr_book().has_addr(self._get_arg(evt)) == self.arg_value


@EventFilter.register("not")
class NotEventFilter(EventFilter):
    negated_filter: EventFilter

    def __init__(self, negated_filter: EventFilter):
        self.negated_filter = negated_filter

    def filter(self, evt: Event) -> bool:
        return not self.negated_filter.filter(evt)


@EventFilter.register("and")
class AndEventFilter(EventFilter):
    filters: Sequence[EventFilter]

    def __init__(self, filters: Sequence[EventFilter]):
        self.filters = filters

    def filter(self, evt: Event) -> bool:
        return not any(f.filter(evt) is False for f in self.filters)


@EventFilter.register("or")
class OrEventFilter(EventFilter):
    filters: Sequence[EventFilter]

    def __init__(self, filters: Sequence[EventFilter]):
        self.filters = filters

    def filter(self, evt: Event) -> bool:
        return any(f.filter(evt) for f in self.filters)


@EventFilter.register("true")
class TrueEventFilter(EventFilter):
    def filter(self, evt: Event) -> bool:
        return True


@dataclass
class TemplateRule:
    template: str
    match: EventFilter
    tags: List[str] = field(default_factory=list)


def read_template_rules(template_rules: dict) -> Sequence[TemplateRule]:
    rules = template_rules["rules"]
    ret: Sequence[TemplateRule] = []

    for rule in rules:
        filters = [EventFilter.from_config(f) for f in rule["match"]]
        if len(filters) == 1:
            filter = filters[0]
        else:
            filter = AndEventFilter(filters)
        tags = rule.get("tags", [])
        ret.append(TemplateRule(template=rule["template"], match=filter, tags=tags))
    return ret


def find_template(template_rules: Sequence[TemplateRule], event: Event) -> Optional[str]:
    for rule in template_rules:
        if rule.match.filter(event):
            return rule.template
    return None
