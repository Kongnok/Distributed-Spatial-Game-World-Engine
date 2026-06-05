import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import NODES, GATEWAY_PORT

app = FastAPI(title="Gateway Node")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request schema — matches what bot_simulator.py sends
# ---------------------------------------------------------------------------
class BotSpawn(BaseModel):
    id:    str
    x:     float
    y:     float
    vx:    float
    vy:    float
    color: str


# ---------------------------------------------------------------------------
# Routing helper — pure function, no side effects
# ---------------------------------------------------------------------------
def resolve_node(x: float, y: float) -> int:
    """Return node number (1-4) based on (x, y) coordinates."""
    if x <= 100 and y > 100:
        return 1  # NW
    if x > 100 and y > 100:
        return 2  # NE
    if x <= 100 and y <= 100:
        return 3  # SW
    # x > 100 and y <= 100
    return 4      # SE


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@app.post("/spawn")
async def spawn(bot: BotSpawn):
    """
    Called by bot_simulator.py once per bot at startup.
    Determines correct node, forwards the full bot payload, returns result.
    Gateway does NOT store any bot state.
    """
    node_id   = resolve_node(bot.x, bot.y)
    node_cfg  = NODES[node_id]
    target    = f"http://127.0.0.1:{node_cfg['port']}/spawn"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(target, json=bot.model_dump())
            resp.raise_for_status()
        print(f"[Gateway] {bot.id} ({bot.x:.0f},{bot.y:.0f}) → Node {node_id} ({node_cfg['label']}) ✓")
        return {"status": "routed", "node": node_id, "label": node_cfg["label"]}

    except Exception as exc:
        msg = f"Node {node_id} unreachable: {exc}"
        print(f"[Gateway] {bot.id} → FAIL — {msg}")
        # Per spec: return error, no retry
        return {"status": "error", "detail": msg}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=GATEWAY_PORT)