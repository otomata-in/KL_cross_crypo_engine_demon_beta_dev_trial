"""
ws_server.py — Multi-Exchange Arbitrage Dashboard Backend
==========================================================
Monitors orderbooks across Binance, Backpack, Bybit, and Dex-Trade.
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
import collections
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from itertools import combinations

import ccxt.pro as ccxt
import websockets
from dotenv import load_dotenv

from adapters.dextrade_adapter import DexTradeAdapter

# Load environment variables from .env
load_dotenv()

# ── Exchange Configuration Registry ─────────────────────────────
# Add any exchange by editing this dict. No code changes needed.

EXCHANGES = {
    "binance": {
        "ccxt_id":    "binance",
        "label":      "BIN",           # Short label for frontend
        "quote":      "USDT",
        "fee_taker":  0.10,            # %
        "gas":        0.00,            # % (no blockchain transfer for CEX↔CEX)
        "ob_limit":   10,              # Orderbook depth limit for WS
        "enabled":    True,
        "options":    {"defaultType": "spot"},
        "api_key":    os.getenv("API_KEY_BINANCE"),
        "api_secret": os.getenv("API_SECRET_BINANCE"),
    },
    "backpack": {
        "ccxt_id":    "backpack",
        "label":      "BP",
        "quote":      "USDC",
        "fee_taker":  0.10,
        "gas":        0.01,            # Solana network tx fee
        "ob_limit":   10,
        "enabled":    True,
        "options":    {},
        "api_key":    os.getenv("API_KEY_BACKPACK"),
        "api_secret": os.getenv("API_SECRET_BACKPACK"),
    },
    "bybit": {
        "ccxt_id":    "bybit",
        "label":      "BYBIT",
        "quote":      "USDT",
        "fee_taker":  0.10,
        "gas":        0.00,
        "ob_limit":   50,              # Bybit spot only accepts [1, 50, 200, 1000]
        "enabled":    True,
        "options":    {"defaultType": "spot"},
        "api_key":    os.getenv("API_KEY_BYBIT"),
        "api_secret": os.getenv("API_SECRET_BYBIT"),
    },
    "dextrade": {
        "ccxt_id":    None,            # Not ccxt — uses custom DexTradeAdapter
        "label":      "DEX",
        "quote":      "USDT",
        "fee_taker":  0.20,            # Dex-Trade taker fee
        "gas":        0.00,
        "ob_limit":   None,            # REST adapter — no limit param
        "enabled":    True,
        "options":    {},
        "api_key":    os.getenv("API_KEY_DEX"),
        "api_secret": os.getenv("API_SECRET_DEX"),
    },
}

# Derive enabled exchange list
ENABLED_EXCHANGES = [name for name, cfg in EXCHANGES.items() if cfg["enabled"]]

# All possible exchange pairs for spread comparison
EXCHANGE_PAIRS = list(combinations(ENABLED_EXCHANGES, 2))

# ── Token Configuration ─────────────────────────────────────────

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

TOKENS = [t for group in CATEGORIES.values() for t in group]

TOKEN_CATEGORY = {}
for cat, tokens in CATEGORIES.items():
    for t in tokens:
        TOKEN_CATEGORY[t] = cat

# ── General Settings ─────────────────────────────────────────────

DEFAULT_THRESHOLD = 0.001    # % net profit to highlight (synced to frontend)
WS_BROADCAST_INTERVAL = 0.1  # 100ms = 10fps

OPP_MIN_SPREAD   = 0.0
OPP_LOG_FILE     = "logs/opportunities.csv"

# CSV columns — now generic (exchange names instead of hard-coded)
OPP_COLUMNS = [
    "timestamp_utc",
    "token",
    "ex_buy",
    "ex_sell",
    "direction",
    "gross_spread_pct",
    "net_spread_pct",
    "pair_fees_pct",
    "buy_ask",
    "sell_bid",
    "usdt_usdc_rate",
]


# ── Helpers ──────────────────────────────────────────────────────

def get_pair_fees(ex_a: str, ex_b: str) -> float:
    """Total round-trip cost for a given exchange pair (buy on ex_a, sell on ex_b)."""
    buy_fee  = EXCHANGES[ex_a]["fee_taker"]
    sell_fee = EXCHANGES[ex_b]["fee_taker"]
    gas      = max(EXCHANGES[ex_a]["gas"], EXCHANGES[ex_b]["gas"])
    return buy_fee + sell_fee + gas


def normalize_to_usdt(price: float, exchange_name: str, usdt_usdc_rate: float) -> float:
    """Convert any quote currency price to USDT equivalent."""
    quote = EXCHANGES[exchange_name]["quote"]
    if quote == "USDT":
        return price
    elif quote == "USDC":
        return price / usdt_usdc_rate if usdt_usdc_rate != 0 else price
    return price


def build_pair_symbol(token: str, exchange_name: str) -> str:
    """Build the trading pair symbol for a given token on a given exchange."""
    quote = EXCHANGES[exchange_name]["quote"]
    if exchange_name == "dextrade":
        return f"{token}{quote}"  # DexTrade format: "SOLUSDT" (no slash)
    return f"{token}/{quote}"      # ccxt format: "SOL/USDT"


# Pre-compute pair fees for all exchange combinations
PAIR_FEES = {}
for ex_a, ex_b in EXCHANGE_PAIRS:
    # Fees are symmetric for our model (buy_fee + sell_fee + gas)
    fee = get_pair_fees(ex_a, ex_b)
    PAIR_FEES[(ex_a, ex_b)] = fee
    PAIR_FEES[(ex_b, ex_a)] = fee


# ── Shared state ─────────────────────────────────────────────────

class LiveState:
    """Shared state for all exchange feeds."""

    def __init__(self):
        # Generic: {exchange_name: {token: {bid, ask, bid_depth, ask_depth, updated}}}
        self.exchanges    = {ex: {} for ex in ENABLED_EXCHANGES}
        self.ws_status    = {ex: {} for ex in ENABLED_EXCHANGES}
        self.update_count = {ex: 0  for ex in ENABLED_EXCHANGES}

        self.usdt_usdc_rate = 1.0
        self.errors = []
        self.started_at = time.monotonic()

        # Per-exchange: which tokens are available on that exchange
        self.supported_tokens = {ex: set(TOKENS) for ex in ENABLED_EXCHANGES}

        # Opportunity tracking
        self.opp_count     = {t: 0 for t in TOKENS}
        self.opp_total     = 0
        self.opp_last      = {}   # token -> last opp dict
        self.opp_best      = {}   # token -> best net spread ever

        # Spread tracking (session highs) — keyed by token
        self.spread_history = {t: {"max_net": -999} for t in TOKENS}


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
    """Extract best bid/ask and depth from a ccxt orderbook."""
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


# ── Generic WebSocket feed task (for ccxt.pro exchanges) ────────

async def watch_orderbook(exchange_obj, exchange_name: str, token: str, symbol: str):
    """Generic WebSocket orderbook watcher for any ccxt.pro exchange."""
    ob_limit = EXCHANGES[exchange_name].get("ob_limit", 10)
    while True:
        try:
            ob = await exchange_obj.watch_order_book(symbol, limit=ob_limit)
            state.exchanges[exchange_name][token] = parse_orderbook(ob)
            state.ws_status[exchange_name][token] = "connected"
            state.update_count[exchange_name] += 1
        except Exception as e:
            err_msg = str(e)[:80]
            state.ws_status[exchange_name][token] = f"error:{err_msg[:30]}"
            print(f"[ws_server] {exchange_name}/{token} feed error: {err_msg}")
            await asyncio.sleep(2)


# ── Dex-Trade REST polling feed task ─────────────────────────────

async def watch_dextrade_book(adapter: DexTradeAdapter, token: str, pair: str):
    """Poll Dex-Trade REST API for one token's orderbook. Rate-limited."""
    while True:
        try:
            ob = await adapter.fetch_orderbook(pair)
            if ob and ob["bid"] is not None:
                state.exchanges["dextrade"][token] = ob
                state.ws_status["dextrade"][token] = "connected"
                state.update_count["dextrade"] += 1
            else:
                state.ws_status["dextrade"][token] = "error:no_data"
        except Exception as e:
            state.ws_status["dextrade"][token] = f"error:{str(e)[:30]}"
        # Rate limit: stagger polling (10 req/sec shared across all tokens)
        await asyncio.sleep(max(0.5, len(state.supported_tokens.get("dextrade", [])) / 10.0))


