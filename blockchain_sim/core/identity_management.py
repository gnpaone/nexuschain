import threading


class IdentityManagement:
    def __init__(self):
        """
        Manage unique node identities, support registration and lookups.
        """
        self._lock = threading.Lock()
        self.node_registry = {}  # node_id -> identity info dictionary
        self.public_keys = {}  # node_id -> public_key PEM string

    def register_node(self, node_id, public_key_pem, metadata=None):
        """
        Register a node's identity and public key.
        Returns True if successful, False if node_id already registered.
        """
        with self._lock:
            if node_id in self.node_registry:
                return False  # Duplicate node_id
            self.node_registry[node_id] = {
                "metadata": metadata or {},
                "registered_at": self._current_time(),
            }
            self.public_keys[node_id] = public_key_pem
        return True

    def unregister_node(self, node_id):
        """
        Remove a node from registry.
        """
        with self._lock:
            self.node_registry.pop(node_id, None)
            self.public_keys.pop(node_id, None)

    def get_node_info(self, node_id):
        """
        Retrieve registered info for a node.
        """
        with self._lock:
            return self.node_registry.get(node_id)

    def get_public_key(self, node_id):
        """
        Retrieve the public key PEM for the node.
        """
        with self._lock:
            return self.public_keys.get(node_id)

    def is_registered(self, node_id):
        """
        Check if node is registered.
        """
        with self._lock:
            return node_id in self.node_registry

    def list_nodes(self):
        """
        Return list of all registered node IDs.
        """
        with self._lock:
            return list(self.node_registry.keys())

    def _current_time(self):
        import time

        return time.time()
