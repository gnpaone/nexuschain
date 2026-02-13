CONFIG = {
    "nodes": [
        {"node_id": 0, "ip": "192.168.1.101", "port": 5000},
        {"node_id": 1, "ip": "192.168.1.102", "port": 5000},
        {"node_id": 2, "ip": "192.168.1.103", "port": 5000},
        {"node_id": 3, "ip": "192.168.1.104", "port": 5000},
        {"node_id": 4, "ip": "192.168.1.105", "port": 5000},
        {"node_id": 5, "ip": "192.168.1.106", "port": 5000},
        {"node_id": 6, "ip": "192.168.1.107", "port": 5000},
        {"node_id": 7, "ip": "192.168.1.108", "port": 5000},
        {"node_id": 8, "ip": "192.168.1.109", "port": 5000},
        {"node_id": 9, "ip": "192.168.1.110", "port": 5000},
    ],
    "consensus_algorithm": "pbft",  # Options: "pbft", "poa", "pos", or custom algorithms
    "simulation_duration": 120,  # seconds
    "block_size": 5,  # Transactions per block
    "transaction_rate": 2,  # Tx per second per node
    "network": {
        "propagation_delay": 0.1,  # Base simulated network delay in seconds
        "socket_timeout": 2,  # Socket connection timeout in seconds
        "max_retries": 3,  # Max retries for message sending
    },
    "staking_balances": {i: 10 for i in range(10)},  # Initial stakes for PoS
    "validators_poa": [0, 1, 2],  # Validator node IDs for PoA
    "attack_config": {
        "enabled": True,
        "drop_rate": 0.1,  # Probability of dropping inbound messages
        "delay_range": (0.05, 0.2),  # Min and max random delay seconds
        "partition_nodes": [7, 8],  # Nodes isolated in network partition attack
    },
    "malicious_nodes": {
        3: {"drop_incoming_messages": True},
        5: {"send_conflicting_blocks": True},
    },
    "logging_level": "INFO",
}
