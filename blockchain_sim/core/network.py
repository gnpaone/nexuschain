import socket
import threading
import json
import time
import random


class Network:
    def __init__(
        self,
        node,
        peers,
        listen_ip,
        listen_port,
        attack_config=None,
        monitoring=None,
        network_config=None,
    ):
        """
        node: Local node instance
        peers: List of peer dicts with 'ip', 'port', 'node_id'
        listen_ip, listen_port: Bind address for incoming messages
        attack_config: dict with network attack parameters
        monitoring: Monitoring instance for detailed logging
        """
        self.node = node
        self.peers = peers
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.listen_port = listen_port
        self.attack_config = attack_config or {}
        self.network_config = network_config or {}
        self.monitoring = monitoring

        self.server_socket = None
        self.running = False
        self.received_messages_cache = []

    def start(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        retries = 5
        for i in range(retries):
            try:
                self.server_socket.bind((self.listen_ip, self.listen_port))
                break
            except OSError as e:
                if i == retries - 1:
                    print(
                        f"Node {self.node.node_id}: Failed to bind port {self.listen_port} after retries: {e}"
                    )
                    raise e
                time.sleep(1.0)

        self.server_socket.listen()
        threading.Thread(target=self._listen_for_connections, daemon=True).start()
        print(
            f"Node {self.node.node_id}: Listening on {self.listen_ip}:{self.listen_port}"
        )

        if self.attack_config.get("replay_enabled", False):
            threading.Thread(
                target=self._replay_messages_periodically, daemon=True
            ).start()

    def update_config(self, network_config):
        """Update network configuration at runtime"""
        self.network_config.update(network_config)

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
            self.server_socket.close()

    def _listen_for_connections(self):
        while self.running:
            try:
                client_sock, _ = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client, args=(client_sock,), daemon=True
                ).start()
            except OSError:
                break

    def _handle_client(self, client_sock):
        from django.db import close_old_connections

        close_old_connections()
        try:
            self._process_client_data(client_sock)
        finally:
            close_old_connections()
            client_sock.close()

    def _process_client_data(self, client_sock):
        with client_sock:
            data = b""
            while True:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                try:
                    message = json.loads(data.decode())
                    msg_bytes = len(data)
                    if self.monitoring:
                        self.monitoring.record_message(
                            self.node.node_id,
                            message.get("type", "unknown"),
                            recv=1,
                            bytes_count=msg_bytes,
                        )
                    self._process_message(message)
                except json.JSONDecodeError:
                    print(f"Node {self.node.node_id}: Received invalid JSON message.")
                    if self.monitoring:
                        self.monitoring.record_message(
                            self.node.node_id, "invalid_json", dropped=1
                        )

    def _process_message(self, message):
        partitioned = self.attack_config.get("partition_nodes", [])
        sender_id = message.get("sender_id")

        if sender_id in partitioned or self.node.node_id in partitioned:
            print(
                f"Node {self.node.node_id}: Dropping message due to network partition."
            )
            if self.monitoring:
                self.monitoring.record_message(
                    self.node.node_id, message.get("type", ""), dropped=1
                )
            return

        drop_rate = self.attack_config.get("drop_rate", 0)
        if random.random() < drop_rate:
            print(f"Node {self.node.node_id}: Dropping message probabilistically.")
            if self.monitoring:
                self.monitoring.record_message(
                    self.node.node_id, message.get("type", ""), dropped=1
                )
            return

        delay_min, delay_max = self.network_config.get("delay_range", (0, 0))
        if delay_max == 0:
            delay_min, delay_max = self.attack_config.get("delay_range", (0, 0))

        if delay_max > 0:
            delay = random.uniform(delay_min, delay_max)
            time.sleep(delay)

        if self.attack_config.get("replay_enabled", False):
            self.received_messages_cache.append(message)
            if len(self.received_messages_cache) > 100:
                self.received_messages_cache.pop(0)

        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "transaction":
            self.node.receive_transaction(payload)
        elif msg_type == "block":
            self.node.receive_block(payload)
        elif msg_type == "sync_request":
            self.node.handle_sync_request(payload, sender_id)
        elif msg_type == "sync_response":
            self.node.handle_sync_response(payload)
        elif (
            msg_type
            and msg_type.endswith("_message")
            and hasattr(self.node, "consensus")
        ):
            self.node.consensus.receive_message(payload)
        else:
            print(
                f"Node {self.node.node_id}: Unknown or unsupported message type {msg_type}."
            )

        if self.monitoring and sender_id is not None:
            display_type = f"{msg_type}"
            if isinstance(payload, dict) and "type" in payload:
                display_type = f"{payload['type']}"
            self.monitoring.record_p2p_event(
                self.node.node_id, sender_id, display_type, direction="RECV"
            )

    def send_message(self, peer, message):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((peer["ip"], peer["port"]))
            msg_str = json.dumps(message, default=lambda o: o.__dict__)
            msg_bytes = len(msg_str.encode())
            sock.sendall(msg_str.encode())
            sock.close()
            if self.monitoring:
                self.monitoring.record_message(
                    self.node.node_id,
                    message.get("type", ""),
                    sent=1,
                    bytes_count=msg_bytes,
                )
                # Log peer communication event
                msg_type = message.get("type", "unknown")
                payload = message.get("payload")
                if isinstance(payload, dict) and "type" in payload:
                    msg_type = payload["type"]
                self.monitoring.record_p2p_event(
                    self.node.node_id, peer["node_id"], msg_type, direction="SENT"
                )
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print(
                f"Node {self.node.node_id}: Failed to send message to {peer['ip']}:{peer['port']} - {e}"
            )
            if self.monitoring:
                self.monitoring.record_message(
                    self.node.node_id, message.get("type", ""), dropped=1
                )

    def broadcast(self, message):
        partitioned = self.attack_config.get("partition_nodes", [])
        for peer in self.peers:
            if peer.get("node_id") in partitioned or self.node.node_id in partitioned:
                print(
                    f"Node {self.node.node_id}: Not sending to partitioned peer {peer.get('node_id')}"
                )
                if self.monitoring:
                    self.monitoring.record_message(
                        self.node.node_id, message.get("type", ""), dropped=1
                    )
                continue
            self.send_message(peer, message)

    def broadcast_transaction(self, transaction):
        self.broadcast(
            {
                "type": "transaction",
                "payload": transaction,
                "sender_id": self.node.node_id,
            }
        )

    def broadcast_block(self, block):
        self.broadcast(
            {"type": "block", "payload": block, "sender_id": self.node.node_id}
        )

    def broadcast_pbft_message(self, pbft_msg):
        self.broadcast(
            {
                "type": "pbft_message",
                "payload": pbft_msg,
                "sender_id": self.node.node_id,
            }
        )

    def broadcast_poa_message(self, poa_msg):
        self.broadcast(
            {"type": "poa_message", "payload": poa_msg, "sender_id": self.node.node_id}
        )

    def broadcast_pos_message(self, pos_msg):
        self.broadcast(
            {"type": "pos_message", "payload": pos_msg, "sender_id": self.node.node_id}
        )

    def broadcast_sync_request(self, start_index, end_index):
        payload = {"start": start_index, "end": end_index}
        self.broadcast(
            {"type": "sync_request", "payload": payload, "sender_id": self.node.node_id}
        )

    def send_sync_response(self, target_node_id, blocks):
        peer = next((p for p in self.peers if p["node_id"] == target_node_id), None)
        if peer:
            self.send_message(
                peer,
                {
                    "type": "sync_response",
                    "payload": blocks,
                    "sender_id": self.node.node_id,
                },
            )

    def _replay_messages_periodically(self):
        while self.running:
            if self.received_messages_cache:
                message = random.choice(self.received_messages_cache)
                print(
                    f"Node {self.node.node_id}: Replaying message type {message.get('type')}."
                )
                self._process_message(message)
            time.sleep(random.uniform(5, 15))
