"""
app/transport/ws_server.py — WebSocket Server
===============================================
Handles client connections, incoming messages, and broadcasting.
Decoupled from opportunity detection and exchange feeds.
"""

import asyncio
import json
import websockets
from typing import Set, Any
from datetime import datetime, timezone

from app.config import get_config
from app.engine.state import get_state
from app.db import opportunity_repo
from app.transport.serializer import serialize_state


class WebSocketServer:
    """
    Manages WebSocket clients, handles incoming requests, and broadcasts state.
    """

    def __init__(self, detector):
        self.cfg = get_config()
        self.state = get_state()
        self.detector = detector
        self.connected_clients: Set[Any] = set()

    async def start(self) -> None:
        """Start the WebSocket server."""
        # Restore wallet balances from DB before accepting connections
        await self.state.restore_balances_from_db()
        
        server = await websockets.serve(self._ws_handler, "127.0.0.1", self.cfg.WS_PORT)
        print(f"[transport] ⚡ WebSocket server running on ws://127.0.0.1:{self.cfg.WS_PORT}")
        
        # Start broadcast loop
        asyncio.create_task(self._broadcast_loop())
        
        # Keep alive
        await asyncio.Future()

    def broadcast_opportunity(self, payload: str) -> None:
        """Broadcast a new opportunity payload to all connected clients."""
        if self.connected_clients:
            websockets.broadcast(self.connected_clients, payload)

    async def _broadcast_loop(self) -> None:
        """Broadcast full LiveState JSON to all connected clients at configured FPS."""
        await asyncio.sleep(3)  # wait for state to populate
        
        while True:
            if self.connected_clients:
                try:
                    state_payload = serialize_state(self.state, self.detector.current_threshold)
                    websockets.broadcast(self.connected_clients, json.dumps(state_payload))
                except Exception as e:
                    print(f"[transport] Broadcast error: {e}")
            await asyncio.sleep(self.cfg.WS_BROADCAST_INTERVAL)

    async def _ws_handler(self, websocket) -> None:
        """Bidirectional WS handler — receives client requests."""
        self.connected_clients.add(websocket)
        remote = websocket.remote_address
        print(f"[transport] Client connected: {remote} ({len(self.connected_clients)} total)")
        
        try:
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    msg_type = msg.get("type")
                    
                    if msg_type == "set_threshold":
                        self.detector.set_threshold(float(msg.get("value", self.cfg.DEFAULT_THRESHOLD)))
                        
                    elif msg_type == "get_recent_opportunities":
                        limit = min(200, max(1, int(msg.get("limit", 100))))
                        logs = await opportunity_repo.get_recent(limit)
                        await websocket.send(json.dumps({
                            "type": "recent_opportunities",
                            "data": logs
                        }))
                        
                    elif msg_type == "get_analytics":
                        analytics = await opportunity_repo.run_analytics()
                        await websocket.send(json.dumps({
                            "type": "analytics_data",
                            "data": analytics
                        }))
                        
                    elif msg_type == "get_timeseries":
                        token = msg.get("token", "SOL")
                        interval = msg.get("interval", "5 minutes")
                        limit = min(500, max(1, int(msg.get("limit", 100))))
                        timeseries = await opportunity_repo.get_timeseries_data(token, interval, limit)
                        await websocket.send(json.dumps({
                            "type": "timeseries_data",
                            "data": { "token": token, "interval": interval, "series": timeseries }
                        }))
                        
                    elif msg_type == "get_consistency":
                        limit = min(50, max(1, int(msg.get("limit", 10))))
                        consistency = await opportunity_repo.get_consistency_metrics(limit)
                        await websocket.send(json.dumps({
                            "type": "consistency_data",
                            "data": consistency
                        }))

                    elif msg_type == "get_pnl_analytics":
                        from app.db.order_repo import get_pnl_analytics
                        timeframe = msg.get("timeframe", "all")
                        exchange_filter = msg.get("exchange", "all")
                        
                        start_time = None
                        if timeframe == "session":
                            # Use state.started_at (unix timestamp) converted to datetime
                            start_time = datetime.fromtimestamp(self.state.started_at, tz=timezone.utc)
                            
                        data = await get_pnl_analytics(timeframe, exchange_filter, start_time)
                        await websocket.send(json.dumps({
                            "type": "pnl_analytics_data",
                            "data": data,
                            "timeframe": timeframe,
                            "exchange": exchange_filter
                        }))

                    elif msg_type == "toggle_autotrader":
                        self.state.auto_trade_enabled = bool(msg.get("enabled", False))
                        websockets.broadcast(self.connected_clients, json.dumps({
                            "type": "autotrader_status",
                            "enabled": self.state.auto_trade_enabled
                        }))

                    elif msg_type == "toggle_pro_mode":
                        self.state.is_pro_mode = bool(msg.get("enabled", False))
                        websockets.broadcast(self.connected_clients, json.dumps({
                            "type": "pro_mode_status",
                            "enabled": self.state.is_pro_mode
                        }))

                    elif msg_type == "kill_switch":
                        self.state.auto_trade_enabled = False
                        self.state.active_trades.clear()
                        # Real implementation would also cancel open orders on exchanges
                        websockets.broadcast(self.connected_clients, json.dumps({
                            "type": "kill_switch_activated"
                        }))
                        
                    elif msg_type == "get_trade_state":
                        from app.db.order_repo import get_recent_trades, get_active_rebalances, get_recent_rebalances
                        trades = await get_recent_trades(50)
                        rebalances = await get_active_rebalances()
                        rebalance_history = await get_recent_rebalances(20)
                        
                        # Merge trades and rebalance events, sort by time
                        all_entries = trades + rebalance_history
                        all_entries.sort(key=lambda x: x.get("trade_time", ""), reverse=True)
                        
                        await websocket.send(json.dumps({
                            "type": "trade_state_data",
                            "data": {
                                "active_trades": list(self.state.active_trades.values()),
                                "history": all_entries[:50],
                                "rebalances": rebalances,
                                "balances": self.state.balances
                            }
                        }))
                        
                    elif msg_type == "reset_mock_wallets":
                        self.state.auto_trade_enabled = False
                        await self.state.reset_mock_wallets()
                        websockets.broadcast(self.connected_clients, json.dumps({
                            "type": "mock_wallets_reset",
                            "balances": self.state.balances
                        }))

                    elif msg_type == "reset_logs":
                        await opportunity_repo.reset()
                        
                        # Reset memory state
                        self.state.opp_total = 0
                        self.state.opp_count = {t: 0 for t in self.state.tokens}
                        self.state.opp_best = {}
                        self.state.spread_history = {t: {"max_net": -999.0} for t in self.state.tokens}
                        
                        websockets.broadcast(self.connected_clients, json.dumps({"type": "logs_reset"}))
                        
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    print(f"[transport] Message parse error: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.discard(websocket)
            print(f"[transport] Client disconnected: {remote} ({len(self.connected_clients)} total)")
