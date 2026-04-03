"""
price_gap_monitor.py — Live Cross-Exchange Price Gap Monitor (WebSocket)
Uses WebSocket streams from Binance and Backpack for real-time orderbook
updates. Counts and logs all potential arbitrage opportunities to CSV.

Usage:
    python price_gap_monitor.py
    python price_gap_monitor.py --threshold 0.3   # highlight gaps > 0.3%

Press Ctrl+C to stop.
"""
import asyncio
import csv
import sys
import os
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt.pro as ccxt  # ccxt.pro = WebSocket support

# ── Configuration ────────────────────────────────────────────────
TOKENS = ["SOL", "PYTH", "JTO", "JUP", "RENDER"]

# Binance uses USDT, Backpack uses USDC
BINANCE_PAIRS  = {t: f"{t}/USDT" for t in TOKENS}
BACKPACK_PAIRS = {t: f"{t}/USDC" for t in TOKENS}

DEFAULT_THRESHOLD = 0.3    # % spread to highlight in green
DISPLAY_REFRESH   = 0.1    # refresh screen every 100ms (10fps)

# Opportunity detection: any gross spread > 0% is a potential opportunity
# Minimum positive spread to count as an opportunity
OPP_MIN_SPREAD    = 0.0    # log ANY positive spread (even tiny)
OPP_LOG_FILE      = "logs/opportunities.csv"

# ── ANSI Colors ──────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"
BG_GREEN = "\033[42m"
BG_RED   = "\033[41m"

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
    """Thread-safe shared state for all WebSocket feeds."""

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
        self.opp_count     = {t: 0 for t in TOKENS}   # per-token count
        self.opp_total     = 0                          # grand total
        self.opp_last      = {}                         # token -> last opp dict
        self.opp_best      = {}                         # token -> best spread ever


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


# ── Display helpers ──────────────────────────────────────────────

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def format_price(price, decimals=4):
    if price is None:
        return f"{'N/A':>11}"
    return f"{price:>{11}.{decimals}f}"


def format_spread(spread_pct, threshold):
    if spread_pct is None:
        return f"{'N/A':>8}"
    sign = "+" if spread_pct >= 0 else ""
    s = f"{sign}{spread_pct:.3f}%"
    if spread_pct >= threshold:
        return f"{BG_GREEN}{BOLD}{s:>8}{RESET}"
    elif spread_pct >= threshold * 0.5:
        return f"{GREEN}{s:>8}{RESET}"
    elif spread_pct > 0:
        return f"{YELLOW}{s:>8}{RESET}"
    else:
        return f"{RED}{s:>8}{RESET}"


