"""
main.py — Unified Pippin Arbitrage Bot Entrypoint
===================================================
Initializes the database, connects to exchange plugins,
and starts the WebSocket server + opportunity detector.
"""

import asyncio
import sys

from app.config import get_config
from app.db import init_db, close_db
from app.engine.state import get_state
from app.engine.detector import OpportunityDetector
from app.db.opportunity_repo import cleanup_old_data
from app.db.order_repo import cleanup_old_orders
from app.exchanges.registry import ExchangeRegistry
from app.transport.ws_server import WebSocketServer
from app.lib.logger import setup_logging


async def main(threshold: float, port: int):
    # Setup structured logging
    setup_logging()

    # Load config and override from args
    cfg = get_config()
    cfg.DEFAULT_THRESHOLD = threshold
    cfg.WS_PORT = port

    print("\n" + "═" * 60)
    print("  PAAL-V2: Multi-Exchange Arbitrage Engine")
    print("═" * 60)
    print(f"  Mode      : {'PAPER TRADING (mock)' if cfg.MOCK_MODE else 'LIVE TRADING'}")
    print(f"  Threshold : {cfg.DEFAULT_THRESHOLD}%")
    print(f"  Storage   : TimescaleDB")

    # 1. Initialize Database
    pool = await init_db()
    if pool is None:
        print("[main] FATAL: Could not connect to TimescaleDB. Exiting.")
        return

    # 2. Load and connect exchange plugins
    registry = ExchangeRegistry()
    registry.load_from_config()
    print(f"  Exchanges : {', '.join(registry.list_enabled())}")
    
    await registry.initialize_all()

    # Share active tokens with state
    state = get_state()
    for ex_name, plugin in registry.plugins.items():
        state.supported_tokens[ex_name] = {
            t for t in state.tokens if plugin.has_pair(t)
        }
        print(f"  [{ex_name}] : {len(state.supported_tokens[ex_name])}/{len(state.tokens)} tokens supported")

    # 3. Setup Detector & WebSocket Server
    # Pass ws server's broadcast function to detector so it can emit events
    ws_server = WebSocketServer(detector=None) # We'll set detector after init
    detector = OpportunityDetector(broadcast_callback=ws_server.broadcast_opportunity)
    ws_server.detector = detector

    print("═" * 60)

    # 4. Start concurrent tasks
    tasks = []
    
    # WebSocket Server
    tasks.append(asyncio.create_task(ws_server.start()))
    
    # Opportunity Detector Loop
    tasks.append(asyncio.create_task(detector.run()))

    # DB Cleanup Loop (runs once a day)
    tasks.append(asyncio.create_task(_db_cleanup_loop()))

    # Orderbook feed loops for each plugin
    for name, plugin in registry.plugins.items():
        if hasattr(plugin, "watch_orderbook"):
            for token in state.tokens:
                if token in state.supported_tokens[name]:
                    symbol = plugin.build_symbol(token)
                    tasks.append(asyncio.create_task(_watch_feed(plugin, token, symbol)))

    # USDT/USDC Peg Tracker (use Binance if available)
    if "binance" in registry.plugins:
        tasks.append(asyncio.create_task(_watch_peg(registry.plugins["binance"])))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[main] Shutting down...")
        detector.stop()
        for task in tasks:
            task.cancel()
        
        await registry.close_all()
        await close_db()
        print("[main] Server stopped cleanly.")


async def _watch_feed(plugin, token: str, symbol: str):
    """Feed watcher wrapper."""
    state = get_state()
    while True:
        try:
            ob = await plugin.watch_orderbook(token, symbol)
            if ob and ob.get("bid") is not None:
                state.exchanges[plugin.name][token] = ob
                state.ws_status[plugin.name][token] = "connected"
                state.update_count[plugin.name] += 1
        except asyncio.CancelledError:
            break
        except Exception as e:
            state.ws_status[plugin.name][token] = "error"
            await asyncio.sleep(5)

async def _db_cleanup_loop():
    """Periodically cleans up old DB data to prevent disk exhaustion."""
    while True:
        try:
            print("[main] Running periodic DB cleanup...")
            await cleanup_old_data(days=7)
            await cleanup_old_orders(days=30)
            print("[main] DB cleanup complete. Sleeping for 24 hours.")
        except Exception as e:
            print(f"[main] DB cleanup failed: {e}")
        
        # Sleep for 24 hours
        try:
            await asyncio.sleep(86400)
        except asyncio.CancelledError:
            break


async def _watch_peg(binance_plugin):
    """USDT/USDC peg tracker."""
    state = get_state()
    exchange = binance_plugin.exchange_obj
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pippin Arbitrage Bot")
    parser.add_argument("--threshold", type=float, default=0.001, help="Minimum net spread % to trigger opportunity")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port")
    args = parser.parse_args()

    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    try:
        asyncio.run(main(args.threshold, args.port))
    except KeyboardInterrupt:
        print("\n[main] Execution stopped.")
