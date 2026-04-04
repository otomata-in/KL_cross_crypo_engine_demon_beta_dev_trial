"""
ws_server.py — Headless WebSocket Backend for Arbitrage Dashboard
=================================================================
Refactored from price_gap_monitor.py. All terminal display code removed.
Broadcasts LiveState as JSON over WebSocket at 10fps (ws://127.0.0.1:8765).

Usage:
    python ws_server.py
    python ws_server.py --threshold 0.3
    python ws_server.py --port 8765

Press Ctrl+C to stop.
"""
import asyncio
import csv
import json
import sys
import os
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt.pro as ccxt
import websockets

# ── Configuration ────────────────────────────────────────────────

# The Elite 20: Arbitrage Candidates
# Organized by category for dashboard grouping
CATEGORIES = {
    "💎 Big Three":          ["SOL", "ETH", "BTC"],
    "🟣 Solana Core":        ["JUP", "PYTH", "JTO"],
    "⚡ High Velocity":      ["RENDER", "W", "DRIFT"],
    "🏗️ DePIN & Infra":      ["HNT", "HONEY", "IO"],
    "🏦 Ecosystem HiCaps":   ["KMNO", "TNSR", "CLOUD"],
    "🐕 Meme Liquidity":     ["WIF", "BONK", "MEW"],
    "⭐ Special Pair":        ["BP"],
    "🌐 Cross-Chain":        ["SUI", "SEI"],
}

# Flat list of all tokens (preserves category ordering)
TOKENS = [t for group in CATEGORIES.values() for t in group]

# Build token → category lookup for display
TOKEN_CATEGORY = {}
for cat, tokens in CATEGORIES.items():
    for t in tokens:
        TOKEN_CATEGORY[t] = cat

# Binance uses USDT, Backpack uses USDC
BINANCE_PAIRS  = {t: f"{t}/USDT" for t in TOKENS}
BACKPACK_PAIRS = {t: f"{t}/USDC" for t in TOKENS}

DEFAULT_THRESHOLD = 15.0    # % net profit to highlight (synced to frontend on connect)
WS_BROADCAST_INTERVAL = 0.1  # 100ms = 10fps

# ── Fee / Cost Model ─────────────────────────────────────────────
# All values in percentage (%). These represent the total round-trip
# cost of executing an arbitrage trade.
FEES = {
    "binance_taker":    0.10,   # Binance spot taker fee
    "backpack_taker":   0.10,   # Backpack spot taker fee
    "solana_gas":       0.01,   # Solana network tx fee (~$0.01 per tx, estimated as % of ~$100 trade)
    # Add withdrawal/deposit fees here if applicable
}
TOTAL_FEES_PCT = sum(FEES.values())  # e.g. 0.21%

# Opportunity detection: any gross spread > 0% is a potential opportunity
OPP_MIN_SPREAD    = 0.0
OPP_LOG_FILE      = "logs/opportunities.csv"

# CSV columns for opportunity log
OPP_COLUMNS = [
    "timestamp_utc",
    "token",
    "direction",
    "gross_spread_pct",
    "net_spread_pct",
    "binance_bid",
    "binance_ask",
    "backpack_bid",
    "backpack_ask",
    "usdt_usdc_rate",
    "backpack_bid_depth_usd",
    "binance_bid_depth_usd",
]


# ── Shared state ─────────────────────────────────────────────────
class LiveState:
    """Shared state for all WebSocket feeds."""

    def __init__(self):
        self.binance  = {}     # token -> {bid, ask, bid_depth, ask_depth, updated}
        self.backpack = {}     # token -> {bid, ask, bid_depth, ask_depth, updated}
        self.usdt_usdc_rate = 1.0
        self.ws_status = {
            "binance":  {},    # token -> "connected" | "error:..."
            "backpack": {},    # token -> "connected" | "error:..."
        }
        self.update_count = {"binance": 0, "backpack": 0}
        self.errors = []
        self.started_at = time.monotonic()

        # ── Opportunity tracking ─────────────────────────────────
        self.opp_count     = {t: 0 for t in TOKENS}
        self.opp_total     = 0
        self.opp_last      = {}   # token -> last opp dict
        self.opp_best      = {}   # token -> best spread ever

        # ── Spread tracking (for session highs) ──────────────────
        self.spread_history = {t: {"max_buy_bin": -999, "max_buy_bp": -999} for t in TOKENS}