def staleness_indicator(updated: Optional[float]) -> str:
    if updated is None:
        return f"{RED}●{RESET}"
    age = time.monotonic() - updated
    if age < 2:
        return f"{GREEN}●{RESET}"
    elif age < 5:
        return f"{YELLOW}●{RESET}"
    else:
        return f"{RED}●{RESET}"


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
    and logs them to CSV + updates counters.
    Runs at ~20 checks/sec to catch fleeting opportunities.
    """
    COMBINED_FEE_PCT = 0.20  # 0.1% Binance taker + 0.1% Backpack taker

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

            # Check each direction
            for spread, direction in [
                (spread_buy_bin, "BuyBIN→SellBP"),
                (spread_buy_bp,  "BuyBP→SellBIN"),
            ]:
                if spread <= OPP_MIN_SPREAD:
                    continue

                now = time.monotonic()
                # Debounce: 1 second between logs for the same token
                if now - last_logged[token] < 1.0:
                    continue

                last_logged[token] = now
                net_spread = spread - COMBINED_FEE_PCT

                # Update counters
                state.opp_count[token] += 1
                state.opp_total += 1

                # Track best
                prev_best = state.opp_best.get(token, -999)
                if spread > prev_best:
                    state.opp_best[token] = spread

                # Store last opportunity info
                state.opp_last[token] = {
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "spread": spread,
                    "net": net_spread,
                    "direction": direction,
                }

                # Log to CSV
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


# ── Display loop ─────────────────────────────────────────────────

async def display_loop(threshold: float):
    """Render the live dashboard from shared state."""
    cycle = 0
    spread_history = {t: {"max_buy_bin": -999, "max_buy_bp": -999} for t in TOKENS}

    await asyncio.sleep(3)  # let WebSockets warm up

    while True:
        cycle += 1
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        uptime = int(time.monotonic() - state.started_at)
        uptime_str = f"{uptime // 3600}h{(uptime % 3600) // 60:02d}m{uptime % 60:02d}s"

        bin_updates = state.update_count["binance"]
        bp_updates  = state.update_count["backpack"]
        usdt_usdc   = state.usdt_usdc_rate

        clear_screen()

        # Header
        print(f"{BOLD}{CYAN}{'═' * 130}{RESET}")
        print(f"{BOLD}{CYAN}  ⚡ LIVE PRICE GAP MONITOR (WebSocket)  │  Binance ↔ Backpack  │  {now}  │  ⏱ {uptime_str}{RESET}")
        print(f"{BOLD}{CYAN}{'═' * 130}{RESET}")

        # Status bar
        bin_connected = sum(1 for s in state.ws_status["binance"].values() if s == "connected")
        bp_connected  = sum(1 for s in state.ws_status["backpack"].values() if s == "connected")
        peg_dev = (usdt_usdc - 1.0) * 100
        peg_color = GREEN if abs(peg_dev) < 0.05 else YELLOW if abs(peg_dev) < 0.1 else RED

        print(f"  {DIM}WS: BIN {GREEN if bin_connected == len(TOKENS) else YELLOW}{bin_connected}/{len(TOKENS)}{RESET}{DIM}"
              f"  BP {GREEN if bp_connected == len(TOKENS) else YELLOW}{bp_connected}/{len(TOKENS)}{RESET}{DIM}"
              f"  │  Ticks: BIN={bin_updates:,}  BP={bp_updates:,}"
              f"  │  USDT/USDC: {peg_color}{usdt_usdc:.6f} ({peg_dev:+.4f}%){RESET}{DIM}"
              f"  │  Threshold: ≥{threshold}%"
              f"  │  {GREEN}Opportunities: {state.opp_total}{RESET}")
        print()

        # Table header
        hdr = (
            f"  {BOLD}{'':>1} {'Token':<7}"
            f"{'BIN Bid':>11} {'BIN Ask':>11}"
            f" │ "
            f"{'BP Bid':>11} {'BP Ask':>11}"
            f" │ "
            f"{'BuyBIN→BP':>10} {'BuyBP→BIN':>10}"
            f" │ "
            f"{'SessHigh':>9}"
            f" {'Opps':>5}"
            f" {'BestOpp':>8}"
            f" {'LastOpp':>16}"
            f"{RESET}"
        )
        print(hdr)
        print(f"  {'─' * 126}")

        best_token = None
        best_spread = -999
        best_direction = ""

        for token in TOKENS:
            bd = state.binance.get(token, {})
            pd = state.backpack.get(token, {})

            b_bid = bd.get("bid")
            b_ask = bd.get("ask")
            p_bid = pd.get("bid")
            p_ask = pd.get("ask")

            b_dot = staleness_indicator(bd.get("updated"))
            p_dot = staleness_indicator(pd.get("updated"))

            if b_bid and b_ask and p_bid and p_ask:
                p_bid_usdt = p_bid / usdt_usdc
                p_ask_usdt = p_ask / usdt_usdc

                spread_buy_bin = ((p_bid_usdt - b_ask) / b_ask) * 100
                spread_buy_bp = ((b_bid - p_ask_usdt) / p_ask_usdt) * 100

                if spread_buy_bin > spread_history[token]["max_buy_bin"]:
                    spread_history[token]["max_buy_bin"] = spread_buy_bin
                if spread_buy_bp > spread_history[token]["max_buy_bp"]:
                    spread_history[token]["max_buy_bp"] = spread_buy_bp

                session_high = max(spread_history[token]["max_buy_bin"],
                                   spread_history[token]["max_buy_bp"])

                max_spread = max(spread_buy_bin, spread_buy_bp)
                if max_spread > best_spread:
                    best_spread = max_spread
                    best_token = token
                    best_direction = "BuyBIN→BP" if spread_buy_bin >= spread_buy_bp else "BuyBP→BIN"
            else:
                spread_buy_bin = None
                spread_buy_bp = None
                session_high = 0

            # Decimals based on price
            sample = b_bid or p_bid or 1
            dec = 2 if sample > 100 else (4 if sample > 1 else 6)

            session_high_str = f"{session_high:+.3f}%" if session_high > -999 else "N/A"
            session_color = GREEN if session_high >= threshold else YELLOW if session_high > 0 else DIM

            # Opportunity stats
            opp_count = state.opp_count.get(token, 0)
            opp_best  = state.opp_best.get(token, 0)
            opp_last  = state.opp_last.get(token)

            opp_count_str = f"{GREEN}{opp_count:>5}{RESET}" if opp_count > 0 else f"{DIM}{opp_count:>5}{RESET}"
            opp_best_str  = f"{GREEN}{opp_best:+.3f}%{RESET}" if opp_best > 0 else f"{DIM}{'--':>8}{RESET}"
            opp_last_str  = f"{GREEN}{opp_last['time']} {opp_last['spread']:+.2f}%{RESET}" if opp_last else f"{DIM}{'--':>16}{RESET}"

            row = (
                f"  {b_dot}{p_dot} {BOLD}{WHITE}{token:<7}{RESET}"
                f"{format_price(b_bid, dec)} {format_price(b_ask, dec)}"
                f" {DIM}│{RESET} "
                f"{format_price(p_bid, dec)} {format_price(p_ask, dec)}"
                f" {DIM}│{RESET} "
                f"{format_spread(spread_buy_bin, threshold)}"
                f"  {format_spread(spread_buy_bp, threshold)}"
                f" {DIM}│{RESET}"
                f" {session_color}{session_high_str:>9}{RESET}"
                f" {opp_count_str}"
                f" {opp_best_str}"
                f" {opp_last_str}"
            )
            print(row)

        print(f"  {'─' * 126}")

        # Best current opportunity
        if best_token and best_spread > 0:
            color = GREEN if best_spread >= threshold else YELLOW
            net = best_spread - 0.20
            net_color = GREEN if net > 0 else RED
            print(f"\n  {BOLD}⚡ Best now:{RESET} {color}{BOLD}{best_token}{RESET}"
                  f" gross {color}{best_spread:+.3f}%{RESET}"
                  f"  net {net_color}{net:+.3f}%{RESET}"
                  f"  ({best_direction})")
        else:
            print(f"\n  {DIM}No positive spread right now — monitoring...{RESET}")

        # Opportunity summary
        if state.opp_total > 0:
            opp_per_min = state.opp_total / max(1, (time.monotonic() - state.started_at) / 60)
            print(f"\n  {BOLD}{GREEN}📊 Opportunities detected: {state.opp_total}{RESET}"
                  f"  ({opp_per_min:.1f}/min)"
                  f"  │  Logged to: {CYAN}{OPP_LOG_FILE}{RESET}")
            # Per-token breakdown
            parts = []
            for t in TOKENS:
                c = state.opp_count.get(t, 0)
                if c > 0:
                    parts.append(f"{t}={c}")
            if parts:
                print(f"  {DIM}  By token: {', '.join(parts)}{RESET}")

        # Legend
        print(f"\n  {DIM}Legend: {GREEN}●{RESET}{DIM}=live  {YELLOW}●{RESET}{DIM}=stale  {RED}●{RESET}{DIM}=dead"
              f"  │  Net = Gross − 0.20% fees  │  Opps = positive gross spread events")
        print(f"  Log file: {OPP_LOG_FILE} (CSV with timestamps, prices, depths){RESET}")

        print(f"\n  {DIM}Press Ctrl+C to stop{RESET}")

        await asyncio.sleep(DISPLAY_REFRESH)


# ── Main orchestrator ────────────────────────────────────────────

async def main(threshold: float):
    """Start all WebSocket feeds, opportunity detector, and display loop."""
    binance  = ccxt.binance({"options": {"defaultType": "spot"}})
    backpack = ccxt.backpack()

    print(f"{CYAN}⚡ Starting WebSocket connections to Binance and Backpack...{RESET}")
    print(f"{DIM}   Subscribing to {len(TOKENS)} orderbooks on each exchange...{RESET}")
    print(f"{DIM}   Opportunities will be logged to: {OPP_LOG_FILE}{RESET}")

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

    # Opportunity detector (runs 20x/sec)
    tasks.append(asyncio.create_task(opportunity_detector()))

    # Display loop
    tasks.append(asyncio.create_task(display_loop(threshold)))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{YELLOW}Closing WebSocket connections...{RESET}")
        for task in tasks:
            task.cancel()
        await binance.close()
        await backpack.close()

        # Print final summary
        print(f"\n{BOLD}{'═' * 60}{RESET}")
        print(f"{BOLD}  SESSION SUMMARY{RESET}")
        print(f"{'─' * 60}")
        uptime = int(time.monotonic() - state.started_at)
        print(f"  Uptime         : {uptime // 3600}h{(uptime % 3600) // 60:02d}m{uptime % 60:02d}s")
        print(f"  Total opps     : {state.opp_total}")
        for t in TOKENS:
            c = state.opp_count.get(t, 0)
            b = state.opp_best.get(t, 0)
            print(f"    {t:<8}: {c:>4} opps  |  best: {b:+.3f}%")
        print(f"  Log file       : {OPP_LOG_FILE}")
        print(f"{'═' * 60}")
        print(f"{GREEN}Monitor stopped cleanly.{RESET}")


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    threshold = DEFAULT_THRESHOLD

    args = sys.argv[1:]
    if "--threshold" in args:
        try:
            threshold = float(args[args.index("--threshold") + 1])
        except (ValueError, IndexError):
            pass

    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    try:
        asyncio.run(main(threshold))
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Monitor stopped.{RESET}")
