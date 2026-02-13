import time
from .block import Block
from .transaction import Transaction


class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.create_genesis_block()

    def create_genesis_block(self):
        """
        Creates the first block in the blockchain, known as the genesis block.
        """
        genesis_block = Block(
            index=0, previous_hash="0", transactions=[], timestamp=0.0
        )
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        return self.chain[-1]

    def add_transaction(self, transaction):
        """
        Add a transaction to the list of pending transactions.
        """
        self.pending_transactions.append(transaction)

    def add_block(self, block, proof=None):
        """
        Add a block to the chain.
        verification logic here (e.g. proof of work or just hash link).
        Simple check: previous_hash valid?
        """
        if block.previous_hash != self.last_block.hash:
            print(
                f"Blockchain: Block {block.index} rejected. Prev Hash {block.previous_hash} != Last Block {self.last_block.index} Hash {self.last_block.hash}"
            )
            import sys

            sys.stdout.flush()
            return False

        computed = block.compute_hash()
        if block.hash != computed:
            print(
                f"Blockchain: Block {block.index} rejected. Hash Mismatch. Block Hash {block.hash} != Computed {computed}"
            )
            import sys

            sys.stdout.flush()
            return False
        pass

        self.chain.append(block)
        self.pending_transactions = []
        return True

    def mine_pending_transactions(self, miner_address, nonce=0, add_to_chain=True):
        """
        Creates a new block with pending transactions and adds a mining reward transaction.
        """
        reward_transaction = Transaction(
            sender="Network", receiver=miner_address, amount=1
        )
        self.pending_transactions.append(reward_transaction)

        new_block = Block(
            index=len(self.chain),
            previous_hash=self.last_block.hash,
            transactions=self.pending_transactions,
            timestamp=time.time(),
            nonce=nonce,
        )

        new_block.hash = new_block.compute_hash()

        if add_to_chain:
            self.add_block(new_block)
        return new_block

    def is_chain_valid(self):
        """
        Validates the entire blockchain for integrity.
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            if current.previous_hash != previous.hash:
                return False
            if current.hash != current.compute_hash():
                return False
        return True

    def __repr__(self):
        return f"Blockchain(Length: {len(self.chain)}, Last Block: {self.last_block})"
