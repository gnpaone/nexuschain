import time
import threading
import random
from .blockchain import Blockchain
from .utils import (
    timestamp,
    sha256_hash,
    generate_private_key,
    serialize_public_key,
    serialize_private_key,
)
from .transaction import Transaction


class Node:
    def __init__(
        self,
        node_id,
        listen_ip,
        listen_port,
        peers,
        monitoring=None,
        network_config=None,
    ):
        self.node_id = node_id
        self.blockchain = Blockchain()
        self.mempool = []  # List of unconfirmed transactions
        self.network = None
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.peers = peers
        self.consensus = None
        self.monitoring = monitoring
        self.network_config = network_config or {}

        # Keys and Identity
        self.public_keys = {}  # Map node_id -> public_key_pem
        self.private_key = generate_private_key()
        self.public_key = self.private_key.public_key()
        self.public_key_pem = serialize_public_key(self.public_key)
        self.public_keys[self.node_id] = self.public_key_pem

        self.seen_transaction_hashes = set()
        self.seen_block_hashes = set()

        # Additional IoEV energy trading metrics
        self.trade_success_count = 0
        self.trade_failure_count = 0
        self.trade_confirmation_times = (
            []
        )  # List of (trade_tx_hash, confirmation_timestamp)

    def start_network(self):
        from .network import Network

        self.network = Network(
            node=self,
            peers=self.peers,
            listen_ip=self.listen_ip,
            listen_port=self.listen_port,
            network_config=self.network_config,
        )
        self.network.monitoring = self.monitoring
        self.network.start()

    def update_network_config(self, config):
        """Updates the network configuration (delays, etc.) at runtime."""
        self.network_config.update(config)
        if self.network:
            self.network.update_config(self.network_config)
        print(f"Node {self.node_id}: Network config updated: {self.network_config}")

    def create_transaction(self, receiver, amount):
        tx = Transaction(sender=self.node_id, receiver=receiver, amount=amount)
        if tx.tx_hash in self.seen_transaction_hashes:
            return None
        self.seen_transaction_hashes.add(tx.tx_hash)
        self.mempool.append(tx.__dict__)

        if self.monitoring:
            self.monitoring.record_message(self.node_id, "transaction", sent=1)

        if self.network:
            self.network.broadcast_transaction(tx.__dict__)
        return tx

    def receive_transaction(self, transaction_dict):
        tx_hash = transaction_dict.get("tx_hash")
        if tx_hash in self.seen_transaction_hashes:
            if self.monitoring:
                self.monitoring.record_message(self.node_id, "transaction", dropped=1)
            print(f"Node {self.node_id}: Ignored replayed transaction {tx_hash}.")
            self._log_trade_failure(tx_hash)
            return

        self.seen_transaction_hashes.add(tx_hash)
        if transaction_dict not in self.mempool:
            self.mempool.append(transaction_dict)
            if self.monitoring:
                self.monitoring.record_message(self.node_id, "transaction", recv=1)
            print(f"Node {self.node_id}: Transaction received and added to mempool.")
            self._log_trade_success(tx_hash)

    def create_block(self, nonce=0, withhold=False):
        if not self.mempool:
            return None

        start_time = time.time()

        if withhold:
            # Convert mempool to Transaction objects for mining
            self.blockchain.pending_transactions = [
                Transaction(t["sender"], t["receiver"], t["amount"], t.get("timestamp"))
                for t in self.mempool
            ]
            new_block = self.blockchain.mine_pending_transactions(
                miner_address=self.node_id, nonce=nonce, add_to_chain=False
            )
            self._withheld_block = new_block
            print(f"Node {self.node_id}: Withholding newly mined block.")

            if new_block:
                block_dict = new_block.__dict__.copy()
                block_dict["transactions"] = [
                    tx.__dict__ if hasattr(tx, "__dict__") else tx
                    for tx in new_block.transactions
                ]
                return block_dict
            return None

        # Convert mempool to Transaction objects for mining
        self.blockchain.pending_transactions = [
            Transaction(t["sender"], t["receiver"], t["amount"], t.get("timestamp"))
            for t in self.mempool
        ]
        new_block = self.blockchain.mine_pending_transactions(
            miner_address=self.node_id, nonce=nonce, add_to_chain=False
        )
        # self.mempool.clear() # Cleared in receive_block
        self._withheld_block = None

        if self.monitoring:
            latency = time.time() - start_time
            if new_block:
                self.monitoring.record_block_produced(self.node_id, new_block.index)
            self.monitoring.record_latency(self.node_id, latency)

        if new_block:
            block_dict = new_block.__dict__.copy()
            # Ensure transactions are serialized as dicts for consistent hashing/signing
            block_dict["transactions"] = [
                tx.__dict__ if hasattr(tx, "__dict__") else tx
                for tx in new_block.transactions
            ]
            return block_dict
        return None

    def release_withheld_block(self):
        if hasattr(self, "_withheld_block") and self._withheld_block and self.network:
            self.network.broadcast_block(self._withheld_block.__dict__)
            print(f"Node {self.node_id}: Released withheld block.")
            self._withheld_block = None

    def receive_block(self, block_dict):
        block_hash = block_dict.get("hash")
        if block_hash in self.seen_block_hashes:
            if self.monitoring:
                self.monitoring.record_message(self.node_id, "block", dropped=1)
            print(f"Node {self.node_id}: Ignored replayed block {block_hash}.")
            return

        self.seen_block_hashes.add(block_hash)
        from .block import Block

        try:
            block = Block(
                index=block_dict["index"],
                previous_hash=block_dict["previous_hash"],
                transactions=block_dict["transactions"],
                timestamp=block_dict["timestamp"],
                nonce=block_dict["nonce"],
            )
            block.hash = block_dict["hash"]

            if not self.blockchain.add_block(block):
                print(f"Node {self.node_id}: add_block failed (validation error)")
                import sys

                sys.stdout.flush()
                return False

            tx_hashes_in_block = {tx["tx_hash"] for tx in block.transactions}
            self.mempool = [
                tx for tx in self.mempool if tx["tx_hash"] not in tx_hashes_in_block
            ]

            if self.monitoring:
                self.monitoring.record_message(self.node_id, "block", recv=1)
                self.monitoring.record_block_committed(self.node_id, block)

            confirmation_time = time.time()
            for tx_hash in tx_hashes_in_block:
                self._log_trade_confirmation(tx_hash, confirmation_time)

            print(
                f"Node {self.node_id}: Block added to blockchain with {len(block.transactions)} transactions."
            )
            import sys

            sys.stdout.flush()
            return True
        except Exception as e:
            with open("node_error.log", "a") as f:
                f.write(
                    f"Node {self.node_id} failed to add block {block_dict.get('index')}: {e}\n"
                )
            print(f"Node {self.node_id}: Failed to add block - {e}")
            import traceback

            traceback.print_exc()
            import sys

            sys.stdout.flush()
            return False

    def handle_sync_request(self, payload, requester_id):
        start = payload.get("start")
        end = payload.get("end")
        if start is None or end is None:
            return

        blocks_to_send = []
        for i in range(start, end + 1):
            if i < len(self.blockchain.chain):
                b = self.blockchain.chain[i]
                b_dict = b.__dict__.copy()
                b_dict["transactions"] = [
                    tx.__dict__ if hasattr(tx, "__dict__") else tx
                    for tx in b.transactions
                ]
                blocks_to_send.append(b_dict)
            else:
                break

        if blocks_to_send and self.network:
            print(
                f"Node {self.node_id}: Sending {len(blocks_to_send)} blocks to Node {requester_id} (Sync)"
            )
            if self.monitoring:
                self.monitoring.record_sync_event(
                    self.node_id,
                    f"Sending {len(blocks_to_send)} blocks to Node {requester_id}",
                )
            self.network.send_sync_response(requester_id, blocks_to_send)

    def handle_sync_response(self, blocks_dict):
        print(
            f"Node {self.node_id}: Received sync response with {len(blocks_dict)} blocks."
        )
        if self.monitoring:
            self.monitoring.record_sync_event(
                self.node_id, f"Received sync response with {len(blocks_dict)} blocks"
            )
        for b_dict in blocks_dict:
            current_height = (
                self.blockchain.chain[-1].index if self.blockchain.chain else -1
            )
            if b_dict["index"] == current_height + 1:
                self.receive_block(b_dict)
            elif b_dict["index"] <= current_height:
                continue
            else:
                pass

    def _log_trade_success(self, tx_hash):
        self.trade_success_count += 1

    def _log_trade_failure(self, tx_hash):
        self.trade_failure_count += 1

    def _log_trade_confirmation(self, tx_hash, confirmation_time):
        self.trade_confirmation_times.append((tx_hash, confirmation_time))

    def __repr__(self):
        return f"Node(ID: {self.node_id}, Chain length: {len(self.blockchain.chain)}, Mempool size: {len(self.mempool)}, Trades Success: {self.trade_success_count}, Trades Fail: {self.trade_failure_count})"


