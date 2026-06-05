# Distributed Spatial Game World Engine

**Distributed Spatial Game World Engine** is a minimal, high-performance prototype demonstrating a 2D spatial grid partitioned seamlessly across isolated backend nodes. This architecture simulates autonomous, moving entities ("bots") traversing quadrant boundaries with real-time state handoffs, fault tolerance, and a unified, retro-styled CRT monitoring dashboard.

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
* **`server.py`**: The heart of the distributed execution. It runs four times simultaneously. Each instance manages localized bot states, drives the physics loop (`game_tick_loop`), processes directional handoffs, and resolves local environment collisions.
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

## Distributed Systems Design

This engine is a practical implementation of several canonical distributed systems patterns. Each design decision maps directly to a well-known concept in the field.

### Shared-Nothing Architecture

Each of the four simulation nodes is fully isolated. They share no memory, no database, and no common state store. The only communication channel between nodes is explicit HTTP over localhost TCP. This is a **shared-nothing architecture** — the same pattern used in large-scale distributed databases and game server clusters.

In `config.py`, this boundary is enforced structurally: each node's address space (coordinate range + port) is defined in isolation, and the neighbor routing table (`NEIGHBORS`) only maps directions to *ports*, never to shared objects or memory references.

```python
# config.py — nodes never reference each other's memory, only their ports
NEIGHBORS = {
    1: { "EAST": 8002, "SOUTH": 8003, "WEST": None, "NORTH": None },
    2: { "WEST": 8001, "SOUTH": 8004, "EAST": None, "NORTH": None },
    ...
}
```

### Stateless Gateway / Coordinator Pattern

`gateway.py` acts as a **stateless router** — it holds zero game state of its own. Its only job is to evaluate the incoming `(x, y)` coordinate and forward the payload to the correct node via `resolve_node()`. Once routed, the gateway is entirely out of the loop.

```python
# gateway.py — pure routing function, no state retained
def resolve_node(x: float, y: float) -> int:
    if x <= 100 and y > 100:  return 1  # NW
    if x > 100  and y > 100:  return 2  # NE
    if x <= 100 and y <= 100: return 3  # SW
    return 4                             # SE
```