state = LiveState()


# ── Opportunity Logger ───────────────────────────────────────────
class OpportunityLogger:
    """Logs every detected opportunity to CSV."""

    def __init__(self, filepath: str):
        self._path = filepath
        self._lock = asyncio.Lock()
        self._init_csv()

    def _init_csv(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.exists(self._path):
            with open(self._path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=OPP_COLUMNS)
                writer.writeheader()

    async def log(self, record: dict):
        async with self._lock:
            with open(self._path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=OPP_COLUMNS)
                writer.writerow(record)


opp_logger = OpportunityLogger(OPP_LOG_FILE)


# ── Orderbook parser ────────────────────────────────────────────

def parse_orderbook(ob: dict) -> dict:
    """Extract best bid/ask and depth from orderbook."""
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    best_bid = float(bids[0][0]) if bids else None
    best_ask = float(asks[0][0]) if asks else None
    bid_depth = sum(float(b[0]) * float(b[1]) for b in bids[:5]) if bids else 0
    ask_depth = sum(float(a[0]) * float(a[1]) for a in asks[:5]) if asks else 0
    return {
        "bid": best_bid,
        "ask": best_ask,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "updated": time.monotonic(),
    }


# ── WebSocket feed tasks ────────────────────────────────────────

async def watch_binance_book(exchange, token: str, symbol: str):
    """Subscribe to one Binance orderbook via WebSocket."""
    while True:
        try:
            ob = await exchange.watch_order_book(symbol, limit=10)
            state.binance[token] = parse_orderbook(ob)
            state.ws_status["binance"][token] = "connected"
            state.update_count["binance"] += 1
        except Exception as e:
            state.ws_status["binance"][token] = f"error:{str(e)[:30]}"
            await asyncio.sleep(2)


async def watch_backpack_book(exchange, token: str, symbol: str):
    """Subscribe to one Backpack orderbook via WebSocket."""
    while True:
        try:
            ob = await exchange.watch_order_book(symbol, limit=10)
            state.backpack[token] = parse_orderbook(ob)
            state.ws_status["backpack"][token] = "connected"
            state.update_count["backpack"] += 1
        except Exception as e:
            state.ws_status["backpack"][token] = f"error:{str(e)[:30]}"
            await asyncio.sleep(2)


async def watch_usdt_usdc(exchange):
    """Track USDT/USDC rate via WebSocket ticker."""
    while True:
        try:
            ticker = await exchange.watch_ticker("USDT/USDC")
            if ticker and ticker.get("last"):
                state.usdt_usdc_rate = float(ticker["last"])
        except Exception:
            try:
                ticker = await exchange.watch_ticker("USDC/USDT")
                if ticker and ticker.get("last"):
                    state.usdt_usdc_rate = 1.0 / float(ticker["last"])
            except Exception:
                state.usdt_usdc_rate = 1.0
                await asyncio.sleep(5)


# ── Opportunity detection loop ───────────────────────────────────

async def opportunity_detector():
    """
    Runs alongside WebSocket feeds. Checks for positive spreads
    and logs ALL to CSV (for data analysis), but only counts/tracks
    opportunities where net_spread >= threshold.
    Runs at ~20 checks/sec to catch fleeting opportunities.
    """
    COMBINED_FEE_PCT = TOTAL_FEES_PCT  # exchange fees + gas (see FEES dict)

    await asyncio.sleep(5)  # let feeds warm up

    # Debounce: don't log the same token twice within 1 second
    last_logged = {t: 0.0 for t in TOKENS}

    while True:
        usdt_usdc = state.usdt_usdc_rate

        for token in TOKENS:
            bd = state.binance.get(token, {})
            pd = state.backpack.get(token, {})

            b_bid = bd.get("bid")
            b_ask = bd.get("ask")
            p_bid = pd.get("bid")
            p_ask = pd.get("ask")

            if not all([b_bid, b_ask, p_bid, p_ask]):
                continue

            # Convert Backpack USDC to USDT-equivalent
            p_bid_usdt = p_bid / usdt_usdc
            p_ask_usdt = p_ask / usdt_usdc

            # Both directions
            spread_buy_bin = ((p_bid_usdt - b_ask) / b_ask) * 100
            spread_buy_bp  = ((b_bid - p_ask_usdt) / p_ask_usdt) * 100

            # Update spread history for session highs
            if spread_buy_bin > state.spread_history[token]["max_buy_bin"]:
                state.spread_history[token]["max_buy_bin"] = spread_buy_bin
            if spread_buy_bp > state.spread_history[token]["max_buy_bp"]:
                state.spread_history[token]["max_buy_bp"] = spread_buy_bp

            # Check each direction
            for spread, direction in [
                (spread_buy_bin, "BuyBIN\u2192SellBP"),
                (spread_buy_bp,  "BuyBP\u2192SellBIN"),
            ]:
                if spread <= OPP_MIN_SPREAD:
                    continue

                now = time.monotonic()
                # Debounce: 1 second between logs for the same token
                if now - last_logged[token] < 1.0:
                    continue

                last_logged[token] = now
                net_spread = spread - COMBINED_FEE_PCT

                # Only count/log as an "opportunity" if net profit meets threshold
                if net_spread < threshold_config["value"]:
                    continue

                # Update counters (threshold-qualified only)
                state.opp_count[token] += 1
                state.opp_total += 1

                # Track best
                prev_best = state.opp_best.get(token, -999)
                if net_spread > prev_best:
                    state.opp_best[token] = net_spread

                # Store last opportunity info
                state.opp_last[token] = {
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "spread": round(spread, 4),
                    "net": round(net_spread, 4),
                    "direction": direction,
                }

                # Log to CSV (threshold-qualified only)
                record = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "token": token,
                    "direction": direction,
                    "gross_spread_pct": round(spread, 4),
                    "net_spread_pct": round(net_spread, 4),
                    "binance_bid": b_bid,
                    "binance_ask": b_ask,
                    "backpack_bid": p_bid,
                    "backpack_ask": p_ask,
                    "usdt_usdc_rate": usdt_usdc,
                    "backpack_bid_depth_usd": round(pd.get("bid_depth", 0), 2),
                    "binance_bid_depth_usd": round(bd.get("bid_depth", 0), 2),
                }
                await opp_logger.log(record)

        await asyncio.sleep(0.05)  # 20 checks/second