# ── USDT/USDC rate tracker ──────────────────────────────────────

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
    Runs alongside feeds. Checks ALL exchange pairs for profitable spreads.
    Only counts/logs opportunities where net_spread >= threshold.
    Runs at ~20 checks/sec.
    """
    await asyncio.sleep(5)  # let feeds warm up

    # Debounce: don't log the same token+pair twice within 1 second
    last_logged = {}  # (token, ex_a, ex_b) -> monotonic time

    while True:
        usdt_usdc = state.usdt_usdc_rate

        for ex_a, ex_b in EXCHANGE_PAIRS:
            pair_fees = PAIR_FEES[(ex_a, ex_b)]

            for token in TOKENS:
                ob_a = state.exchanges[ex_a].get(token, {})
                ob_b = state.exchanges[ex_b].get(token, {})

                a_bid = ob_a.get("bid")
                a_ask = ob_a.get("ask")
                b_bid = ob_b.get("bid")
                b_ask = ob_b.get("ask")

                if not all([a_bid, a_ask, b_bid, b_ask]):
                    continue

                # Normalize all prices to USDT
                a_bid_u = normalize_to_usdt(a_bid, ex_a, usdt_usdc)
                a_ask_u = normalize_to_usdt(a_ask, ex_a, usdt_usdc)
                b_bid_u = normalize_to_usdt(b_bid, ex_b, usdt_usdc)
                b_ask_u = normalize_to_usdt(b_ask, ex_b, usdt_usdc)

                # Direction 1: Buy on ex_a, sell on ex_b
                spread_a_to_b = ((b_bid_u - a_ask_u) / a_ask_u) * 100
                # Direction 2: Buy on ex_b, sell on ex_a
                spread_b_to_a = ((a_bid_u - b_ask_u) / b_ask_u) * 100

                label_a = EXCHANGES[ex_a]["label"]
                label_b = EXCHANGES[ex_b]["label"]

                for spread, direction, buy_ex, sell_ex, buy_ask, sell_bid in [
                    (spread_a_to_b, f"Buy{label_a}→Sell{label_b}", ex_a, ex_b, a_ask, b_bid),
                    (spread_b_to_a, f"Buy{label_b}→Sell{label_a}", ex_b, ex_a, b_ask, a_bid),
                ]:
                    if spread <= OPP_MIN_SPREAD:
                        continue

                    now = time.monotonic()
                    debounce_key = (token, buy_ex, sell_ex)
                    if now - last_logged.get(debounce_key, 0) < 1.0:
                        continue

                    last_logged[debounce_key] = now
                    net_spread = spread - pair_fees

                    # Only count/log if net meets threshold
                    if net_spread < threshold_config["value"]:
                        continue

                    # Update counters
                    state.opp_count[token] += 1
                    state.opp_total += 1

                    # Track best (net)
                    prev_best = state.opp_best.get(token, -999)
                    if net_spread > prev_best:
                        state.opp_best[token] = net_spread

                    # Update session high
                    if net_spread > state.spread_history[token]["max_net"]:
                        state.spread_history[token]["max_net"] = net_spread

                    # Store last opportunity info
                    state.opp_last[token] = {
                        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                        "spread": round(spread, 4),
                        "net": round(net_spread, 4),
                        "direction": direction,
                        "pair": f"{buy_ex}→{sell_ex}",
                    }

                    # Log to CSV
                    record = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "token": token,
                        "ex_buy": buy_ex,
                        "ex_sell": sell_ex,
                        "direction": direction,
                        "gross_spread_pct": round(spread, 4),
                        "net_spread_pct": round(net_spread, 4),
                        "pair_fees_pct": round(pair_fees, 4),
                        "buy_ask": normalize_to_usdt(buy_ask, buy_ex, usdt_usdc),
                        "sell_bid": normalize_to_usdt(sell_bid, sell_ex, usdt_usdc),
                        "usdt_usdc_rate": usdt_usdc,
                    }
                    await opp_logger.log(record)

                    if connected_clients:
                        try:
                            new_opp = json.dumps({"type": "new_opportunity", "data": record})
                            websockets.broadcast(connected_clients, new_opp)
                        except Exception as e:
                            print(f"[ws_server] Broadcast error for new opp: {e}")

        await asyncio.sleep(0.05)  # 20 checks/second


# ── Analytics & Reset ────────────────────────────────────────────

def run_analytics() -> dict:
    if not os.path.exists(OPP_LOG_FILE):
        return {"top_coins": [], "peak_hour": None, "peak_day": None, "total_opps": 0}

    token_counter = collections.Counter()
    route_counter = collections.Counter()
    hour_counter = collections.Counter()
    day_counter = collections.Counter()
    token_max_spread = {}
    total_opps = 0

    try:
        with open(OPP_LOG_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_opps += 1
                token = row.get("token")
                buy_ex = row.get("ex_buy")
                sell_ex = row.get("ex_sell")
                ts_str = row.get("timestamp_utc")

                if token and buy_ex and sell_ex:
                    token_counter[token] += 1
                    route_counter[f"{token}:{buy_ex}->{sell_ex}"] += 1
                    try:
                        net_spread = float(row.get("net_spread_pct", 0))
                        if token not in token_max_spread or net_spread > token_max_spread[token]:
                            token_max_spread[token] = net_spread
                    except (ValueError, TypeError):
                        pass

                if ts_str:
                    try:
                        # Convert to IST (UTC + 5:30)
                        dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        dt_ist = dt_utc + timedelta(hours=5, minutes=30)
                        # 12-hour format e.g. "02:00 PM"
                        hour_str = dt_ist.strftime('%I:00 %p')
                        hour_counter[hour_str] += 1
                        day_counter[dt_ist.strftime("%A")] += 1
                    except Exception:
                        pass
    except Exception as e:
        print(f"[ws_server] Analytics parse error: {e}")

    # Sort top 5 coins by max_net_spread instead of frequency
    sorted_tokens_by_gap = sorted(token_max_spread.items(), key=lambda x: x[1], reverse=True)
    top_5_tokens = [t for t, _ in sorted_tokens_by_gap[:5]]
    
    top_coins_data = []
    for token in top_5_tokens:
        best_route = None
        best_route_count = -1
        for route, count in route_counter.items():
            if route.startswith(f"{token}:"):
                if count > best_route_count:
                    best_route_count = count
                    best_route = route.split(":")[1]
        top_coins_data.append({
            "token": token,
            "count": token_counter[token],
            "best_route": best_route,
            "max_net": round(token_max_spread.get(token, 0), 4)
        })

    return {
        "top_coins": top_coins_data,
        "peak_hour": hour_counter.most_common(1)[0] if hour_counter else None,
        "peak_day": day_counter.most_common(1)[0] if day_counter else None,
        "total_opps": total_opps
    }

async def handle_analytics(websocket):
    analytics = await asyncio.to_thread(run_analytics)
    try:
        await websocket.send(json.dumps({
            "type": "analytics_data",
            "data": analytics
        }))
    except Exception as e:
        print(f"[ws_server] Failed to send analytics: {e}")

async def reset_logs(websocket):
    try:
        with open(OPP_LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=OPP_COLUMNS)
            writer.writeheader()
        
        state.opp_total = 0
        state.opp_count = {t: 0 for t in TOKENS}
        state.opp_best = {}
        state.spread_history = {t: {"max_net": -999} for t in TOKENS}
        
        if connected_clients:
            websockets.broadcast(connected_clients, json.dumps({"type": "logs_reset"}))
    except Exception as e:
        print(f"[ws_server] Error resetting logs: {e}")

# ── WebSocket broadcast server ───────────────────────────────────

connected_clients: set = set()

# Shared mutable threshold — updated by frontend via WS
threshold_config = {"value": DEFAULT_THRESHOLD}


async def ws_handler(websocket):
    """Bidirectional WS handler — broadcasts state, receives threshold updates."""
    connected_clients.add(websocket)
    remote = websocket.remote_address
    print(f"[ws_server] Client connected: {remote}  ({len(connected_clients)} total)")
    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                if msg.get("type") == "set_threshold":
                    new_val = float(msg.get("value", threshold_config["value"]))
                    new_val = max(-2.0, min(15.0, new_val))
                    old_val = threshold_config["value"]
                    threshold_config["value"] = new_val
                    if abs(new_val - old_val) > 0.0001:
                        print(f"[ws_server] Threshold updated: {old_val}% → {new_val}% (by {remote})")
                elif msg.get("type") == "get_recent_opportunities":
                    limit = min(200, max(1, int(msg.get("limit", 100))))
                    try:
                        with open(OPP_LOG_FILE, "r") as f:
                            q = collections.deque(f, limit)
                        reader = csv.DictReader(q, fieldnames=OPP_COLUMNS)
                        logs = list(reader)
                        if logs and logs[0].get("timestamp_utc") == "timestamp_utc":
                            logs.pop(0)
                        await websocket.send(json.dumps({
                            "type": "recent_opportunities",
                            "data": logs
                        }))
                    except Exception as e:
                        print(f"[ws_server] Error reading logs: {e}")
                elif msg.get("type") == "get_analytics":
                    asyncio.create_task(handle_analytics(websocket))
                elif msg.get("type") == "reset_logs":
                    asyncio.create_task(reset_logs(websocket))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[ws_server] Client disconnected: {remote}  ({len(connected_clients)} total)")


def serialize_state(threshold: float) -> dict:
    """Convert global LiveState into JSON-serializable payload for the frontend."""
    now_mono = time.monotonic()
    usdt_usdc = state.usdt_usdc_rate
    uptime = int(now_mono - state.started_at)

    # Build per-token data
    token_data = {}
    for token in TOKENS:
        # Collect exchange data for this token
        exchanges_data = {}
        for ex in ENABLED_EXCHANGES:
            ob = state.exchanges[ex].get(token, {})
            exchanges_data[ex] = {
                "bid": ob.get("bid"),
                "ask": ob.get("ask"),
                "bid_depth": round(ob.get("bid_depth", 0), 2),
                "ask_depth": round(ob.get("ask_depth", 0), 2),
                "age_ms": int((now_mono - ob["updated"]) * 1000) if ob.get("updated") else None,
                "status": state.ws_status[ex].get(token, "disconnected"),
            }

        # Compute spreads for ALL exchange pairs
        spread_pairs = []
        for ex_a, ex_b in EXCHANGE_PAIRS:
            ob_a = state.exchanges[ex_a].get(token, {})
            ob_b = state.exchanges[ex_b].get(token, {})

            a_bid = ob_a.get("bid")
            a_ask = ob_a.get("ask")
            b_bid = ob_b.get("bid")
            b_ask = ob_b.get("ask")

            pair_fees = PAIR_FEES[(ex_a, ex_b)]

            if all([a_bid, a_ask, b_bid, b_ask]):
                a_bid_u = normalize_to_usdt(a_bid, ex_a, usdt_usdc)
                a_ask_u = normalize_to_usdt(a_ask, ex_a, usdt_usdc)
                b_bid_u = normalize_to_usdt(b_bid, ex_b, usdt_usdc)
                b_ask_u = normalize_to_usdt(b_ask, ex_b, usdt_usdc)

                label_a = EXCHANGES[ex_a]["label"]
                label_b = EXCHANGES[ex_b]["label"]

                # Direction: buy on ex_a, sell on ex_b
                gross_a2b = round(((b_bid_u - a_ask_u) / a_ask_u) * 100, 4)
                net_a2b = round(gross_a2b - pair_fees, 4)

                # Direction: buy on ex_b, sell on ex_a
                gross_b2a = round(((a_bid_u - b_ask_u) / b_ask_u) * 100, 4)
                net_b2a = round(gross_b2a - pair_fees, 4)

                spread_pairs.append({
                    "ex_buy": ex_a, "ex_sell": ex_b,
                    "label": f"{label_a}→{label_b}",
                    "gross": gross_a2b, "net": net_a2b,
                    "fees": pair_fees,
                })
                spread_pairs.append({
                    "ex_buy": ex_b, "ex_sell": ex_a,
                    "label": f"{label_b}→{label_a}",
                    "gross": gross_b2a, "net": net_b2a,
                    "fees": pair_fees,
                })
            else:
                label_a = EXCHANGES[ex_a]["label"]
                label_b = EXCHANGES[ex_b]["label"]
                spread_pairs.append({
                    "ex_buy": ex_a, "ex_sell": ex_b,
                    "label": f"{label_a}→{label_b}",
                    "gross": None, "net": None,
                    "fees": pair_fees,
                })
                spread_pairs.append({
                    "ex_buy": ex_b, "ex_sell": ex_a,
                    "label": f"{label_b}→{label_a}",
                    "gross": None, "net": None,
                    "fees": pair_fees,
                })

        # Find best net spread across all pairs
        valid_nets = [sp["net"] for sp in spread_pairs if sp["net"] is not None]
        best_net = max(valid_nets) if valid_nets else None
        best_pair_entry = None
        if best_net is not None:
            best_pair_entry = next(
                (sp for sp in spread_pairs if sp["net"] == best_net), None
            )

        # Update session high from live spread data (not just threshold-filtered opps)
        if best_net is not None and best_net > state.spread_history[token]["max_net"]:
            state.spread_history[token]["max_net"] = best_net

        # Session high
        sh_net = state.spread_history[token]["max_net"]
        session_high_net = round(sh_net, 4) if sh_net > -999 else None

        token_data[token] = {
            "category": TOKEN_CATEGORY[token],
            "exchanges": exchanges_data,
            "spread_pairs": spread_pairs,
            "best_net": round(best_net, 4) if best_net is not None else None,
            "best_net_label": best_pair_entry["label"] if best_pair_entry else None,
            "best_gross": round(best_pair_entry["gross"], 4) if best_pair_entry and best_pair_entry["gross"] is not None else None,
            "best_fees": round(best_pair_entry["fees"], 4) if best_pair_entry else None,
            "session_high_net": session_high_net,
            "opp_count": state.opp_count.get(token, 0),
            "opp_best": round(state.opp_best[token], 4) if token in state.opp_best else None,
            "opp_last": state.opp_last.get(token),
        }

    # Exchange connectivity summaries
    exchange_meta = {}
    for ex in ENABLED_EXCHANGES:
        connected = sum(1 for s in state.ws_status[ex].values() if s == "connected")
        total = len(state.supported_tokens.get(ex, []))
        exchange_meta[ex] = {
            "label": EXCHANGES[ex]["label"],
            "quote": EXCHANGES[ex]["quote"],
            "connected": connected,
            "total": total,
        }

    # Fee model — per-pair fees
    pair_fees_map = {}
    for (a, b), fee in PAIR_FEES.items():
        key = f"{a}_{b}"
        if key not in pair_fees_map:
            pair_fees_map[key] = {
                "ex_a": a, "ex_b": b,
                "label": f"{EXCHANGES[a]['label']}↔{EXCHANGES[b]['label']}",
                "total": round(fee, 4),
            }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime,
        "threshold": threshold,

        # Exchange info
        "exchanges_list": ENABLED_EXCHANGES,
        "exchange_meta": exchange_meta,
        "pair_fees": pair_fees_map,

        "total_tokens": len(TOKENS),
        "update_count": state.update_count.copy(),

        # USDT/USDC peg
        "usdt_usdc_rate": usdt_usdc,

        # Opportunity summary
        "opp_total": state.opp_total,

        # Structure metadata
        "categories": CATEGORIES,
        "tokens": TOKENS,

        # Per-token data
        "token_data": token_data,
    }


async def broadcast_state():
    """Broadcast full LiveState JSON to all connected WebSocket clients at 10fps."""
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
    """Start all exchange feeds, opportunity detector, and broadcast loop."""
    threshold_config["value"] = threshold

    tasks = []
    exchange_objects = {}   # name -> ccxt exchange or adapter instance

    # ── Initialize ccxt.pro exchanges ──────────────────────────
    for ex_name in ENABLED_EXCHANGES:
        cfg = EXCHANGES[ex_name]
        if cfg["ccxt_id"] is None:
            continue  # handled separately (e.g. dextrade)

        ccxt_class = getattr(ccxt, cfg["ccxt_id"])
        ccxt_config = {
            "options": cfg.get("options", {}),
        }
        if cfg.get("api_key"):
            ccxt_config["apiKey"] = cfg["api_key"]
        if cfg.get("api_secret"):
            ccxt_config["secret"] = cfg["api_secret"]

        exchange_obj = ccxt_class(ccxt_config)
        exchange_objects[ex_name] = exchange_obj

        # Load markets to check which tokens are available
        try:
            await exchange_obj.load_markets()
            available = set()
            for token in TOKENS:
                symbol = build_pair_symbol(token, ex_name)
                if symbol in exchange_obj.markets:
                    available.add(token)
            state.supported_tokens[ex_name] = available
            print(f"[ws_server] {ex_name}: {len(available)}/{len(TOKENS)} tokens available")
        except Exception as e:
            print(f"[ws_server] {ex_name}: failed to load markets: {e}")
            state.supported_tokens[ex_name] = set(TOKENS)  # assume all available

    # ── Initialize Dex-Trade adapter ───────────────────────────
    dextrade_adapter = None
    if "dextrade" in ENABLED_EXCHANGES:
        cfg = EXCHANGES["dextrade"]
        dextrade_adapter = DexTradeAdapter(
            api_key=cfg.get("api_key"),
            api_secret=cfg.get("api_secret"),
        )
        exchange_objects["dextrade"] = dextrade_adapter

        # Load available markets
        available_pairs = await dextrade_adapter.load_markets()
        available_tokens = set()
        for token in TOKENS:
            pair = build_pair_symbol(token, "dextrade")
            if dextrade_adapter.has_pair(pair):
                available_tokens.add(token)
        state.supported_tokens["dextrade"] = available_tokens
        print(f"[ws_server] dextrade: {len(available_tokens)}/{len(TOKENS)} tokens available")

    # ── Start WebSocket broadcast server ───────────────────────
    server = await websockets.serve(ws_handler, "127.0.0.1", port)
    print(f"[ws_server] ⚡ WebSocket server running on ws://127.0.0.1:{port}")
    print(f"[ws_server] Subscribing to orderbooks on {', '.join(ENABLED_EXCHANGES)}...")
    print(f"[ws_server] Exchange pairs: {len(EXCHANGE_PAIRS)} ({', '.join(f'{a}↔{b}' for a, b in EXCHANGE_PAIRS)})")
    print(f"[ws_server] Threshold: {threshold}%  |  Broadcast: {int(1/WS_BROADCAST_INTERVAL)}fps")
    print(f"[ws_server] Opportunity log: {OPP_LOG_FILE}")

    # ── Launch orderbook feeds ─────────────────────────────────
    for ex_name in ENABLED_EXCHANGES:
        cfg = EXCHANGES[ex_name]
        supported = state.supported_tokens.get(ex_name, set())

        if ex_name == "dextrade" and dextrade_adapter:
            # REST polling for Dex-Trade
            for token in TOKENS:
                if token not in supported:
                    continue
                pair = build_pair_symbol(token, "dextrade")
                tasks.append(asyncio.create_task(
                    watch_dextrade_book(dextrade_adapter, token, pair)
                ))
        elif cfg["ccxt_id"] is not None:
            # ccxt.pro WebSocket feed
            exchange_obj = exchange_objects[ex_name]
            for token in TOKENS:
                if token not in supported:
                    continue
                symbol = build_pair_symbol(token, ex_name)
                tasks.append(asyncio.create_task(
                    watch_orderbook(exchange_obj, ex_name, token, symbol)
                ))

    # ── USDT/USDC rate tracker (use Binance) ───────────────────
    if "binance" in exchange_objects:
        tasks.append(asyncio.create_task(watch_usdt_usdc(exchange_objects["binance"])))

    # ── Opportunity detector ───────────────────────────────────
    tasks.append(asyncio.create_task(opportunity_detector()))

    # ── Broadcast loop ─────────────────────────────────────────
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

        # Close all exchange connections
        for name, obj in exchange_objects.items():
            try:
                await obj.close()
            except Exception:
                pass

        # Print session summary
        uptime = int(time.monotonic() - state.started_at)
        print(f"\n{'═' * 60}")
        print(f"  SESSION SUMMARY")
        print(f"{'─' * 60}")
        print(f"  Uptime         : {uptime // 3600}h{(uptime % 3600) // 60:02d}m{uptime % 60:02d}s")
        print(f"  Exchanges      : {', '.join(ENABLED_EXCHANGES)}")
        print(f"  Total opps     : {state.opp_total}")
        for t in TOKENS:
            c = state.opp_count.get(t, 0)
            b = state.opp_best.get(t, 0)
            if c > 0:
                print(f"    {t:<8}: {c:>4} opps  |  best net: {b:+.3f}%")
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
