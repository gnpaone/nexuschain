import time
import threading
import random
import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from queue import PriorityQueue
from .models import Node, Block, NetworkEvent, SimulationConfig, Transaction
from django.utils import timezone
import uuid


class LocalBlock:
    def __init__(self, index, timestamp, previous_hash, transactions, validator_id):
        self.index = index
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.validator_id = validator_id
        self.nonce = 0
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "previous_hash": self.previous_hash,
                "transactions": [t["id"] for t in self.transactions],
                "validator": self.validator_id,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode()).hexdigest()

    def mine(self, difficulty):
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()


class NodeAgent:
    def __init__(self, node_model: Node, config: SimulationConfig):
        self.model = node_model
        self.id = node_model.id
        self.name = node_model.name
        self.chain: List[LocalBlock] = []
        self.pending_transactions = []
        self.config = config

        genesis = LocalBlock(0, time.time(), "0", [], None)
        genesis.hash = "0" * 64
        self.chain.append(genesis)

    def generate_transaction(self, receiver_id, amount):
        tx = {
            "id": str(uuid.uuid4()),
            "sender": str(self.id),
            "receiver": str(receiver_id),
            "amount": amount,
            "timestamp": time.time(),
        }
        return tx

    def validate_block(self, block: LocalBlock):
        last_block = self.chain[-1]
        if block.index != last_block.index + 1:
            return False
        if block.previous_hash != last_block.hash:
            return False
        if not block.hash.startswith("0" * self.config.difficulty):
            return False
        return True

    def add_block(self, block: LocalBlock):
        if self.validate_block(block):
            self.chain.append(block)
            self.pending_transactions = []
            return True
        return False


@dataclass(order=True)
class SimEvent:
    priority: float
    event_type: str = field(compare=False)
    payload: dict = field(compare=False)


class SimulationEngine:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.nodes: Dict[str, NodeAgent] = {}
        self.event_queue = PriorityQueue()
        self.config = None

    def start(self):
        if self.is_running:
            return

        self.config = SimulationConfig.objects.first()
        if not self.config:
            self.config = SimulationConfig.objects.create()

        self.nodes = {}
        Node.objects.all().delete()
        Block.objects.all().delete()
        Transaction.objects.all().delete()
        NetworkEvent.objects.all().delete()

        for i in range(self.config.num_nodes):
            n = Node.objects.create(name=f"Node-{i+1}", balance=1000)
            self.nodes[str(n.id)] = NodeAgent(n, self.config)

        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()

        NetworkEvent.objects.create(message="Simulation Started", event_type="SYSTEM")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join()

    def _run_loop(self):
        while self.is_running:
            try:
                if random.random() < 0.1:
                    self._generate_random_tx()

                if random.random() < 0.05:
                    self._start_mining_attempt()

                current_time = time.time()
                while not self.event_queue.empty():
                    evt = self.event_queue.queue[0]
                    if evt.priority <= current_time:
                        self.event_queue.get()
                        self._process_event(evt)
                    else:
                        break

                time.sleep(0.1)
            except Exception as e:
                print(f"Error in sim loop: {e}")

    def _generate_random_tx(self):
        sender_id = random.choice(list(self.nodes.keys()))
        receiver_id = random.choice(list(self.nodes.keys()))
        if sender_id == receiver_id:
            return

        sender = self.nodes[sender_id]
        tx = sender.generate_transaction(receiver_id, random.randint(1, 10))

        self._broadcast_event("TX_ANNOUNCE", tx, sender_id)

        sender_model = Node.objects.get(id=sender_id)
        receiver_model = Node.objects.get(id=receiver_id)
        Transaction.objects.create(
            sender=sender_model,
            receiver=receiver_model,
            amount=tx["amount"],
            timestamp=tx["timestamp"],
        )
        NetworkEvent.objects.create(
            node=sender_model,
            event_type="TX",
            message=f"Sent {tx['amount']} to {receiver_model.name}",
        )

    def _start_mining_attempt(self):
        miner_id = random.choice(list(self.nodes.keys()))
        miner = self.nodes[miner_id]

        if not miner.chain:
            return

        last_block = miner.chain[-1]
        new_block = LocalBlock(
            index=last_block.index + 1,
            timestamp=time.time(),
            previous_hash=last_block.hash,
            transactions=miner.pending_transactions,
            validator_id=miner_id,
        )

        mining_time = self.config.difficulty * 0.5 + random.random()
        completion_time = time.time() + mining_time

        self.event_queue.put(
            SimEvent(
                completion_time,
                "BLOCK_MINED",
                {"block": new_block, "miner_id": miner_id},
            )
        )

        NetworkEvent.objects.create(
            node=Node.objects.get(id=miner_id),
            event_type="MINING",
            message=f"Started mining Block {new_block.index}",
        )

    def _broadcast_event(self, type, data, origin_id):
        for nid in self.nodes:
            if nid == origin_id:
                continue

            delay = random.uniform(self.config.min_delay, self.config.max_delay)
            arrival_time = time.time() + delay

            self.event_queue.put(
                SimEvent(
                    arrival_time,
                    "MSG_ARRIVE",
                    {
                        "type": type,
                        "data": data,
                        "receiver_id": nid,
                        "sender_id": origin_id,
                    },
                )
            )

    def _process_event(self, event: SimEvent):
        if event.event_type == "MSG_ARRIVE":
            receiver = self.nodes[event.payload["receiver_id"]]
            msg_type = event.payload["type"]
            data = event.payload["data"]

            if msg_type == "TX_ANNOUNCE":
                receiver.pending_transactions.append(data)
            elif msg_type == "BLOCK_ANNOUNCE":
                block_data = data
                pass

        elif event.event_type == "BLOCK_MINED":
            block = event.payload["block"]
            miner_id = event.payload["miner_id"]
            miner = self.nodes[miner_id]

            if miner.add_block(block):
                db_miner = Node.objects.get(id=miner_id)
                Block.objects.create(
                    index=block.index,
                    timestamp=block.timestamp,
                    previous_hash=block.previous_hash,
                    hash=block.hash,
                    validator=db_miner,
                    nonce=block.nonce,
                )
                NetworkEvent.objects.create(
                    node=db_miner,
                    event_type="SUCCESS",
                    message=f"Mined Block {block.index} ({block.hash[:8]}...)",
                )

                self._broadcast_event("BLOCK_ANNOUNCE", block, miner_id)

                for nid, agent in self.nodes.items():
                    if nid != miner_id:
                        agent.add_block(block)


simulation_engine = SimulationEngine()
