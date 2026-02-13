import time
from ..utils import verify_signature


class PoAConsensus:
    def __init__(self, node, validators, monitoring=None):
        self.node = node
        self.validators = validators
        self.current_leader_index = 0
        self.block_time = 5  # seconds per block
        self.last_block_time = 0
        self.malicious_nodes = set()
        self.received_blocks = set()
        self.monitoring = monitoring

    def current_leader(self):
        return self.validators[self.current_leader_index]

    def rotate_leader(self):
        self.current_leader_index = (self.current_leader_index + 1) % len(
            self.validators
        )

    def can_propose_block(self):
        now = time.time()
        if (
            self.node.node_id == self.current_leader()
            and (now - self.last_block_time) >= self.block_time
        ):
            return True
        return False

    def propose_block(self):
        if self.can_propose_block():
            start_time = time.time()
            block = self.node.create_block()
            if block:
                signature = self._sign_block(block)

                # Log block size and transaction count
                block_size = len(str(block))
                tx_count = len(block.get("transactions", []))
                if self.monitoring:
                    self.monitoring.record_message(
                        self.node.node_id, "poa_message", sent=1, bytes_count=block_size
                    )
                    # Custom log for transaction count could be added if needed

                if self.node.network:
                    msg = {
                        "block": block,
                        "signature": signature,
                        "sender_id": self.node.node_id,
                    }
                    self.node.network.broadcast_poa_message(msg)

                self.last_block_time = time.time()
                self.rotate_leader()

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
            print(f"PoA: Invalid message received by node {self.node.node_id}")
            return

        if self.monitoring:
            self.monitoring.record_message(
                self.node.node_id, "poa_message", recv=1, bytes_count=len(str(msg))
            )

        if sender_id not in self.validators:
            print(f"PoA: Message from non-validator node {sender_id} rejected.")
            self._record_malicious(sender_id)
            if self.monitoring:
                self.monitoring.raise_alert(
                    sender_id, "Message from non-validator rejected", severity="WARNING"
                )
            return

        sender_pubkey_pem = self._get_public_key_for_node(sender_id)
        if not sender_pubkey_pem:
            print(f"PoA: Unknown public key for node {sender_id}, message rejected.")
            return

        sender_pubkey = verify_signature.load_public_key(sender_pubkey_pem)
        block_data_str = str(block)

        if not verify_signature.verify_signature(
            sender_pubkey, block_data_str, signature
        ):
            print(f"PoA: Invalid signature from node {sender_id}, message rejected.")
            self._record_malicious(sender_id)
            if self.monitoring:
                self.monitoring.raise_alert(
                    sender_id, "Invalid signature in PoA message", severity="WARNING"
                )
            return

        block_hash = block.get("hash")
        if block_hash in self.received_blocks:
            print(
                f"PoA: Duplicate block received by node {self.node.node_id}, ignoring."
            )
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
            print(f"PoA: Received block does not match last hash, possible conflict.")
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
            print(f"PoA: Node {node_id} marked as malicious.")
            self.malicious_nodes.add(node_id)
