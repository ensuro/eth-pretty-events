from random import randint

import factory
from factory.faker import Faker
from faker.providers import BaseProvider

from eth_pretty_events import types


class EthProvider(BaseProvider):
    """
    A Provider for Ethereum related data
    >>> from faker import Faker
    >>> fake = Faker()
    >>> fake.add_provider(EthProvider)
    """

    def eth_address(self):
        ret = randint(0, 2**160 - 1)
        return types.Address(f"0x{ret:040x}")

    def eth_hash(self):
        ret = randint(0, 2**256 - 1)
        return types.Hash(f"0x{ret:064x}")


Faker.add_provider(EthProvider)


class Chain(factory.Factory):
    class Meta:
        model = types.Chain

    id = 137
    name = "Polygon"


class Block(factory.Factory):
    class Meta:
        model = types.Block

    chain = factory.SubFactory(Chain)
    number = factory.Sequence(lambda n: n + 100000)
    hash = factory.Faker("eth_hash")
    timestamp = factory.Sequence(lambda n: n + 1722853708)


class Tx(factory.Factory):
    class Meta:
        model = types.Tx

    block = factory.SubFactory(Block)
    hash = factory.Faker("eth_hash")
    index = factory.Sequence(lambda n: n)


class Hash(factory.Factory):
    class Meta:
        model = types.Hash

    value = factory.Faker("eth_hash")


EVENT_NAMES = ["Transfer", "Approval", "NewPolicy"]

TRANSFER_ABI = [
    {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
    {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
    {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"},
]

APPROVAL_ABI = [
    {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
    {"indexed": True, "internalType": "address", "name": "spender", "type": "address"},
    {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"},
]

NEW_POLICY_ABI = [
    {"indexed": True, "internalType": "contract IRiskModule", "name": "riskModule", "type": "address"},
    {
        "components": [
            {"internalType": "uint256", "name": "id", "type": "uint256"},
            {"internalType": "uint256", "name": "payout", "type": "uint256"},
            {"internalType": "uint256", "name": "premium", "type": "uint256"},
            {"internalType": "uint256", "name": "jrScr", "type": "uint256"},
            {"internalType": "uint256", "name": "srScr", "type": "uint256"},
            {"internalType": "uint256", "name": "lossProb", "type": "uint256"},
            {"internalType": "uint256", "name": "purePremium", "type": "uint256"},
            {"internalType": "uint256", "name": "ensuroCommission", "type": "uint256"},
            {"internalType": "uint256", "name": "partnerCommission", "type": "uint256"},
            {"internalType": "uint256", "name": "jrCoc", "type": "uint256"},
            {"internalType": "uint256", "name": "srCoc", "type": "uint256"},
            {"internalType": "contract IRiskModule", "name": "riskModule", "type": "address"},
            {"internalType": "uint40", "name": "start", "type": "uint40"},
            {"internalType": "uint40", "name": "expiration", "type": "uint40"},
        ],
        "indexed": False,
        "internalType": "struct Policy.PolicyData",
        "name": "policy",
        "type": "tuple",
    },
]


class TransferArgs(factory.Factory):
    class Meta:
        model = types.make_abi_namedtuple("Transfer", TRANSFER_ABI)

    from_ = factory.Faker("eth_address")
    to = factory.Faker("eth_address")
    value = factory.Faker("pyint", min_value=10**6, step=1000, max_value=10**20)


class ApprovalArgs(factory.Factory):
    class Meta:
        model = types.make_abi_namedtuple("Approval", APPROVAL_ABI)

    owner = factory.Faker("eth_address")
    spender = factory.Faker("eth_address")
    value = factory.Faker("pyint", min_value=10**6, max_value=10**20, step=1000)


new_policy_args = types.make_abi_namedtuple("NewPolicy", NEW_POLICY_ABI)


class PolicyArgs(factory.Factory):
    class Meta:
        model = new_policy_args._tuple_components["policy"]

    id = factory.Faker("pyint", min_value=2**160, max_value=2**256 - 1)
    payout = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    premium = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    jrScr = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    srScr = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    lossProb = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    purePremium = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    ensuroCommission = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    partnerCommission = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    jrCoc = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    srCoc = factory.Faker("pyint", min_value=10**7, step=10**4, max_value=10**20)
    riskModule = factory.Faker("eth_address")
    start = factory.Faker("pyint", min_value=1722879647, max_value=1739999999)
    expiration = factory.Faker("pyint", min_value=1722879647, max_value=1739999999)


class NewPolicyArgs(factory.Factory):
    class Meta:
        model = new_policy_args

    riskModule = factory.Faker("eth_address")
    policy = factory.SubFactory(PolicyArgs)


class Event(factory.Factory):
    class Meta:
        model = types.Event

    tx = factory.SubFactory(Tx)
    address = factory.Faker("eth_address")
    name = factory.Sequence(lambda n: EVENT_NAMES[n % len(EVENT_NAMES)])
    log_index = factory.Sequence(lambda n: n)

    @factory.lazy_attribute
    def args(self):
        if self.name == "Transfer":
            return TransferArgs()
        elif self.name == "Approval":
            return ApprovalArgs()
        elif self.name == "NewPolicy":
            return NewPolicyArgs()
