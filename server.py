# server.py
# The core distributed node. Run four times with different --node arguments.
#
#   python server.py --node 1   → NW, port 8001
#   python server.py --node 2   → NE, port 8002
#   python server.py --node 3   → SW, port 8003
#   python server.py --node 4   → SE, port 8004
#
# Responsibilities:
#   - Own + update all bots currently in this quadrant
#   - Detect boundary crossings, hand bots off to neighbors
#   - Restore bots if a neighbor is dead (fault tolerance)
#   - Serve GET /get_all_bots for dashboard polling

import argparse
import asyncio
import random
import time

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    NODES, NEIGHBORS,
    WORLD_WIDTH, WORLD_HEIGHT,
    MAX_SPEED, TICK_RATE,
)

# ---------------------------------------------------------------------------
# Parse CLI args early so constants are ready before FastAPI starts
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--node", type=int, required=True, choices=[1, 2, 3, 4])
args = parser.parse_args()

NODE_ID   = args.node
NODE_CFG  = NODES[NODE_ID]
PORT      = NODE_CFG["port"]
X_MIN     = NODE_CFG["x_min"]
X_MAX     = NODE_CFG["x_max"]
Y_MIN     = NODE_CFG["y_min"]
Y_MAX     = NODE_CFG["y_max"]
LABEL     = NODE_CFG["label"]
MY_NEIGHBORS = NEIGHBORS[NODE_ID]  # { "EAST": port|None, ... }

# ---------------------------------------------------------------------------
# Shared state — all bots currently owned by this node
# { bot_id: { id, x, y, vx, vy, color, tick_counter } }
# ---------------------------------------------------------------------------
CURRENT_BOTS: dict = {}
STATE_LOCK = asyncio.Lock()

app = FastAPI(title=f"Node {NODE_ID} ({LABEL})")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class BotData(BaseModel):
    id:    str
    x:     float
    y:     float
    vx:    float
    vy:    float
    color: str


# ---------------------------------------------------------------------------
# Block 2 — Boundary detection
# Returns (direction, neighbor_port) or (None, None) if still in bounds.
# Priority: check X first, then Y. This avoids ambiguity at corners.
# ---------------------------------------------------------------------------
def determine_handoff(x: float, y: float):
    """
    Returns (direction_str, port) if the bot has crossed into a neighbor's
    territory, or (None, None) if it's still in bounds.

    Corner note: a bot can only cross one boundary per tick (MAX_SPEED=5,
    quadrant size=100). We still pick X over Y arbitrarily for safety.
    """
    if x > X_MAX:
        return "EAST",  MY_NEIGHBORS.get("EAST")
    if x < X_MIN:
        return "WEST",  MY_NEIGHBORS.get("WEST")
    if y > Y_MAX:
        return "NORTH", MY_NEIGHBORS.get("NORTH")
    if y < Y_MIN:
        return "SOUTH", MY_NEIGHBORS.get("SOUTH")
    return None, None


# ---------------------------------------------------------------------------
# World-edge bounce — only applies when no neighbor exists in that direction
# Returns (vx, vy) after applying bounce (may be unchanged)
# ---------------------------------------------------------------------------
def apply_bounce(x: float, y: float, vx: float, vy: float):
    """
    Flip velocity component when the bot hits a hard world edge.
    Also clamp position back inside the world to prevent drift.
    """
    if x >= WORLD_WIDTH:
        vx = -abs(vx)   # force negative, don't just flip (handles repeated hits)
    elif x <= 0:
        vx = abs(vx)    # force positive
    if y >= WORLD_HEIGHT:
        vy = -abs(vy)
    elif y <= 0:
        vy = abs(vy)
    return vx, vy


# ---------------------------------------------------------------------------
# Block 3 — Handoff (most critical distributed moment)
# ---------------------------------------------------------------------------
async def handoff_bot(bot_id: str, bot_data: dict, target_port: int):
    """
    Send bot to neighbor node.
    Bot is already removed from CURRENT_BOTS before this is called.

    Fault tolerance: if the neighbor is dead, restore bot here.

    Known limitation (documented per spec):
        The bot is deleted BEFORE we confirm delivery.
        If THIS process crashes mid-handoff, the bot is permanently lost.
        That's accepted for prototype scope.
    """
    url = f"http://127.0.0.1:{target_port}/receive_entity"
    payload = {k: v for k, v in bot_data.items() if k != "tick_counter"}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        print(f"[Node {NODE_ID}] ✓ Handed off {bot_id} → port {target_port}")

    except Exception as exc:
        # Neighbor is down — restore the bot here so it isn't lost
        print(f"[Node {NODE_ID}] ✗ Handoff failed for {bot_id} → port {target_port} ({exc})")
        print(f"[Node {NODE_ID}]   Restoring {bot_id} (fault tolerance)")
        async with STATE_LOCK:
            CURRENT_BOTS[bot_id] = bot_data


