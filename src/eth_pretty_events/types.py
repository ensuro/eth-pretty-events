import keyword
import re
import types
from collections import namedtuple
from dataclasses import dataclass
from typing import (
    Any,
    ClassVar,
    Dict,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Type,
    Union,
)

from eth_typing import ABIComponent
from eth_utils.abi import event_abi_to_log_topic
from eth_utils.address import is_checksum_address, to_checksum_address
from hexbytes import HexBytes
from web3.types import EventData


class Address(str):
    def __new__(cls, value: Union[HexBytes, str]):
        if isinstance(value, HexBytes):
            value = value.hex()
            if len(value) != 40:
                raise ValueError(f"'0x{value}' is not a valid address")
            value = to_checksum_address(value)
        elif isinstance(value, str) and value == value.lower():
            value = to_checksum_address(value)
        elif not is_checksum_address(value):
            raise ValueError(f"'{value}' is not a valid address")

        return str.__new__(cls, value)


class Hash(str):
    def __new__(cls, value: Union[HexBytes, str, bytes]):
        if isinstance(value, HexBytes) or isinstance(value, bytes):
            value = "0x" + value.hex()
            if len(value) != 66:
                raise ValueError(f"'{value}' is not a valid hash")
        elif isinstance(value, str):
            if len(value) == 64 and not value.startswith("0x"):
                value = "0x" + value
            elif len(value) != 66:
                raise ValueError(f"'{value}' is not a valid hash")
            if value != value.lower():
                value = value.lower()
            if value[0:2] != "0x":
                raise ValueError(f"'{value}' is not a valid hash")
            else:
                try:
                    int(value, 16)
                except ValueError:
                    raise ValueError(f"'{value}' is not a valid hash")
        else:
            raise ValueError("Only HexBytes, bytes or str accepted")

        return str.__new__(cls, value)


@dataclass
class Chain:
    id: int
    name: str
    metadata: Optional[Dict] = None


@dataclass
class Block:
    hash: Hash
    timestamp: int
    number: int
    chain: Chain

    def __hash__(self) -> int:
        return hash(self.hash)


@dataclass
class Tx:
    hash: Hash
    index: int
    block: Block


@dataclass
class Event:
    address: Address
    args: NamedTuple
    tx: Tx
    name: str
    log_index: int

    @classmethod
    def from_event_data(cls, evt: EventData, args_nt: Type["ArgsTuple"], block: Block, tx: Optional[Tx] = None):
        if tx is not None:
            assert tx.hash == Hash(evt["transactionHash"])
        else:
            tx = Tx(
                hash=Hash(evt["transactionHash"]),
                index=evt["transactionIndex"],
                block=block,
            )
        return cls(
            address=Address(evt["address"]),
            args=args_nt.from_args(evt["args"]),
            log_index=evt["logIndex"],
            tx=tx,
            name=evt["event"],
        )

    @property
    def topic(self) -> Hash:
        return Hash(event_abi_to_log_topic({"inputs": self.args._components, "name": self.name, "type": "event"}))


INT_TYPE_REGEX = re.compile(r"int\d+|uint\d+")
BYTES_TYPE_REGEX = re.compile(r"bytes\d+")
ARRAY_TYPE_REGEX = re.compile(r"(.+)\[\]$")


def arg_from_solidity_type(type_: str) -> Type:
    if type_ == "string":
        return str
    if type_ == "bool":
        return bool
    if ARRAY_TYPE_REGEX.match(type_):
        base_type = ARRAY_TYPE_REGEX.match(type_).group(1)
        return lambda x: [arg_from_solidity_type(base_type)(item) for item in x]
    if INT_TYPE_REGEX.match(type_):
        return int
    if type_ == "bytes32":
        return Hash
    if type_ == "bytes":
        return lambda x: x.hex()
    if BYTES_TYPE_REGEX.match(type_):
        # TODO: handle bytes4 or other special cases
        return lambda x: x.hex()
    if type_ == "address":
        return Address
    raise RuntimeError(f"Unsupported type {type_}")


def sanitize_field_name(field_name):
    if field_name.startswith("_"):
        return sanitize_field_name(field_name.lstrip("_"))
    if field_name in keyword.kwlist:
        return f"{field_name}_"
    else:
        return field_name


class ArgsTuple(Protocol):
    @classmethod
    def from_args(cls, args) -> "ArgsTuple": ...

    def __getitem__(self, key: Union[str, int]): ...

    _components: ClassVar[Sequence[ABIComponent]]

    _fields: ClassVar[Sequence[str]]

    @classmethod
    def _abi_fields(cls) -> Sequence[str]: ...

    _tuple_components: ClassVar[Dict[str, Type["ArgsTuple"]]]

    def _asdict(self) -> Dict[str, Any]: ...


class NamedTupleDictMixin:
    """Class to adapt a named tuple to behave as a dict"""

    def __getitem__(self: ArgsTuple, key):
        if isinstance(key, str):
            nt_asdict = self._asdict()
            if key in nt_asdict:
                return nt_asdict[key]
            else:
                return nt_asdict[sanitize_field_name(key)]
        return super().__getitem__(key)


class ABITupleMixin(NamedTupleDictMixin):

    @classmethod
    def from_args(cls: Type[ArgsTuple], args) -> ArgsTuple:
        field_values = []
        for i, (field, component) in enumerate(zip(cls._fields, cls._components)):
            assert sanitize_field_name(component["name"]) == field
            if isinstance(args, (tuple, list)):
                value = args[i]
            else:
                value = args[component["name"]]
            if component["type"] == "tuple":
                value = cls._tuple_components[field].from_args(value)
            else:
                value = arg_from_solidity_type(component["type"])(value)
            field_values.append(value)
        return cls(*field_values)

    @classmethod
    def _abi_fields(cls: Type[ArgsTuple]):
        return [comp["name"] for comp in cls._components]

    @classmethod
    def _field_abi(cls: Type[ArgsTuple], field: str):
        return [comp for comp in cls._components if field == comp["name"]][0]


def make_abi_namedtuple(name, components) -> Type[ArgsTuple]:
    attributes = [comp["name"] for comp in components]
    attributes = map(sanitize_field_name, attributes)

    nt = namedtuple(name, attributes)
    ret = types.new_class(name, bases=(ABITupleMixin, nt))
    ret._components = components
    ret._tuple_components = {}
    for tuple_comp in filter(lambda comp: comp["type"] == "tuple", components):
        ret._tuple_components[tuple_comp["name"]] = make_abi_namedtuple(
            f"{name}_{tuple_comp['name']}", tuple_comp["components"]
        )
    return ret
