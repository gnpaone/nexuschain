import random
from ..utils import verify_signature
import time


class PoSConsensus:
    def __init__(self, node, validator_set, staking_balances, monitoring=None):
        """
        node: Node instance
        validator_set: List of validator node IDs
        staking_balances: dict mapping node_id to stake amount
        monitoring: Monitoring instance
        """
        self.node = node
        self.validator_set = validator_set
        self.balances = staking_balances
        self.total_staked = sum(staking_balances.values())
        self.current_validator = None
        self.malicious_nodes = set()
        self.received_blocks = set()
        self.monitoring = monitoring

    def select_validator(self):
        rand_value = random.uniform(0, self.total_staked)
        cumulative = 0
        for node_id in self.validator_set:
            stake = self.balances.get(node_id, 0)
            cumulative += stake
            if rand_value <= cumulative:
                self.current_validator = node_id
                return node_id
        return None

    def can_propose(self):
        selected_validator = self.select_validator()
        return self.node.node_id == selected_validator

    def propose_block(self):
        if self.can_propose():
            start_time = time.time()
            block = self.node.create_block()
            if block:
                signature = self._sign_block(block)

                block_size = len(str(block))
                tx_count = len(block.get("transactions", []))

                if self.monitoring:
                    self.monitoring.record_message(
                        self.node.node_id, "pos_message", sent=1, bytes_count=block_size
                    )

                if self.node.network:
                    msg = {
                        "block": block,
                        "signature": signature,
                        "sender_id": self.node.node_id,
                    }
                    self.node.network.broadcast_pos_message(msg)

                if self.monitoring:
                    self.monitoring.record_block_produced(self.node.node_id)
                    latency = time.time() - start_time
                    self.monitoring.record_latency(self.node.node_id, latency)

                return block
        return None

    def receive_message(self, msg):
        block = msg.get("block")
        signature = msg.get("signature")
        sender_id = msg.get("sender_id")

        if not block or not signature or not sender_id:
            print(f"PoS: Invalid message received by node {self.node.node_id}")
            return

        if self.monitoring:
            self.monitoring.record_message(
                self.node.node_id, "pos_message", recv=1, bytes_count=len(str(msg))
            )

        if sender_id not in self.validator_set:
            print(f"PoS: Node {sender_id} is not in validator set, message rejected.")
            self._record_malicious(sender_id)
            if self.monitoring:
                self.monitoring.raise_alert(
                    sender_id, "Message from non-validator rejected", severity="WARNING"
                )
            return

        sender_pubkey_pem = self._get_public_key_for_node(sender_id)
        if not sender_pubkey_pem:
            print(f"PoS: Unknown public key for node {sender_id}, message rejected.")
            return

        sender_pubkey = verify_signature.load_public_key(sender_pubkey_pem)
        block_data_str = str(block)

        if not verify_signature.verify_signature(
            sender_pubkey, block_data_str, signature
        ):
            print(f"PoS: Invalid signature from node {sender_id}, message rejected.")
            self._record_malicious(sender_id)
            if self.monitoring:
                self.monitoring.raise_alert(
                    sender_id, "Invalid signature in PoS message", severity="WARNING"
                )
            return

        block_hash = block.get("hash")
        if block_hash in self.received_blocks:
            print(f"PoS: Duplicate block {block_hash} received, ignoring.")
            return

        self.received_blocks.add(block_hash)

        last_hash = (
            self.node.blockchain.last_block.hash if self.node.blockchain.chain else None
        )
        if block.get("previous_hash") == last_hash:
            self.node.receive_block(block)
            if self.monitoring:
                self.monitoring.record_block_committed(self.node.node_id)
        else:
            print(f"PoS: Block previous hash mismatch, possible fork or attack.")
            if self.monitoring:
                self.monitoring.record_fork_event(
                    self.node.node_id, fork_info="conflict detected"
                )

    def _sign_block(self, block):
        from ..utils import sign_message

        block_data = str(block)
        return sign_message(self.node.private_key, block_data)

    def _get_public_key_for_node(self, node_id):
        return self.node.public_keys.get(node_id)

    def _record_malicious(self, node_id):
        if node_id not in self.malicious_nodes:
            print(f"PoS: Node {node_id} marked malicious.")
            self.malicious_nodes.add(node_id)
