import pytest

from eth_pretty_events.block_tree import Block, BlockTree
from eth_pretty_events.types import Hash


@pytest.fixture
def block_tree():
    return BlockTree()


@pytest.fixture
def sample_blocks():
    return [
        Block(number=1, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a")),
        Block(number=2, hash=Hash("0x4a76712bb2be112fd59f3a4f285dbc3c4b39914f557e5e336cf95b3cf4545328")),
        Block(number=3, hash=Hash("0x0e7f26e06d8180ef5ded173f6e2f2de666cc4e78b7957e6aaa0b9aa2dd04de76")),
        Block(number=4, hash=Hash("0x3bb2053d860f35c67cfa32c256ca4d969c8693d36bbdd60b4aadc73e8efb0def")),
    ]


def test_add_new_blocks(block_tree):

    block1_hash = Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a")
    block_tree.add_block(1, None, block1_hash)

    assert len(block_tree.forks) == 1
    assert block_tree.forks[0][0].number == 1
    assert block_tree.forks[0][0].hash == block1_hash

    block2_hash = Hash("0x4a76712bb2be112fd59f3a4f285dbc3c4b39914f557e5e336cf95b3cf4545328")
    block_tree.add_block(2, block1_hash, block2_hash)

    assert len(block_tree.forks[0]) == 2
    assert block_tree.forks[0][1].number == 2
    assert block_tree.forks[0][1].hash == block2_hash
    assert block_tree.forks[0][1].number == block_tree.forks[0][0].number + 1


def test_add_new_blocks_create_fork(block_tree):
    block1_hash = Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a")
    block_tree.add_block(1, None, block1_hash)

    block2_hash = Hash("0x4a76712bb2be112fd59f3a4f285dbc3c4b39914f557e5e336cf95b3cf4545328")
    block_tree.add_block(1, None, block2_hash)

    assert len(block_tree.forks) == 2
    assert block_tree.forks[0][0].hash == block1_hash
    assert block_tree.forks[1][0].hash == block2_hash


def test_clean_older_blocks(block_tree, sample_blocks):

    for block in sample_blocks:
        parent_hash = sample_blocks[block.number - 2].hash if block.number > 1 else None
        block_tree.add_block(block.number, parent_hash, block.hash)

    block_tree.clean(older_than_blocks=2)

    assert len(block_tree.forks[0]) == 3
    assert block_tree.forks[0][0].number == 2
    assert block_tree.forks[0][1].number == 3
    assert block_tree.forks[0][2].number == 4


def test_clean_with_old_fork(block_tree, sample_blocks):

    for block in sample_blocks:
        parent_hash = sample_blocks[block.number - 2].hash if block.number > 1 else None
        block_tree.add_block(block.number, parent_hash, block.hash)

    block_fork = Block(number=1, hash=Hash("0x53573de4e74a1b8f6018610a624605cba6434336d2ea96bfa0e947bf37f2d169"))
    block_tree.add_block(block_fork.number, sample_blocks[2], block_fork.hash)

    assert len(block_tree.forks) == 2
    block_tree.clean(older_than_blocks=2)

    assert len(block_tree.forks) == 1
    assert len(block_tree.forks[0]) == 3
    assert block_tree.forks[0][0].number == 2
    assert block_tree.forks[0][1].number == 3
    assert block_tree.forks[0][2].number == 4


def test_confirmations(block_tree, sample_blocks):

    for block in sample_blocks:
        parent_hash = sample_blocks[block.number - 2].hash if block.number > 1 else None
        block_tree.add_block(block.number, parent_hash, block.hash)

    assert block_tree.confirmations(4, sample_blocks[3].hash) == 0
    assert block_tree.confirmations(3, sample_blocks[2].hash) == 1
    assert block_tree.confirmations(2, sample_blocks[1].hash) == 2
    assert block_tree.confirmations(1, sample_blocks[0].hash) == 3


def test_confirmations_nonexisting_block(block_tree):
    nonexisting_block_hash = Hash("0x53573de4e74a1b8f6018610a624605cba6434336d2ea96bfa0e947bf37f2d169")
    assert block_tree.confirmations(5, nonexisting_block_hash) == -1


def test_confirmations_number_higher_than_last_block(block_tree):
    block = Block(number=1, hash=Hash("0xd77c733e1884cd516c042549861c93cad8b998f691c38682c6100d7872761d4a"))
    block_tree.add_block(block.number, None, block.hash)
    assert block_tree.confirmations(5, block.hash) == -1


def test_confirmations_fork_len_shorter(block_tree, sample_blocks):
    for block in sample_blocks:
        parent_hash = sample_blocks[block.number - 2].hash if block.number > 1 else None
        block_tree.add_block(block.number, parent_hash, block.hash)

    assert block_tree.confirmations(0, sample_blocks[0].hash) == -1


def test_confirmations_incorrect_hash(block_tree, sample_blocks):
    for block in sample_blocks:
        parent_hash = sample_blocks[block.number - 2].hash if block.number > 1 else None
        block_tree.add_block(block.number, parent_hash, block.hash)

    assert block_tree.confirmations(1, sample_blocks[1].hash) == -1
