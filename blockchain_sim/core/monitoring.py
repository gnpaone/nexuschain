import time
import logging
from collections import defaultdict, deque
from django.db.models import F
from blockchain_sim.models import Node as NodeModel, MetricLog, NetworkEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


class Monitoring:
    def __init__(self, window_size=60):
        self.window_size = window_size

    def record_block_committed(self, node_id, block_obj=None):
        self._log_metric(node_id, "block_committed", 1.0)
        NodeModel.objects.filter(id=str(node_id)).update(
            reputation=F("reputation") + 1.0
        )

        if block_obj:
            try:
                self._log_event(
                    node_id, "BLOCK_COMMITTED", f"Committed block {block_obj.index}"
                )
                validator_id = str(node_id)

                if hasattr(block_obj, "transactions") and block_obj.transactions:
                    first_tx = block_obj.transactions[0]
                    if isinstance(first_tx, dict):
                        validator_id = str(first_tx.get("receiver", node_id))
                    elif hasattr(first_tx, "receiver"):
                        validator_id = str(first_tx.receiver)

                validator_node = None
                try:
                    validator_node = NodeModel.objects.get(id=validator_id)
                except NodeModel.DoesNotExist:
                    try:
                        validator_node = NodeModel.objects.get(id=str(node_id))
                    except:
                        pass

                from blockchain_sim.models import Block

                exists = Block.objects.filter(hash=block_obj.hash).exists()

                if not exists:
                    Block.objects.create(
                        index=block_obj.index,
                        timestamp=block_obj.timestamp,
                        previous_hash=block_obj.previous_hash,
                        hash=block_obj.hash,
                        validator=validator_node,
                        nonce=block_obj.nonce,
                    )
            except Exception as e:
                print(f"Failed to save block to DB: {e}")

    def record_block_produced(self, node_id, block_index):
        self._log_metric(node_id, "block_produced", 1.0)
        self._log_event(node_id, "BLOCK_PROPOSAL", f"Proposed block {block_index}")

    def record_pbft_prepare(self, node_id, block_index, quorum=False):
        msg = f"Sent Prepare for Block {block_index}"
        if quorum:
            msg = f"Quorum reached: Prepared Block {block_index}"
        self._log_event(node_id, "PBFT_PREPARE", msg)

    def record_pbft_commit(self, node_id, block_index, quorum=False):
        msg = f"Sent Commit for Block {block_index}"
        if quorum:
            msg = f"Quorum reached: Committed Block {block_index}"
        self._log_event(node_id, "PBFT_COMMIT", msg)

    def record_sync_event(self, node_id, event_info):
        self._log_event(node_id, "SYNC", f"Synchronization: {event_info}")

    def record_p2p_event(self, node_id, peer_id, msg_type, direction="SENT"):
        """Logs node-to-node communication milestones"""
        if msg_type == "transaction":
            msg_type = "TRANSACTION"

        if direction == "SENT":
            msg = f"Sent {msg_type} to Node {peer_id}"
        else:
            msg = f"Received {msg_type} from Node {peer_id}"
        self._log_event(node_id, "P2P_COMM", msg)

    def record_message(
        self, node_id, msg_type, sent=0, recv=0, dropped=0, retransmit=0, bytes_count=0
    ):
        try:
            updates = {}
            if sent > 0:
                updates["packets_sent"] = F("packets_sent") + sent
            if recv > 0:
                updates["packets_received"] = F("packets_received") + recv
            if dropped > 0:
                updates["packets_dropped"] = F("packets_dropped") + dropped

            if updates:
                NodeModel.objects.filter(id=str(node_id)).update(**updates)
        except Exception as e:
            print(f"Error updating stats for {node_id}: {e}")

    def record_latency(self, node_id, latency_seconds):
        self._log_metric(node_id, "latency", latency_seconds)

    def record_trade_success(self, node_id, count=1):
        NodeModel.objects.filter(id=node_id).update(
            trade_success_count=F("trade_success_count") + count,
            reputation=F("reputation") + (0.5 * count),
        )
        self._log_metric(node_id, "trade_success", float(count))

    def record_trade_failure(self, node_id, count=1):
        NodeModel.objects.filter(id=node_id).update(
            trade_failure_count=F("trade_failure_count") + count,
            reputation=F("reputation") - (2.0 * count),
        )
        self._log_metric(node_id, "trade_fail", float(count))

    def record_trade_confirmation(self, node_id, tx_hash):
        pass

    def _log_metric(self, node_id, metric_type, value):
        try:
            MetricLog.objects.create(
                timestamp=time.time(),
                node_id=node_id,
                metric_type=metric_type,
                value=value,
            )
        except Exception:
            pass

    def _log_event(self, node_id, event_type, message):
        try:
            NetworkEvent.objects.create(
                node_id=node_id, event_type=event_type, message=message
            )
        except Exception:
            pass

    def record_fork_event(self, node_id, fork_info=""):
        self._log_event(node_id, "FORK", f"Fork detected: {fork_info}")

    def raise_alert(self, node_id, message, severity="WARNING"):
        self._log_event(node_id, f"ALERT_{severity}", message)
