import time
import json
import hashlib


class Transaction:
    def __init__(self, sender, receiver, amount, timestamp=None):
        self.sender = sender  # Address of the sender
        self.receiver = receiver  # Address of the receiver
        self.amount = amount  # Amount to transfer
        self.timestamp = timestamp or time.time()  # Time the transaction is created
        self.tx_hash = self.compute_hash()  # Unique hash of this transaction

    def compute_hash(self):
        """
        Compute SHA-256 hash of the transaction contents.
        """
        tx_dict = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
        }
        tx_string = json.dumps(tx_dict, sort_keys=True)
        return hashlib.sha256(tx_string.encode()).hexdigest()

    def __repr__(self):
        return f"Transaction({self.sender} -> {self.receiver}, amount: {self.amount}, hash: {self.tx_hash[:10]}...)"