# ── WebSocket broadcast server ───────────────────────────────────

connected_clients: set = set()

# Shared mutable threshold — updated by frontend via WS, read by all coroutines
threshold_config = {"value": DEFAULT_THRESHOLD}


async def ws_handler(websocket):
    """Handle a new WebSocket client connection.
    
    Bidirectional: broadcasts state to client, and listens for
    incoming messages (e.g. threshold updates from the frontend slider).
    """
    connected_clients.add(websocket)
    remote = websocket.remote_address
    print(f"[ws_server] Client connected: {remote}  ({len(connected_clients)} total)")
    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                if msg.get("type") == "set_threshold":
                    new_val = float(msg.get("value", threshold_config["value"]))
                    new_val = max(0.1, min(15.0, new_val))
                    old_val = threshold_config["value"]
                    threshold_config["value"] = new_val
                    if abs(new_val - old_val) > 0.01:
                        print(f"[ws_server] Threshold updated: {old_val}% → {new_val}% (by {remote})")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass  # ignore malformed messages
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[ws_server] Client disconnected: {remote}  ({len(connected_clients)} total)")


def serialize_state(threshold: float) -> dict:
    """Convert the global LiveState into a JSON-serializable dictionary.

    This is the single payload shape that the React frontend consumes.
    Computed spreads are calculated here so the frontend doesn't need
    to know about USDT/USDC conversion math.
    """
    now_mono = time.monotonic()
    usdt_usdc = state.usdt_usdc_rate
    uptime = int(now_mono - state.started_at)

    # Build per-token orderbook + computed spread data
    token_data = {}
    for token in TOKENS:
        bd = state.binance.get(token, {})
        pd = state.backpack.get(token, {})

        b_bid = bd.get("bid")
        b_ask = bd.get("ask")
        p_bid = pd.get("bid")
        p_ask = pd.get("ask")

        # Compute spreads if we have all prices
        spread_buy_bin = None
        spread_buy_bp = None
        net_buy_bin = None
        net_buy_bp = None
        if all([b_bid, b_ask, p_bid, p_ask]):
            p_bid_usdt = p_bid / usdt_usdc
            p_ask_usdt = p_ask / usdt_usdc
            spread_buy_bin = round(((p_bid_usdt - b_ask) / b_ask) * 100, 4)
            spread_buy_bp  = round(((b_bid - p_ask_usdt) / p_ask_usdt) * 100, 4)
            net_buy_bin = round(spread_buy_bin - TOTAL_FEES_PCT, 4)
            net_buy_bp  = round(spread_buy_bp - TOTAL_FEES_PCT, 4)

        # Session highs (using net spread for meaningful comparison)
        sh = state.spread_history[token]
        session_high_gross = max(sh["max_buy_bin"], sh["max_buy_bp"])
        session_high_net = round(session_high_gross - TOTAL_FEES_PCT, 4) if session_high_gross > -999 else None
        if session_high_gross <= -999:
            session_high_gross = None

        token_data[token] = {
            "category": TOKEN_CATEGORY[token],
            "binance": {
                "bid": b_bid,
                "ask": b_ask,
                "bid_depth": round(bd.get("bid_depth", 0), 2),
                "ask_depth": round(bd.get("ask_depth", 0), 2),
                "age_ms": int((now_mono - bd["updated"]) * 1000) if bd.get("updated") else None,
                "status": state.ws_status["binance"].get(token, "disconnected"),
            },
            "backpack": {
                "bid": p_bid,
                "ask": p_ask,
                "bid_depth": round(pd.get("bid_depth", 0), 2),
                "ask_depth": round(pd.get("ask_depth", 0), 2),
                "age_ms": int((now_mono - pd["updated"]) * 1000) if pd.get("updated") else None,
                "status": state.ws_status["backpack"].get(token, "disconnected"),
            },
            "spread_buy_bin": spread_buy_bin,       # Gross: Buy on Binance → Sell on Backpack
            "spread_buy_bp": spread_buy_bp,         # Gross: Buy on Backpack → Sell on Binance
            "net_spread_buy_bin": net_buy_bin,       # Net: gross - total_fees
            "net_spread_buy_bp": net_buy_bp,         # Net: gross - total_fees
            "session_high_gross": session_high_gross,
            "session_high_net": session_high_net,
            "opp_count": state.opp_count.get(token, 0),
            "opp_best": round(state.opp_best[token], 4) if token in state.opp_best else None,
            "opp_last": state.opp_last.get(token),
        }

    # Connection summaries
    bin_connected = sum(1 for s in state.ws_status["binance"].values() if s == "connected")
    bp_connected  = sum(1 for s in state.ws_status["backpack"].values() if s == "connected")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime,
        "threshold": threshold,

        # Fee model (so frontend can display the cost breakdown)
        "fees": FEES,
        "total_fees_pct": TOTAL_FEES_PCT,

        # Exchange connectivity
        "binance_connected": bin_connected,
        "backpack_connected": bp_connected,
        "total_tokens": len(TOKENS),
        "update_count": state.update_count.copy(),

        # USDT/USDC peg
        "usdt_usdc_rate": usdt_usdc,

        # Opportunity summary
        "opp_total": state.opp_total,

        # Structure metadata (for frontend grouping)
        "categories": CATEGORIES,
        "tokens": TOKENS,

        # Per-token data (the main payload)
        "token_data": token_data,
    }