# ---------------------------------------------------------------------------
# Block 1 — Game tick loop
# ---------------------------------------------------------------------------
async def game_tick_loop():
    """
    Runs every TICK_RATE seconds indefinitely.
    Updates positions, detects boundary crossings, applies steering.
    Collects handoff candidates FIRST, processes them AFTER iteration
    to avoid modifying CURRENT_BOTS while iterating.
    """
    print(f"[Node {NODE_ID}] Game tick loop started ({TICK_RATE*1000:.0f}ms interval)")

    while True:
        await asyncio.sleep(TICK_RATE)

        handoff_queue = []   # [(bot_id, bot_data, target_port)]

        async with STATE_LOCK:
            for bot_id, bot in list(CURRENT_BOTS.items()):
                # --- Move ---
                bot["x"] += bot["vx"]
                bot["y"] += bot["vy"]

                # --- Steering (random nudge ~every 20 ticks) ---
                bot["tick_counter"] = bot.get("tick_counter", 0) + 1
                if bot["tick_counter"] >= random.randint(18, 22):
                    bot["tick_counter"] = 0
                    axis = random.choice(["vx", "vy"])
                    bot[axis] += random.choice([-1, 1])
                    # Clamp to MAX_SPEED, but never let it reach 0
                    bot[axis] = max(-MAX_SPEED, min(MAX_SPEED, bot[axis]))
                    if bot[axis] == 0:
                        bot[axis] = random.choice([-1, 1])

                # --- Boundary check: does the bot need a handoff? ---
                direction, target_port = determine_handoff(bot["x"], bot["y"])

                if direction is not None:
                    if target_port is not None:
                        # Has a neighbor → queue handoff, remove from this node
                        handoff_queue.append((bot_id, dict(bot), target_port))
                        del CURRENT_BOTS[bot_id]
                    else:
                        # World edge, no neighbor → bounce
                        bot["vx"], bot["vy"] = apply_bounce(
                            bot["x"], bot["y"], bot["vx"], bot["vy"]
                        )
                        # Clamp position back so it doesn't accumulate past the wall
                        bot["x"] = max(0.0, min(float(WORLD_WIDTH),  bot["x"]))
                        bot["y"] = max(0.0, min(float(WORLD_HEIGHT), bot["y"]))

        # --- Fire handoffs after the iteration (never modify dict while iterating) ---
        for bot_id, bot_data, target_port in handoff_queue:
            asyncio.create_task(handoff_bot(bot_id, bot_data, target_port))


# ---------------------------------------------------------------------------
# Block 4 — HTTP endpoints
# ---------------------------------------------------------------------------

@app.post("/spawn")
async def spawn(bot: BotData):
    """Called by Gateway once per bot at startup."""
    async with STATE_LOCK:
        CURRENT_BOTS[bot.id] = {**bot.model_dump(), "tick_counter": 0}
    print(f"[Node {NODE_ID}] Spawned {bot.id} at ({bot.x:.0f},{bot.y:.0f})")
    return {"status": "ok", "node": NODE_ID}


@app.post("/receive_entity")
async def receive_entity(bot: BotData):
    """Called by neighbor nodes during a handoff."""
    async with STATE_LOCK:
        CURRENT_BOTS[bot.id] = {**bot.model_dump(), "tick_counter": 0}
    print(f"[Node {NODE_ID}] Received {bot.id} at ({bot.x:.0f},{bot.y:.0f})")
    return {"status": "success"}


@app.get("/get_all_bots")
async def get_all_bots():
    """
    Called by dashboard every 100ms.
    Returns the current bot list. Read-only — never modifies state.
    """
    async with STATE_LOCK:
        # Strip internal tick_counter before sending to dashboard
        bots = [
            {k: v for k, v in bot.items() if k != "tick_counter"}
            for bot in CURRENT_BOTS.values()
        ]
    return {"node": NODE_ID, "label": LABEL, "bots": bots}


# ---------------------------------------------------------------------------
# Startup hook — kick off the game tick loop
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(game_tick_loop())
    print(f"[Node {NODE_ID}] {LABEL} node live on port {PORT}")
    print(f"[Node {NODE_ID}] Bounds: x[{X_MIN}-{X_MAX}] y[{Y_MIN}-{Y_MAX}]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)