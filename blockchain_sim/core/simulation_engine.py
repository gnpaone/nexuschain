import time
import threading
import numpy as np
import random
from .node import Node, MaliciousNode
from .consensus.pbft import PbftConsensus
from .consensus.poa import PoAConsensus
from .consensus.pos import PoSConsensus
from .monitoring import Monitoring
from blockchain_sim.models import SimulationConfig, Node as NodeModel


class SimulationEngine:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.nodes = []
        self.monitoring = Monitoring()
        self.metric_history = {"block_rate": [], "latency": [], "fork_rate": []}
        self.config = None
        self.network_mode = "fixed"
        self.network_params = {}

    def start(self, network_mode="fixed", network_params=None):
        if self.is_running:
            return

        self.network_mode = network_mode
        self.network_params = network_params or {}

        self.stop()

        for _ in range(5):
            if not self.thread or not self.thread.is_alive():
                break
            print("Warning: Simulation thread still alive after stop(), forcing wait")
            self.thread.join(timeout=1.0)

        if self.thread and self.thread.is_alive():
            print(
                "ERROR: Simulation thread failed to stop. New simulation might crash."
            )

        time.sleep(1)

        db_config = SimulationConfig.objects.first()
        if not db_config:
            db_config = SimulationConfig.objects.create()

        self.num_nodes = db_config.num_nodes
        self.node_configs = []
        for i in range(self.num_nodes):
            self.node_configs.append(
                {"node_id": i, "ip": "127.0.0.1", "port": 5000 + i}
            )

        self.sim_duration = 3600  # 1 hour max
        self.consensus_alg = "pbft"  # Hardcoded for now or add to model

        base_min = float(self.network_params.get("min_delay", 0.1))
        base_max = float(self.network_params.get("max_delay", 0.2))

        for nc in self.node_configs:
            if self.network_mode == "randomized":
                node_bias = random.uniform(0, 0.2)
                nc["network_config"] = {
                    "delay_range": (base_min + node_bias, base_max + node_bias)
                }
            elif self.network_mode == "manual":
                nc["network_config"] = {"delay_range": (base_min, base_max)}
            else:
                nc["network_config"] = {"delay_range": (base_min, base_max)}

        self.malicious_nodes_config = {}

        NodeModel.objects.all().delete()
        from blockchain_sim.models import Block, Transaction, NetworkEvent, MetricLog

        Block.objects.all().delete()
        Transaction.objects.all().delete()
        NetworkEvent.objects.all().delete()
        MetricLog.objects.all().delete()

        for nc in self.node_configs:
            NodeModel.objects.create(
                id=str(nc["node_id"]), name=f"Node-{nc['node_id']}"
            )

        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        print("Stopping simulation engine...")
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)

        for n in self.nodes:
            if n.network:
                try:
                    n.network.stop()
                except:
                    pass
        self.nodes = []

    def _run_loop(self):
        try:
            self.setup_network()
            print(
                f"Starting simulation with {len(self.nodes)} nodes, consensus={self.consensus_alg}"
            )

            start_time = time.time()
            last_metrics_time = start_time
            last_block_counts = {node.node_id: 0 for node in self.nodes}

            while self.is_running:
                current_time = time.time()
                tx_rate = 2
                total_tx_to_gen = int(self.num_nodes * tx_rate)

                for _ in range(total_tx_to_gen):
                    sender = random.choice(self.nodes)
                    receiver = random.choice(self.nodes)
                    if sender.node_id != receiver.node_id:
                        sender.create_transaction(
                            receiver.node_id, amount=random.randint(1, 10)
                        )

                for node in self.nodes:
                    if self.consensus_alg == "pbft":
                        if hasattr(node, "consensus"):
                            if node.node_id == node.consensus.primary():
                                new_block = node.create_block()
                                if new_block:
                                    node.consensus.propose_block(new_block)

                if current_time - last_metrics_time >= 5:
                    last_metrics_time = current_time

                    from django.db import close_old_connections

                    close_old_connections()

                time.sleep(1.0)
        except Exception as e:
            print(f"Simulation Loop Crashed: {e}")
        finally:
            from django.db import close_old_connections

            close_old_connections()
            self.is_running = False
            for n in self.nodes:
                if n.network:
                    n.network.stop()

    def setup_network(self):
        self.nodes = []
        for node_conf in self.node_configs:
            node_id = node_conf["node_id"]
            node = Node(
                node_id=node_id,
                listen_ip=node_conf["ip"],
                listen_port=node_conf["port"],
                peers=[p for p in self.node_configs if p["node_id"] != node_id],
                monitoring=self.monitoring,
                network_config=node_conf.get("network_config"),
            )
            node.start_network()
            node.consensus = PbftConsensus(
                node, len(self.node_configs), monitoring=self.monitoring
            )
            self.nodes.append(node)

        all_pub_keys = {n.node_id: n.public_key_pem for n in self.nodes}
        for node in self.nodes:
            node.public_keys = all_pub_keys.copy()

    def update_node_network_config(self, node_id, config):
        for node in self.nodes:
            if node.node_id == node_id:
                node.update_network_config(config)
                return True
        return False


simulation_engine = SimulationEngine()