class MaliciousNode(Node):
    def __init__(
        self,
        node_id,
        listen_ip,
        listen_port,
        peers,
        behavior_config=None,
        monitoring=None,
    ):
        super().__init__(node_id, listen_ip, listen_port, peers, monitoring=monitoring)
        self.behavior_config = behavior_config if behavior_config else {}
        self._withheld_block = None
        self._withholding_enabled = self.behavior_config.get("withhold_blocks", False)
        self.replay_attack_enabled = self.behavior_config.get("replay_attack", False)
        self.replay_queue = []

    def create_block(self, nonce=0):
        if self._withholding_enabled:
            return super().create_block(nonce=nonce, withhold=True)

        if self.behavior_config.get("send_conflicting_blocks", False):
            original_block = self.blockchain.mine_pending_transactions(
                miner_address=self.node_id, nonce=nonce
            )
            if original_block:
                conflicting_block = self._generate_conflicting_block(original_block)
                if self.network:
                    self.network.broadcast_block(original_block.__dict__)
                    self.network.broadcast_block(conflicting_block.__dict__)
                self.mempool.clear()
                print(f"MaliciousNode {self.node_id}: Broadcasted conflicting blocks.")
                if self.monitoring:
                    self.monitoring.record_block_produced(
                        self.node_id, original_block.index
                    )

                block_dict = original_block.__dict__.copy()
                block_dict["transactions"] = [
                    tx.__dict__ if hasattr(tx, "__dict__") else tx
                    for tx in original_block.transactions
                ]
                return block_dict
            return None

        return super().create_block(nonce)

    def release_withheld_block(self):
        if self._withheld_block and self.network:
            self.network.broadcast_block(self._withheld_block.__dict__)
            print(f"MaliciousNode {self.node_id}: Released withheld block.")
            self._withheld_block = None

    def receive_transaction(self, transaction_dict):
        if self.replay_attack_enabled and random.random() < 0.2 and self.replay_queue:
            tx = random.choice(self.replay_queue)
            if self.network:
                self.network.broadcast_transaction(tx)
            print(
                f"MaliciousNode {self.node_id}: Replaying transaction {tx.get('tx_hash')}"
            )

        if len(self.replay_queue) > 50:
            self.replay_queue.pop(0)
        self.replay_queue.append(transaction_dict)
        super().receive_transaction(transaction_dict)

    def _generate_conflicting_block(self, original_block):
        import copy

        conflicting_block = copy.deepcopy(original_block)
        conflicting_block.previous_hash = "conflict_" + conflicting_block.previous_hash
        if conflicting_block.transactions:
            conflicting_block.transactions.append(conflicting_block.transactions[0])
        conflicting_block.hash = conflicting_block.compute_hash()
        return conflicting_block

    def receive_block(self, block_dict):
        if self.behavior_config.get("ignore_consensus_messages", False):
            print(f"MaliciousNode {self.node_id}: Ignored incoming block for attack.")
            return
        super().receive_block(block_dict)

    def __repr__(self):
        return (
            f"MaliciousNode(ID: {self.node_id}, Chain length: {len(self.blockchain.chain)}, "
            f"Mempool size: {len(self.mempool)}, Trades Success: {self.trade_success_count}, "
            f"Trades Fail: {self.trade_failure_count})"
        )
