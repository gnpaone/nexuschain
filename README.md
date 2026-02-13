# NexusChain Simulator

A modular and interactive Blockchain Simulator built with **Django**, **Poetry**, and **PostgreSQL**. This platform provides a visual dashboard to monitor consensus mechanisms, network traffic, node reputations, and real-time transaction metrics.

---

## 🚀 Key Features

- **Consensus Mechanisms**: Supports PBFT, Proof-of-Stake (PoS), and Proof-of-Authority (PoA).
- **Interactive Dashboard**: Real-time visualization of block production, node status, and network events.
- **Node Management**: Simulate malicious nodes, adjust network delays, and monitor reputation scores (RBCET).
- **Comprehensive Metrics**: Track throughput (block rate), latency, and message statistics via dynamic charts.
- **Dockerized Setup**: Quick deployment using Docker and Docker Compose.

---

## 🛠 Prerequisites

Before you begin, ensure you have the following installed:
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- (Optional for Local Dev) [Python 3.11+](https://www.python.org/downloads/)
- (Optional for Local Dev) [Poetry](https://python-poetry.org/docs/#installation)
- (Optional for Local Dev) [PostgreSQL](https://www.postgresql.org/downloads/)

---

## 🐳 Getting Started (Docker - Recommended)

The fastest way to get the simulation running is using Docker.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gnpaone/nexuschain.git
   cd nexuschain
   ```

2. **Run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

3. **Access the Dashboard**:
   Open your browser and navigate to:
   [http://localhost:8000](http://localhost:8000)

---

## 🐍 Local Installation (Manual Setup)

If you prefer to run the project without Docker:

1. **Install Dependencies**:
   ```bash
   poetry install
   ```

2. **Configure PostgreSQL**:
   Create a PostgresSql database named `blockchain_db` and update the environment variables or `dts_block/settings.py` with your credentials.

3. **Run Migrations**:
   ```bash
   poetry run python manage.py migrate
   ```

4. **Start the Server**:
   ```bash
   poetry run python manage.py runserver
   ```

---

## 🎮 GUI Usage Guide

1. **Start Simulation**: Click the "Start" button on the dashboard. You can configure the number of nodes and the initial network delay.
2. **Monitor Logs**: Watch the "Network Events" log for real-time protocol messages (PRE-PREPARE, COMMIT, etc.).
3. **Drill Down**: Click on any Node ID in the table to view its specific metrics, network configuration, and reputation history.
4. **Stop Simulation**: Click "Stop" to halt block production and clear the dashboard.

---

## 🔌 API Usage

- **POST http://localhost:8000/start/**  
  Starts the simulation.  
  **Parameters:**  
  - `num_nodes` (int) – Number of nodes in the network  
  - `delay` (float) – Network delay in seconds  
  - `network_mode` (string) – Network mode (`fixed`, `randomized`)

- **GET http://localhost:8000/status/**  
  Returns the current simulation state, including network events and node metrics.

- **POST http://localhost:8000/stop/**  
  Stops the simulation and clears the current state.

---

## 🧪 License

Distributed under the MIT License. See `LICENSE` for more information.
