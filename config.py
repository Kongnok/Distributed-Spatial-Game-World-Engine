# config.py
# Single source of truth. No logic. No imports. Just constants.
# Every other file imports from here.

# ---------------------------------------------------------------------------
# World dimensions
# ---------------------------------------------------------------------------
WORLD_WIDTH  = 200
WORLD_HEIGHT = 200
MID_X        = 100
MID_Y        = 100

MAX_SPEED    = 5     # units per tick — bot cannot skip an entire quadrant
TICK_RATE    = 0.1   # seconds — 10 ticks/sec

# ---------------------------------------------------------------------------
# Node definitions
# key   → node number (1-4)
# value → { port, x_min, x_max, y_min, y_max }
#
# Quadrant layout (y-axis: 0 = bottom, 200 = top)
#   NW (1): x 0-100,   y 101-200
#   NE (2): x 101-200, y 101-200
#   SW (3): x 0-100,   y 0-100
#   SE (4): x 101-200, y 0-100
# ---------------------------------------------------------------------------
NODES = {
    1: {"port": 8001, "x_min": 0,   "x_max": 100, "y_min": 101, "y_max": 200, "label": "NW"},
    2: {"port": 8002, "x_min": 101, "x_max": 200, "y_min": 101, "y_max": 200, "label": "NE"},
    3: {"port": 8003, "x_min": 0,   "x_max": 100, "y_min": 0,   "y_max": 100, "label": "SW"},
    4: {"port": 8004, "x_min": 101, "x_max": 200, "y_min": 0,   "y_max": 100, "label": "SE"},
}

# ---------------------------------------------------------------------------
# Neighbor map
# key   → node number
# value → dict of direction → port (or None if world edge → bounce)
# ---------------------------------------------------------------------------
NEIGHBORS = {
    1: {  # NW
        "EAST":  8002,  # → NE
        "SOUTH": 8003,  # → SW
        "WEST":  None,  # world edge
        "NORTH": None,  # world edge
    },
    2: {  # NE
        "WEST":  8001,  # → NW
        "SOUTH": 8004,  # → SE
        "EAST":  None,  # world edge
        "NORTH": None,  # world edge
    },
    3: {  # SW
        "EAST":  8004,  # → SE
        "NORTH": 8001,  # → NW
        "WEST":  None,  # world edge
        "SOUTH": None,  # world edge
    },
    4: {  # SE
        "WEST":  8003,  # → SW
        "NORTH": 8002,  # → NE
        "EAST":  None,  # world edge
        "SOUTH": None,  # world edge
    },
}

# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------
GATEWAY_PORT = 8000