async def broadcast_state():
    """Broadcast full LiveState JSON to all connected WebSocket clients at 10fps."""
    # Wait for feeds to warm up before broadcasting
    await asyncio.sleep(3)

    while True:
        if connected_clients:
            try:
                payload = json.dumps(serialize_state(threshold_config["value"]))
                websockets.broadcast(connected_clients, payload)
            except Exception as e:
                print(f"[ws_server] Broadcast error: {e}")
        await asyncio.sleep(WS_BROADCAST_INTERVAL)


# ── Main orchestrator ────────────────────────────────────────────

async def main(threshold: float, port: int = 8765):
    """Start all WebSocket feeds, opportunity detector, and broadcast loop."""
    # Set shared threshold from CLI arg
    threshold_config["value"] = threshold

    binance  = ccxt.binance({"options": {"defaultType": "spot"}})
    backpack = ccxt.backpack()

    # Start WebSocket broadcast server
    server = await websockets.serve(ws_handler, "127.0.0.1", port)
    print(f"[ws_server] ⚡ WebSocket server running on ws://127.0.0.1:{port}")
    print(f"[ws_server] Subscribing to {len(TOKENS)} orderbooks on Binance + Backpack...")
    print(f"[ws_server] Threshold: {threshold}%  |  Broadcast: {int(1/WS_BROADCAST_INTERVAL)}fps")
    print(f"[ws_server] Opportunity log: {OPP_LOG_FILE}")

    tasks = []

    # Binance WebSocket feeds
    for token in TOKENS:
        tasks.append(asyncio.create_task(
            watch_binance_book(binance, token, BINANCE_PAIRS[token])
        ))

    # Backpack WebSocket feeds
    for token in TOKENS:
        tasks.append(asyncio.create_task(
            watch_backpack_book(backpack, token, BACKPACK_PAIRS[token])
        ))

    # USDT/USDC rate tracker
    tasks.append(asyncio.create_task(watch_usdt_usdc(binance)))

    # Opportunity detector (runs 20x/sec, reads threshold_config)
    tasks.append(asyncio.create_task(opportunity_detector()))

    # WebSocket broadcast loop (10fps)
    tasks.append(asyncio.create_task(broadcast_state()))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n[ws_server] Shutting down...")
        server.close()
        for task in tasks:
            task.cancel()
        await binance.close()
        await backpack.close()

        # Print session summary
        uptime = int(time.monotonic() - state.started_at)
        print(f"\n{'═' * 60}")
        print(f"  SESSION SUMMARY")
        print(f"{'─' * 60}")
        print(f"  Uptime         : {uptime // 3600}h{(uptime % 3600) // 60:02d}m{uptime % 60:02d}s")
        print(f"  Total opps     : {state.opp_total}")
        for t in TOKENS:
            c = state.opp_count.get(t, 0)
            b = state.opp_best.get(t, 0)
            if c > 0:
                print(f"    {t:<8}: {c:>4} opps  |  best: {b:+.3f}%")
        print(f"  Log file       : {OPP_LOG_FILE}")
        print(f"{'═' * 60}")
        print(f"Server stopped cleanly.")


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    threshold = DEFAULT_THRESHOLD
    port = 8765

    args = sys.argv[1:]
    if "--threshold" in args:
        try:
            threshold = float(args[args.index("--threshold") + 1])
        except (ValueError, IndexError):
            pass
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except (ValueError, IndexError):
            pass

    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    try:
        asyncio.run(main(threshold, port))
    except KeyboardInterrupt:
        print(f"\n[ws_server] Monitor stopped.")
