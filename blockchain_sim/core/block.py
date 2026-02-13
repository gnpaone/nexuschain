import hashlib
import time
import json


class Block:
    def __init__(self, index, previous_hash, transactions, timestamp=None, nonce=0):
        self.index = index  # Position of the block in the chain
        self.previous_hash = previous_hash  # Hash of the previous block
        self.transactions = transactions  # List of transactions included in the block
        self.timestamp = (
            timestamp if timestamp is not None else time.time()
        )  # Block creation time
        self.nonce = nonce  # Nonce for proof of work or other consensus mechanisms
        self.hash = self.compute_hash()  # Current block hash

    def compute_hash(self):
        """
        Compute the SHA-256 hash of the block contents.
        """
        block_data = self.__dict__.copy()
        if "transactions" in block_data:
            serialized_txs = []
            for tx in block_data["transactions"]:
                if hasattr(tx, "__dict__"):
                    tx_dict = tx.__dict__.copy()
                else:
                    tx_dict = tx.copy()
                if "timestamp" in tx_dict:
                    tx_dict["timestamp"] = str(tx_dict["timestamp"])

                serialized_txs.append(tx_dict)
            block_data["transactions"] = serialized_txs

        if "timestamp" in block_data:
            block_data["timestamp"] = str(block_data["timestamp"])

        block_data.pop("hash", None)
        block_string = json.dumps(block_data, sort_keys=True, default=str)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def __repr__(self):
        return f"Block(Index: {self.index}, Hash: {self.hash[:10]}..., PrevHash: {self.previous_hash[:10]}...)"
