# Distributed Spatial Game World Engine

**Distributed Spatial Game World Engine** a minimal, high-performance prototype demonstrating a 2D spatial grid partitioned seamlessly across isolated backend nodes. This architecture simulates autonomous, moving entities ("bots") traversing quadrant boundaries with real-time state handoffs, fault tolerance, and a unified, retro-styled CRT monitoring dashboard.

---

## Developer Identity

* **Name:** Nusa Sofyan Auliya Akbar
* **NRP:** 152024169

---

## Architectural Overview

The system is designed as a decentralized architecture where the game world space ($200 \times 200$ units) is structurally split into four equal quadrants. Each quadrant is governed by its own independent, isolated simulation server.

```
                  [ 200, 200 ]
      +-----------------+-----------------+
      |                 |                 |
      |     Node 1      |     Node 2      |
      |      (NW)       |      (NE)       |
      |   Port: 8001    |   Port: 8002    |
      |                 |                 |
[0,100]+-----------------+-----------------+ [200,100]
      |                 |                 |
      |     Node 3      |     Node 4      |
      |      (SW)       |      (SE)       |
      |   Port: 8003    |   Port: 8004    |
      |                 |                 |
      +-----------------+-----------------+
    [ 0, 0 ]                           [ 200, 0 ]

```

### Component Breakdown

* **`config.py`**: The single source of truth containing all environment constants, bounding boxes, network ports, neighbor routing topologies, and loop tick-rates.
* **`gateway.py`**: A stateless FastAPI routing proxy. It calculates spatial targets for newly spawned entities based on coordinates and proxies requests cleanly to the correct quadrant node.
* **`server.py`**: The heart of the distributed execution. It runs four times simultaneously. Each instance manages localized bot states, drives the physical physics loop (`game_tick_loop`), processes directional handoffs, and resolves local environment collisions.
* **`bot_simulator.py`**: A lightweight startup routine that populates the simulation by injecting distributed workloads evenly across all quadrants to prevent initial cold-starts.
* **`run.py`**: The multi-process engine orchestrator. It manages execution lifetimes, provisions an HTTP engine for asset serving, handles cross-origin policies (CORS bypass), and coordinates unified log streaming with clean SIGINT teardowns.
* **`index.html`**: A low-latency canvas visualizer designed with an industrial terminal/CRT monitor aesthetic that aggregates and projects state by polling all distinct live nodes concurrently.

---

## Core System Mechanics

### 1. Spatial Partitioning & Boundary Coordinates

The engine explicitly dictates rigid spatial constraints across a 2D matrix map. The space allocations are detailed below:

| Node ID | Quadrant | X Coordinates | Y Coordinates | Service Port |
| --- | --- | --- | --- | --- |
| **Node 1** | NW | $0 \rightarrow 100$ | $101 \rightarrow 200$ | `8001` |
| **Node 2** | NE | $101 \rightarrow 200$ | $101 \rightarrow 200$ | `8002` |
| **Node 3** | SW | $0 \rightarrow 100$ | $0 \rightarrow 100$ | `8003` |
| **Node 4** | SE | $101 \rightarrow 200$ | $0 \rightarrow 100$ | `8004` |

### 2. The Cross-Node Handoff Flow

When a bot's position vector updates beyond its current server boundaries, a synchronized handoff chain fires:

1. The local node loops position steps and evaluates edge parameters via `determine_handoff()`.
2. Upon breach detection, the bot is immediately extracted from the local thread state to prevent duplication.
3. An asynchronous HTTP POST transmits the entity payload to the neighbor's `/receive_entity` endpoint.

> ⚠️ **Architecture Note:** Per design specifications, the bot is popped from local memory right before remote delivery confirmation. If a specific node process terminates exactly mid-handoff, the entity instance will be lost. This intentional compromise keeps the prototyping footprint lightweight and performant.

### 3. Fault Tolerance (Neighbor Dead-Drop)

If a bot attempts to cross into a quadrant whose node server has crashed or dropped offline, the parent node intercepts the `httpx` connection error. Instead of dropping the entity, it automatically triggers a recovery routine:

* It cancels the boundary exit.
* It safely restores the bot into its own local dictionary state (`CURRENT_BOTS`).
* The bot continues simulating locally, gracefully reacting to the dead node as an impassable barrier until the neighbor recovers.

### 4. Physics and Kinetic Steering

* **World Edge Bouncing**: Hard perimeter walls clamp coordinates within the $200 \times 200$ grid and execute absolute velocity inversions via `apply_bounce()` (e.g., $v_x = -\lvert v_x \rvert$).
* **Dynamic Drift**: Every $\approx 20$ simulation ticks, bots undergo a randomized steering nudge to adjust velocity vectors and guarantee randomized, non-linear trajectories across the system grid.

---

## Installation & Setup

### Prerequisites

Ensure your local environment has **Python 3.9+** installed.

### 1. Clone & Initialize Environment

Set up a clean directory structure and initialize a virtual environment to manage dependencies securely.

```bash
# Create and navigate to the project root
mkdir distributed-world && cd distributed-world

# Initialize virtual environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate

# Activate environment (Linux / macOS)
source .venv/bin/activate

```

### 2. Install Required Dependencies

The engine relies on `FastAPI` and `Uvicorn` for modern, asynchronous web services, alongside `HTTPX` for non-blocking node communication.

```bash
pip install fastapi uvicorn httpx pydantic

```

---

## Running the Simulation

The entire orchestration layer is automated through `run.py`. You do not need to boot individual node shells manually.

### Launching the Cluster

Execute the main script to spin up the Gateway, four localized cluster instances, and the dashboard host server:

```bash
python run.py --bots 30 --delay 40

```

### Command Flags

* `--bots [int]`: Configures total concurrent bots generated across the environment (Default: `20`).
* `--delay [int]`: Millisecond pacing throttle between bot creation packets to avoid gateway spamming (Default: `50`).
* `--no-browser`: Prevents the engine from automatically triggering your OS browser layout on boot.

### Stopping the Cluster

To cleanly exit the simulation, press `Ctrl+C` in your terminal workspace. The orchestrator catches the interrupt, stops log capture, and gracefully terminates all detached background node processes.

---

## API Endpoint Blueprint

### Gateway Node (`Port 8000`)

* **`POST /spawn`**
* *Purpose*: Evaluates spatial parameters and proxies payloads to initial coordinate centers.
* *Payload*: `BotSpawn` Pydantic model (`id`, `x`, `y`, `vx`, `vy`, `color`).



### Cluster Nodes (`Ports 8001 - 8004`)

* **`POST /spawn`**
* *Purpose*: Directly materializes a bot into local server tracking dictionaries.


* **`POST /receive_entity`**
* *Purpose*: Handles boundary crossings by accepting entity migrations from adjacent quadrants.


* **`GET /get_all_bots`**
* *Purpose*: High-speed data dump targeting the dashboard visualizer layer. Sanitizes data structures by omitting performance metadata like `tick_counter`."# Distributed-Spatial-Game-World-Engine" 
