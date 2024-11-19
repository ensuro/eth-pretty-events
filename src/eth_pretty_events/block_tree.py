from dataclasses import dataclass, field
from typing import List

from .types import Hash


@dataclass(frozen=True)
class Block:
    number: int
    hash: Hash


@dataclass(frozen=True)
class BlockTree:
    forks: List[List[Block]] = field(default_factory=list)

    def confirmations(self, number: int, hash: Hash) -> int:
        for f in self.forks:
            last_block = f[-1]
            if number > last_block.number:
                continue
            else:
                blocks_back = last_block.number - number + 1
                if len(f) < blocks_back:
                    continue
                elif f[-blocks_back].hash == hash:
                    return blocks_back - 1
                else:
                    continue
        return -1

    def add_block(self, number: int, parent_hash: Hash, hash: Hash):
        """
        Adds a new block to the BlockTree.

        The resulting .forks structure has the following invariants:
        1. len(f) > 0 for f in self.forks
        2. f[i+1].number = f[i].number + 1
        3. f[i+1].hash is a block with parent_hash = f[i].hash

        Returns the number of fork where the block was added
        """
        for i, f in enumerate(self.forks):
            last_block = f[-1]
            if last_block.number == number - 1 and last_block.hash == parent_hash:
                f.append(Block(number, hash))
                return i
        else:  # adds a new fork
            ret = len(self.forks)
            self.forks.append([Block(number, hash)])
            return ret

    def clean(self, older_than_blocks):
        """
        Cleans blocks older than X blocks from the last one

        Used to avoid increasing the memory usage forever
        """
        max_block_number = max(f[-1].number for f in self.forks)
        clean_older_than = max_block_number - older_than_blocks
        forks_to_remove = []
        for i, f in enumerate(self.forks):
            if clean_older_than > f[-1].number:
                forks_to_remove.append(i)
            elif f[0].number < clean_older_than:
                f[0 : clean_older_than - f[0].number] = []

        for i in reversed(forks_to_remove):
            self.forks.pop(i)

    def dump(self, with_confirmations=True):
        for i, f in enumerate(self.forks):
            print(f"********** Fork {i} *************")
            for block in f:
                if with_confirmations:
                    confirmations = self.confirmations(block.number, block.hash)
                    print(f"- {block.number} ({block.hash}) - {confirmations} confirmations")
                else:
                    print(f"- {block.number} ({block.hash})")
