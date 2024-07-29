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
from eth_utils.address import is_checksum_address, to_checksum_address
from hexbytes import HexBytes
from web3.types import EventData


class Address(str):
    def __new__(cls, value: Union[HexBytes, str]):
        if isinstance(value, HexBytes):
            value = value.hex()
            if len(value) != 42:
                raise ValueError(f"'{value}' is not a valid address")
            value = to_checksum_address(value)
        elif isinstance(value, str) and value == value.lower():
            value = to_checksum_address(value)
        elif not is_checksum_address(value):
            raise ValueError(f"'{value}' is not a valid address")

        return str.__new__(cls, value)


class Hash(str):
    def __new__(cls, value: Union[HexBytes, str, bytes]):
        if isinstance(value, HexBytes):
            value = value.hex()
            if len(value) != 66:
                raise ValueError(f"'{value}' is not a valid hash")
        elif isinstance(value, bytes):
            value = "0x" + value.hex()
            if len(value) != 66:
                raise ValueError(f"'{value}' is not a valid hash")
        elif isinstance(value, str):
            if len(value) != 66:
                raise ValueError(f"'{value}' is not a valid hash")
            if value != value.lower():
                value = value.lower()
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
                hash=Hash(evt["transactionHash"].hex()),
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


INT_TYPE_REGEX = re.compile(r"int\d+|uint\d+")
BYTES_TYPE_REGEX = re.compile(r"bytes\d+")


def arg_from_solidity_type(type_: str) -> Type:
    if type_ == "bool":
        return bool
    if INT_TYPE_REGEX.match(type_):
        return int
    if type_ == "bytes32":
        return Hash
    if BYTES_TYPE_REGEX.match(type_):
        # TODO: handle bytes4 or other special cases
        return lambda x: x.hex()
    if type_ == "address":
        return Address
    raise RuntimeError(f"Unsupported type {type_}")


def rename_keyword(field_name):
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
                return nt_asdict[rename_keyword(key)]
        return super().__getitem__(key)


class ABITupleMixin(NamedTupleDictMixin):

    @classmethod
    def from_args(cls: Type[ArgsTuple], args) -> ArgsTuple:
        field_values = []
        for i, (field, component) in enumerate(zip(cls._fields, cls._components)):
            assert rename_keyword(component["name"]) == field
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
    attributes = map(rename_keyword, attributes)

    nt = namedtuple(name, attributes)
    ret = types.new_class(name, bases=(ABITupleMixin, nt))
    ret._components = components
    ret._tuple_components = {}
    for tuple_comp in filter(lambda comp: comp["type"] == "tuple", components):
        ret._tuple_components[tuple_comp["name"]] = make_abi_namedtuple(
            f"{name}_{tuple_comp['name']}", tuple_comp["components"]
        )
    return ret