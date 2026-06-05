# bot_simulator.py
# Runs once at startup. Generates bots, sends them to Gateway. Exits.
# Has zero involvement after all bots are spawned.
#
# Usage:
#   python bot_simulator.py --bots 20 --delay 50

import argparse
import random
import time

import httpx

from config import (
    NODES, GATEWAY_PORT,
    MID_X, MID_Y,
    WORLD_WIDTH, WORLD_HEIGHT,
    MAX_SPEED,
)

GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}/spawn"


# ---------------------------------------------------------------------------
# Color helper
# ---------------------------------------------------------------------------
def random_hex_color() -> str:
    """Returns a random bright hex color. Avoids very dark/near-black values."""
    r = random.randint(80, 255)
    g = random.randint(80, 255)
    b = random.randint(80, 255)
    return f"#{r:02X}{g:02X}{b:02X}"


# ---------------------------------------------------------------------------
# Velocity helper — never returns 0
# ---------------------------------------------------------------------------
def random_velocity() -> float:
    """
    Returns a random velocity in [-MAX_SPEED, MAX_SPEED] excluding 0.
    A bot with zero velocity never crosses boundaries → defeats the demo.
    """
    v = 0
    while v == 0:
        v = random.randint(-MAX_SPEED, MAX_SPEED)
    return float(v)


# ---------------------------------------------------------------------------
# Bot generation — guaranteed spread across all 4 quadrants
# ---------------------------------------------------------------------------
def generate_bots(n: int) -> list[dict]:
    """
    Splits n into 4 equal groups (remainder goes to last group).
    Each group spawns in a specific quadrant.

    Why guaranteed spread over pure random:
        With small N (8–20), pure random risks all bots in one quadrant.
        Guaranteed spread makes all 4 nodes visually active from second 1.
    """
    quadrants = [
        # (label,  x_range,        y_range)
        ("NW",    (0,   MID_X),    (MID_Y + 1, WORLD_HEIGHT)),
        ("NE",    (MID_X + 1, WORLD_WIDTH),  (MID_Y + 1, WORLD_HEIGHT)),
        ("SW",    (0,   MID_X),    (0, MID_Y)),
        ("SE",    (MID_X + 1, WORLD_WIDTH),  (0, MID_Y)),
    ]

    base      = n // 4
    remainder = n % 4   # extra bots go to the last quadrant
    bots      = []
    bot_index = 1

    for i, (label, (x_lo, x_hi), (y_lo, y_hi)) in enumerate(quadrants):
        count = base + (remainder if i == 3 else 0)
        for _ in range(count):
            bots.append({
                "id":    f"bot_{bot_index}",
                "x":     float(random.randint(x_lo, x_hi)),
                "y":     float(random.randint(y_lo, y_hi)),
                "vx":    random_velocity(),
                "vy":    random_velocity(),
                "color": random_hex_color(),
            })
            bot_index += 1

    return bots


# ---------------------------------------------------------------------------
# Spawn loop
# ---------------------------------------------------------------------------
def spawn_all_bots(bots: list[dict], delay_ms: int):
    """
    Posts each bot to Gateway /spawn.
    Waits delay_ms between each to prevent startup request flood.
    Prints result per bot.
    Exits cleanly after all bots are sent.
    """
    print(f"[Simulator] Spawning {len(bots)} bots → Gateway port {GATEWAY_PORT}")
    print(f"[Simulator] Delay between spawns: {delay_ms}ms\n")

    with httpx.Client(timeout=5.0) as client:
        for bot in bots:
            try:
                resp = client.post(GATEWAY_URL, json=bot)
                resp.raise_for_status()
                data = resp.json()
                node_label = data.get("label", "?")
                print(
                    f"[Simulator] ✓ {bot['id']:8s} "
                    f"({bot['x']:5.0f},{bot['y']:5.0f}) "
                    f"vx={bot['vx']:+.0f} vy={bot['vy']:+.0f} "
                    f"→ Node {data.get('node','?')} ({node_label})"
                )
            except Exception as exc:
                print(f"[Simulator] ✗ {bot['id']} FAILED — {exc}")
                print("[Simulator]   Is the Gateway running?")

            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    print(f"\n[Simulator] Done. All {len(bots)} bots submitted. Exiting.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spawn bots into the distributed world.")
    parser.add_argument("--bots",  type=int, default=20,
                        help="Number of bots to spawn (default: 20)")
    parser.add_argument("--delay", type=int, default=50,
                        help="Milliseconds between each spawn (default: 50)")
    args = parser.parse_args()

    if args.bots < 4:
        print("[Simulator] Warning: fewer than 4 bots — some quadrants may start empty.")

    bots = generate_bots(args.bots)
    spawn_all_bots(bots, args.delay)