from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from eth_pretty_events.address_book import get_default as get_addr_book
from eth_pretty_events.types import Address, Event


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


@EventFilter.register("address")
class AddressEventFilter(EventFilter):
    value: Address

    def __init__(self, value: str):
        self.value = _str_to_addr(value)

    def filter(self, evt: Event) -> bool:
        return evt.address == self.value


@EventFilter.register("in_address")
class InAddressBookEventFilter(EventFilter):
    value: bool

    def __init__(self, value: bool):
        self.value = value

    def filter(self, evt: Event) -> bool:
        return get_addr_book().has_addr(evt.address) == self.value


@EventFilter.register("name")
class NameEventFilter(EventFilter):
    value: str

    def __init__(self, value: str):
        self.value = value

    def filter(self, evt: Event) -> bool:
        return evt.name == self.value


@EventFilter.register("arg")
class ArgEventFilter(EventFilter):
    def __init__(self, arg_name: str, arg_value: Any):
        self.arg_name = arg_name
        self.arg_value = arg_value

    def _get_arg(self, evt: Event):
        arg_path = self.arg_name.split(".")
        ret = evt.args[arg_path[0]]
        for arg_step in arg_path[1:]:
            ret = ret[arg_step]
        return ret

    def filter(self, evt: Event) -> bool:
        return self._get_arg(evt) == self.arg_value


@EventFilter.register("address_arg")
class AddressArgEventFilter(ArgEventFilter):
    def __init__(self, arg_name: str, arg_value: Any):
        return super().__init__(arg_name, _str_to_addr(arg_value))


@EventFilter.register("in_address_arg")
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


def read_template_rules(template_rules: dict) -> Sequence[TemplateRule]:
    rules = template_rules["rules"]
    ret: Sequence[TemplateRule] = []

    for rule in rules:
        filters = [EventFilter.from_config(f) for f in rule["match"]]
        if len(filters) == 1:
            filter = filters[0]
        else:
            filter = AndEventFilter(filters)
        ret.append(TemplateRule(template=rule["template"], match=filter))
    return ret


def find_template(template_rules: Sequence[TemplateRule], event: Event) -> Optional[str]:
    for rule in template_rules:
        if rule.match.filter(event):
            return rule.template
    return None