from enum import Enum, auto
from ..utils import verify_signature, load_public_key, sign_message
import time


class PbftState(Enum):
    PRE_PREPARE = auto()
    PREPARE = auto()
    COMMIT = auto()
    REPLY = auto()


class PbftConsensus:
    def __init__(self, node, total_nodes, monitoring=None):
        self.node = node
        self.total_nodes = total_nodes
        self.current_view = 0
        self.sequence_number = 0
        self.prepared = {}  # Dictionary: seq_number -> set of node_ids
        self.committed = {}  # Dictionary: seq_number -> set of node_ids
        self.message_log = []
        self.received_messages = {}  # (sender_id, msg_type, seq) -> msg
        self.malicious_nodes = set()
        self.monitoring = monitoring
        self.round_start_time = None
        self.last_proposed_index = -1
        import threading

        self.lock = threading.Lock()

    def primary(self):
        return self.current_view % self.total_nodes

    def broadcast(self, message_type, block, signature, seq):
        msg = {
            "type": message_type.name
            if hasattr(message_type, "name")
            else message_type,
            "view": self.current_view,
            "seq": seq,
            "node_id": self.node.node_id,
            "block": block,
            "signature": signature,
        }
        self.message_log.append(msg)

        block_size = len(str(block)) if block else 0
        tx_count = (
            len(block["transactions"]) if block and "transactions" in block else 0
        )
        if self.monitoring:
            self.monitoring.record_message(
                self.node.node_id, msg["type"], sent=1, bytes_count=block_size
            )

        if self.node.network:
            self.node.network.broadcast_pbft_message(msg)

    def receive_message(self, msg):
        try:
            with self.lock:
                msg_type = msg.get("type")
            sender_id = msg.get("node_id")
            block = msg.get("block")
            signature = msg.get("signature")

            if block:
                print(
                    f"DEBUG: Node {self.node.node_id} received {msg_type} from {sender_id} for Block {block.get('index')}"
                )

            sender_public_key_pem = self._get_public_key_for_node(sender_id)
            if not sender_public_key_pem:
                self._log_and_monitor_reject(sender_id, "Unknown sender")
                return
            sender_public_key = load_public_key(sender_public_key_pem)

            from ..utils import serialize

            block_str = serialize(block)

            msg_view = msg.get("view")
            msg_seq = msg.get("seq")

            message_data = f"{msg_type}:{msg_view}:{msg_seq}:{sender_id}:{block_str}"

            if not verify_signature(sender_public_key, message_data, signature):
                self._log_and_monitor_reject(sender_id, "Invalid signature")
                return

            if self.monitoring:
                bytes_len = len(str(msg))
                self.monitoring.record_message(
                    self.node.node_id, msg_type, recv=1, bytes_count=bytes_len
                )

            msg_key = (sender_id, msg_type, msg_seq)
            if msg_key in self.received_messages:
                return

            self.received_messages[msg_key] = msg

            if msg_type == PbftState.PRE_PREPARE.name:
                current_height = (
                    self.node.blockchain.chain[-1].index
                    if self.node.blockchain.chain
                    else -1
                )
                if block["index"] > current_height + 1:
                    self._trigger_sync(current_height + 1, block["index"])
                    return  # Don't vote for gaps

                if (
                    self.node.blockchain.chain
                    and block["previous_hash"] != self.node.blockchain.chain[-1].hash
                ):
                    if self.monitoring:
                        self.monitoring.record_fork_event(
                            self.node.node_id,
                            fork_info=f"Fork overlap at Block {block['index']}",
                        )
                    return

                if self.node.node_id != self.primary():
                    self._send_prepare(block, msg_seq)
                    if msg_seq not in self.prepared:
                        self.prepared[msg_seq] = set()
                    self.prepared[msg_seq].add(self.primary())
                self._start_round_timer()

            elif msg_type == PbftState.PREPARE.name:
                current_height = (
                    self.node.blockchain.chain[-1].index
                    if self.node.blockchain.chain
                    else -1
                )
                if block["index"] > current_height + 1:
                    return

                if msg_seq not in self.prepared:
                    self.prepared[msg_seq] = set()
                self.prepared[msg_seq].add(sender_id)

                quorum = (2 * (self.total_nodes // 3)) + 1
                if len(self.prepared[msg_seq]) >= quorum:
                    if self.monitoring:
                        self.monitoring.record_pbft_prepare(
                            self.node.node_id, block["index"], quorum=True
                        )
                    self._send_commit(block, msg_seq)
                    if msg_seq not in self.committed:
                        self.committed[msg_seq] = set()
                    self.committed[msg_seq].add(self.node.node_id)

            elif msg_type == PbftState.COMMIT.name:
                if msg_seq not in self.committed:
                    self.committed[msg_seq] = set()
                self.committed[msg_seq].add(sender_id)

                quorum = (2 * (self.total_nodes // 3)) + 1
                if len(self.committed[msg_seq]) >= quorum:
                    current_height = (
                        self.node.blockchain.chain[-1].index
                        if self.node.blockchain.chain
                        else -1
                    )
                    if block["index"] <= current_height:
                        return

                    if block["index"] > current_height + 1:
                        self._trigger_sync(current_height + 1, block["index"])
                        return

                    if (
                        self.node.blockchain.chain
                        and block["previous_hash"]
                        != self.node.blockchain.chain[-1].hash
                    ):
                        return

                    try:
                        added = self.node.receive_block(block)
                        if added:
                            self._finish_round_timer(success=True)
                            if msg_seq > self.sequence_number:
                                self.sequence_number = msg_seq
                            self._cleanup_rounds(msg_seq)
                        else:
                            self._finish_round_timer(success=False)
                    except Exception as e:
                        print(f"DEBUG: Exception in receive_block: {e}")
                        import sys

                        sys.stdout.flush()

                    if self.monitoring:
                        self.monitoring.record_pbft_commit(
                            self.node.node_id, block["index"], quorum=True
                        )
                    self._send_reply(block, msg_seq)
            elif msg_type == PbftState.REPLY.name:
                pass
        except Exception as e:
            print(f"CRITICAL PBFT ERROR Node {self.node.node_id}: {e}")
            import traceback

            traceback.print_exc()
            import sys

            sys.stdout.flush()

    def propose_block(self, block):
        with self.lock:
            if block["index"] <= self.last_proposed_index:
                print(
                    f"Node {self.node.node_id}: Skipping duplicate proposal for index {block['index']}"
                )
                return

            if self.node.node_id == self.primary():
                self.sequence_number += 1
                self.last_proposed_index = block["index"]
                seq = self.sequence_number
                if seq not in self.prepared:
                    self.prepared[seq] = set()
                self.prepared[seq].add(self.node.node_id)
                self._start_round_timer()

                signature = self._sign_message(PbftState.PRE_PREPARE.name, block, seq)
                self.broadcast(PbftState.PRE_PREPARE, block, signature, seq)

    def _cleanup_rounds(self, current_seq):
        """Removes logs and vote sets for very old rounds"""
        threshold = 5
        to_delete = [s for s in self.prepared.keys() if s < current_seq - threshold]
        for s in to_delete:
            self.prepared.pop(s, None)
            self.committed.pop(s, None)
            keys_to_del = [k for k in self.received_messages.keys() if k[2] == s]
            for k in keys_to_del:
                self.received_messages.pop(k, None)

    def _send_prepare(self, block, seq):
        if self.monitoring:
            self.monitoring.record_pbft_prepare(self.node.node_id, block.get("index"))
        signature = self._sign_message(PbftState.PREPARE.name, block, seq)
        self.broadcast(PbftState.PREPARE, block, signature, seq)

    def _send_commit(self, block, seq):
        if self.monitoring:
            self.monitoring.record_pbft_commit(self.node.node_id, block.get("index"))
        signature = self._sign_message(PbftState.COMMIT.name, block, seq)
        self.broadcast(PbftState.COMMIT, block, signature, seq)

    def _send_reply(self, block, seq):
        signature = self._sign_message(PbftState.REPLY.name, block, seq)
        self.broadcast(PbftState.REPLY, block, signature, seq)

    def _sign_message(self, msg_type, block, seq):
        from ..utils import serialize

        block_str = serialize(block)
        message_data = (
            f"{msg_type}:{self.current_view}:{seq}:{self.node.node_id}:{block_str}"
        )
        return sign_message(self.node.private_key, message_data)

    def _get_public_key_for_node(self, node_id):
        return self.node.public_keys.get(node_id)

    def _log_and_monitor_reject(self, sender_id, reason):
        print(f"PBFT: Message rejected from node {sender_id}: {reason}")
        self._record_malicious(sender_id)
        if self.monitoring:
            self.monitoring.raise_alert(
                sender_id, f"Message rejected: {reason}", severity="WARNING"
            )

    def _record_malicious(self, node_id):
        if node_id not in self.malicious_nodes:
            print(f"PBFT: Node {node_id} identified as malicious and recorded.")
            self.malicious_nodes.add(node_id)

    def _trigger_sync(self, start_index, end_index):
        if self.node.network:
            print(
                f"PBFT Node {self.node.node_id}: Triggering sync for blocks {start_index} to {end_index}"
            )
            if self.monitoring:
                self.monitoring.record_sync_event(
                    self.node.node_id,
                    f"Triggered sync for blocks {start_index}-{end_index}",
                )
            self.node.network.broadcast_sync_request(start_index, end_index)

    def _start_round_timer(self):
        self.round_start_time = time.time()

    def _finish_round_timer(self, success=False):
        if self.round_start_time and self.monitoring:
            latency = time.time() - self.round_start_time
            self.monitoring.record_latency(self.node.node_id, latency)
            # if success:
            #     self.monitoring.record_block_committed(self.node.node_id)
            self.round_start_time = None
