from eth_pretty_events import types

from . import factories


def test_arg_factories():
    policy = factories.PolicyArgs()
    assert policy.premium > 1000
    new_policy_args = factories.NewPolicyArgs()
    assert isinstance(new_policy_args.riskModule, types.Address)

    transfer = factories.TransferArgs()
    assert transfer.value != 0
    approval = factories.ApprovalArgs()
    assert approval.value != 0


def test_factories():
    chain = factories.Chain()
    assert isinstance(chain, types.Chain)
    block = factories.Block()
    assert isinstance(block, types.Block)
    tx = factories.Tx()
    assert isinstance(tx, types.Tx)

    for _ in range(10):
        event = factories.Event()
        assert isinstance(event, types.Event)

        assert event.name in ["Transfer", "Approval", "NewPolicy"]

        if event.name == "Transfer":
            assert hasattr(event.args, "to")
        elif event.name == "Approval":
            assert hasattr(event.args, "owner")
            assert not hasattr(event.args, "to")
        elif event.name == "NewPolicy":
            assert hasattr(event.args, "riskModule")