This pattern mirrors the **coordinator node** pattern in distributed databases (e.g., MongoDB's `mongos` router), where a lightweight proxy routes requests to the correct shard without itself becoming a bottleneck or a point of state.

### Eventual Consistency via HTTP Handoff

When a bot crosses a quadrant boundary, its state is transferred via a `POST /receive_entity` HTTP call. There is a brief window — between the bot being removed from the source node's `CURRENT_BOTS` dict and its arrival at the destination — where the entity does not exist on any node. This is a deliberate, documented trade-off:

```python
# server.py — bot is deleted BEFORE delivery is confirmed
del CURRENT_BOTS[bot_id]
# ... then the async handoff fires
await client.post(url, json=payload)
```

This is an **at-most-once delivery** model with acknowledged data loss risk at failure boundaries. A production system would implement a two-phase commit or an acknowledgment queue to guarantee exactly-once delivery.

### Topology-Aware Routing (Neighbor Map)

Rather than broadcasting to all nodes or using a central registry lookup on every tick, each node carries a **static neighbor topology map** (`NEIGHBORS` in `config.py`). A boundary crossing only ever communicates with one pre-determined neighbor — O(1) routing with no discovery overhead.

The topology is a 2D mesh graph:

```
  Node 1 (NW) ←→ Node 2 (NE)
       ↕                ↕
  Node 3 (SW) ←→ Node 4 (SE)
```

Each edge is a directed pair of ports. World-edge directions (e.g., Node 1's `WEST` and `NORTH`) map to `None`, signaling the bounce handler instead of a handoff.

### Fault Isolation & Node-Level Crash Recovery

Because each node is a separate OS process, a crash in one node does not propagate to others. The `run.py` orchestrator monitors each `subprocess.Popen` handle in a polling loop:

```python
# run.py — detects unexpected node exits without stopping the rest
while True:
    for i, (tag, _) in enumerate(SERVICES):
        if procs[i].poll() is not None:
            log("LAUNCH", f"⚠  {tag} exited unexpectedly (code {procs[i].returncode})")
    time.sleep(2)
```

When the dead node's neighbors attempt a handoff, they catch the `httpx` connection error and fall back to the dead-drop recovery path — restoring the bot locally and treating the missing quadrant as an impassable wall until the process is restarted.

### Distributed State Observation (Dashboard Polling)

The dashboard (`index.html`) does not receive pushed events. Instead, it performs **fan-out polling**: once every 100 ms it fires four concurrent `fetch()` calls — one per node — and merges the responses into a single unified world view.

```javascript
// index.html — all four nodes are queried in parallel
const results = await Promise.all(NODES.map(fetchNode));
```

This is a **pull-based observability** model. Each node is authoritative only over its own sub-space. The dashboard assembles the global picture client-side, making it resilient to any single node being offline (dead nodes simply show `DEAD` and return zero bots, while the rest of the world continues rendering normally).

---

## Parallel Computation Model

The engine exploits two orthogonal layers of parallelism: **process-level** (OS multiprocessing) and **task-level** (async concurrency within each process).

### Layer 1 — Process-Level Parallelism (True Parallelism)

`run.py` spawns each service as an independent OS process using `subprocess.Popen`. On a multi-core machine, the OS scheduler can assign each node process to a different CPU core, giving true simultaneous execution:

```
CPU Core 0 → run.py (orchestrator + monitor)
CPU Core 1 → gateway.py (port 8000)
CPU Core 2 → server.py --node 1 (NW, port 8001)
CPU Core 3 → server.py --node 2 (NE, port 8002)
CPU Core 4 → server.py --node 3 (SW, port 8003)
CPU Core 5 → server.py --node 4 (SE, port 8004)
```

This sidesteps Python's **Global Interpreter Lock (GIL)** entirely. Because each node is its own interpreter process, bot physics across all four quadrants are computed in true parallel — not interleaved, not time-sliced within a single GIL.

Each process is also isolated in memory. A node crashing with a segfault or unhandled exception does not corrupt the memory space of any other node.

### Layer 2 — Async Concurrency Within Each Node (Cooperative Multitasking)

Within each `server.py` process, parallelism is achieved through Python's `asyncio` event loop. All HTTP request handling and the game tick loop run as **coroutines** — cooperative tasks that yield control at `await` points:

```
asyncio event loop (single thread, single process):
  ├── game_tick_loop()          → runs every 100ms, updates all bots
  ├── POST /spawn               → materializes a new bot into CURRENT_BOTS
  ├── POST /receive_entity      → accepts incoming bots from neighbors
  ├── GET  /get_all_bots        → serves snapshot to dashboard
  └── handoff_bot() tasks       → fired asynchronously per boundary crossing
```

This means a node can be simultaneously ticking bot physics, receiving a new bot from a neighbor, and serving the dashboard — all within one OS thread, with no blocking.

```python
# server.py — handoffs are fired as non-blocking background tasks
asyncio.create_task(handoff_bot(bot_id, bot_data, target_port))
```

Using `create_task` rather than `await` directly means handoffs do not stall the tick loop. Many handoffs can be in-flight at once while physics updates continue.

### Layer 3 — Concurrent Spawn Distribution (bot_simulator.py)

At startup, `bot_simulator.py` guarantees an even spatial distribution of bots across all four quadrants before the first tick fires. It divides `N` bots into four groups and assigns each group to its correct quadrant coordinate range:

```python
# bot_simulator.py — guaranteed spread, not pure random
quadrants = [
    ("NW", (0, MID_X),       (MID_Y+1, WORLD_HEIGHT)),
    ("NE", (MID_X+1, WORLD_WIDTH), (MID_Y+1, WORLD_HEIGHT)),
    ("SW", (0, MID_X),       (0, MID_Y)),
    ("SE", (MID_X+1, WORLD_WIDTH), (0, MID_Y)),
]
```

This ensures all four node processes receive load from second one, preventing a cold-start imbalance where some nodes are idle and others are overloaded.

### Async State Safety — The `STATE_LOCK`

Since multiple coroutines within one node can access `CURRENT_BOTS` simultaneously (tick loop writing positions, `receive_entity` inserting new bots, `get_all_bots` reading for the dashboard), access is serialized with an `asyncio.Lock`:

```python
# server.py — all reads and writes go through the same async lock
async with STATE_LOCK:
    for bot_id, bot in list(CURRENT_BOTS.items()):
        bot["x"] += bot["vx"]
        bot["y"] += bot["vy"]
        ...
```

Because this is an `asyncio.Lock` (not a `threading.Lock`), it never actually blocks the OS thread. It only suspends the current coroutine and yields back to the event loop, which can then run other coroutines — including responding to incoming HTTP requests — while the lock is held.

### Parallel Computation Timeline (One Tick Cycle)

The sequence below illustrates how work flows across all processes during a single 100 ms tick window:

```
t=0ms   ─── All 4 node tick loops wake concurrently (asyncio.sleep(0.1) expires)
            Node 1: updates bots in NW quadrant
            Node 2: updates bots in NE quadrant   ← true parallel (separate processes)
            Node 3: updates bots in SW quadrant
            Node 4: updates bots in SE quadrant

t=~2ms  ─── Boundary crossings detected; handoff coroutines fire as background tasks
            Node 1 → Node 2: bot_42 crosses EAST boundary
            Node 3 → Node 1: bot_07 crosses NORTH boundary  ← concurrent HTTP posts

t=~5ms  ─── Neighbors receive entities via POST /receive_entity
            Each receiving node acquires STATE_LOCK, inserts bot, releases lock

t=100ms ─── Dashboard fires concurrent fetch() to all 4 nodes (Promise.all)
            All 4 nodes serve GET /get_all_bots simultaneously
            Dashboard merges results and redraws canvas
```

All four physics simulations, the inter-node HTTP handoffs, and the dashboard polling all proceed simultaneously — the only serialization is the per-node `STATE_LOCK`, which only gates access within a single node's own coroutines.

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

### Cluster Nodes (`Ports 8001 – 8004`)

* **`POST /spawn`**
  * *Purpose*: Directly materializes a bot into local server tracking dictionaries.

* **`POST /receive_entity`**
  * *Purpose*: Handles boundary crossings by accepting entity migrations from adjacent quadrants.

* **`GET /get_all_bots`**
  * *Purpose*: High-speed data dump targeting the dashboard visualizer layer. Sanitizes data structures by omitting performance metadata like `tick_counter`.