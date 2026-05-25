"""
app/db/order_repo.py — Order Repository
=========================================
CRUD operations for the `orders` table.
Tracks order lifecycle for arbitrage trade execution.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.db.pool import get_pool
from app.models.order import ORDER_INSERT_SQL, ORDER_UPDATE_STATUS_SQL, OrderStatus


async def insert_order(order_dict: dict) -> None:
    """
    Insert a new order record into TimescaleDB.

    Args:
        order_dict: Dict from Order.to_dict()
    """
    pool = get_pool()
    if pool is None:
        return

    ts = order_dict.get("created_at")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif ts is None:
        ts = datetime.now(timezone.utc)

    await pool.execute(
        ORDER_INSERT_SQL,
        ts,
        order_dict["order_id"],
        order_dict.get("trade_id", ""),
        order_dict["exchange"],
        order_dict["side"],
        order_dict["symbol"],
        float(order_dict["qty"]),
        float(order_dict["price"]),
        order_dict.get("status", "pending"),
        float(order_dict.get("filled_qty", 0)),
        float(order_dict.get("filled_price", 0)),
        float(order_dict.get("fee", 0)),
        float(order_dict["net_pnl"]) if order_dict.get("net_pnl") is not None else None,
        order_dict.get("is_mock", True),
        order_dict.get("error"),
    )


async def update_status(
    order_id: str,
    status: str,
    filled_qty: float = 0.0,
    filled_price: float = 0.0,
    fee: float = 0.0,
    net_pnl: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Update an order's status and fill information."""
    pool = get_pool()
    if pool is None:
        return

    await pool.execute(
        ORDER_UPDATE_STATUS_SQL,
        order_id,
        status,
        filled_qty,
        filled_price,
        fee,
        net_pnl,
        error,
    )


async def get_by_trade(trade_id: str) -> List[dict]:
    """Get all orders belonging to a trade (buy + sell legs)."""
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch(
        """
        SELECT order_id, trade_id, exchange, side, symbol,
               qty, price, status, filled_qty, filled_price, fee,
               net_pnl, is_mock, error, created_at, updated_at
        FROM orders
        WHERE trade_id = $1
        ORDER BY created_at ASC
        """,
        trade_id,
    )

    return [
        {
            "order_id":     row["order_id"],
            "trade_id":     row["trade_id"],
            "exchange":     row["exchange"],
            "side":         row["side"],
            "symbol":       row["symbol"],
            "qty":          float(row["qty"]),
            "price":        float(row["price"]),
            "status":       row["status"],
            "filled_qty":   float(row["filled_qty"]),
            "filled_price": float(row["filled_price"]),
            "fee":          float(row["fee"]),
            "net_pnl":      float(row["net_pnl"]) if row["net_pnl"] is not None else None,
            "is_mock":      row["is_mock"],
            "error":        row["error"],
            "created_at":   row["created_at"].isoformat(),
            "updated_at":   row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


async def get_open_orders() -> List[dict]:
    """Get all orders with status PENDING or OPEN."""
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch(
        """
        SELECT order_id, trade_id, exchange, side, symbol,
               qty, price, status, created_at
        FROM orders
        WHERE status IN ('pending', 'open')
        ORDER BY created_at DESC
        """
    )

    return [dict(row) for row in rows]


async def get_recent_trades(limit: int = 50) -> List[dict]:
    """Get recent completed trades grouped by trade_id."""
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch(
        """
        SELECT o.trade_id,
               MIN(o.created_at) AS trade_time,
               MAX(CASE WHEN o.side = 'buy' THEN o.exchange END) AS ex_buy,
               MAX(CASE WHEN o.side = 'sell' THEN o.exchange END) AS ex_sell,
               MAX(CASE WHEN o.side = 'buy' THEN o.status END) AS buy_status,
               MAX(CASE WHEN o.side = 'sell' THEN o.status END) AS sell_status,
               SUM(CASE WHEN o.side = 'buy' THEN o.filled_qty * o.filled_price ELSE 0 END) AS buy_value,
               SUM(CASE WHEN o.side = 'sell' THEN o.filled_qty * o.filled_price ELSE 0 END) AS sell_value,
               SUM(CASE WHEN o.side = 'buy' THEN o.filled_qty ELSE 0 END) AS buy_qty,
               SUM(CASE WHEN o.side = 'sell' THEN o.filled_qty ELSE 0 END) AS sell_qty,
               SUM(o.fee) AS total_fees,
               MAX(tg.realized_pnl) AS net_pnl,
               MAX(tg.token) AS token,
               BOOL_AND(o.is_mock) AS is_mock
        FROM orders o
        LEFT JOIN trade_groups tg ON o.trade_id = tg.trade_id
        WHERE o.status IN ('filled', 'partial', 'pending', 'open', 'failed')
          AND o.trade_id != ''
        GROUP BY o.trade_id
        ORDER BY trade_time DESC
        LIMIT $1
        """,
        limit,
    )

    result = []
    for row in rows:
        d = dict(row)
        if hasattr(d.get("trade_time"), "isoformat"):
            d["trade_time"] = d["trade_time"].isoformat()
        result.append(d)
        
    return result


async def insert_trade_group(trade_dict: dict) -> None:
    pool = get_pool()
    if pool is None:
        return
        
    ts = trade_dict.get("created_at")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif ts is None:
        ts = datetime.now(timezone.utc)

    await pool.execute(
        """
        INSERT INTO trade_groups (
            trade_id, created_at, token, route, target_spread,
            status, realized_pnl, is_mock
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        trade_dict["trade_id"],
        ts,
        trade_dict["token"],
        trade_dict["route"],
        float(trade_dict["target_spread"]),
        trade_dict.get("status", "executing"),
        float(trade_dict["realized_pnl"]) if trade_dict.get("realized_pnl") is not None else None,
        trade_dict.get("is_mock", True),
    )


async def update_trade_group_status(trade_id: str, status: str, realized_pnl: Optional[float] = None) -> None:
    pool = get_pool()
    if pool is None:
        return
    await pool.execute(
        "UPDATE trade_groups SET status = $2, realized_pnl = $3 WHERE trade_id = $1",
        trade_id, status, realized_pnl
    )


async def insert_rebalance_transfer(transfer_dict: dict) -> None:
    pool = get_pool()
    if pool is None:
        return

    ts = transfer_dict.get("created_at")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif ts is None:
        ts = datetime.now(timezone.utc)

    await pool.execute(
        """
        INSERT INTO rebalance_transfers (
            transfer_id, created_at, updated_at, asset, amount,
            source_ex, dest_ex, status, tx_hash, is_mock
        ) VALUES ($1, $2, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        transfer_dict["transfer_id"],
        ts,
        transfer_dict["asset"],
        float(transfer_dict["amount"]),
        transfer_dict["source_ex"],
        transfer_dict["dest_ex"],
        transfer_dict.get("status", "pending"),
        transfer_dict.get("tx_hash"),
        transfer_dict.get("is_mock", True),
    )


async def get_active_rebalances() -> List[dict]:
    pool = get_pool()
    if pool is None:
        return []
    rows = await pool.fetch("SELECT * FROM rebalance_transfers WHERE status = 'pending' ORDER BY created_at DESC")
    result = []
    for row in rows:
        d = dict(row)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        if hasattr(d.get("updated_at"), "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        result.append(d)
    return result


async def get_wallet_deltas() -> List[dict]:
    """
    Reconstruct net wallet changes from all filled mock orders.
    Returns per-exchange USDT and token deltas to apply on top of initial $250.
    """
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch("""
        SELECT exchange, symbol,
               SUM(CASE WHEN side='buy' THEN -(filled_qty * filled_price) ELSE (filled_qty * filled_price) END) AS usdt_delta,
               SUM(CASE WHEN side='buy' THEN filled_qty ELSE -filled_qty END) AS token_delta
        FROM orders
        WHERE is_mock = true AND status = 'filled'
        GROUP BY exchange, symbol
    """)
    return [dict(r) for r in rows]


async def get_rebalance_deltas() -> List[dict]:
    """
    Reconstruct net wallet changes from completed rebalance transfers.
    """
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch("""
        SELECT source_ex, dest_ex, asset, SUM(amount) as total_amount
        FROM rebalance_transfers
        WHERE is_mock = true AND status = 'completed'
        GROUP BY source_ex, dest_ex, asset
    """)
    return [dict(r) for r in rows]


async def update_rebalance_status(transfer_id: str, status: str) -> None:
    """Update a rebalance transfer's status (e.g. pending -> completed)."""
    pool = get_pool()
    if pool is None:
        return
    await pool.execute(
        "UPDATE rebalance_transfers SET status = $2, updated_at = NOW() WHERE transfer_id = $1",
        transfer_id, status
    )


async def get_recent_rebalances(limit: int = 20) -> List[dict]:
    """Get recent rebalance transfers for trade ledger display."""
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch("""
        SELECT transfer_id, created_at, asset, amount,
               source_ex, dest_ex, status, is_mock
        FROM rebalance_transfers
        ORDER BY created_at DESC
        LIMIT $1
    """, limit)

    result = []
    for row in rows:
        d = {
            "trade_id": row["transfer_id"][:12],
            "trade_time": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            "ex_buy": row["dest_ex"],
            "ex_sell": row["source_ex"],
            "buy_status": row["status"],
            "sell_status": row["status"],
            "buy_value": float(row["amount"]),
            "sell_value": float(row["amount"]),
            "buy_qty": float(row["amount"]),
            "sell_qty": float(row["amount"]),
            "total_fees": 0.0,
            "net_pnl": 0.0,
            "token": row["asset"],
            "is_mock": row["is_mock"],
            "is_rebalance": True,
        }
        result.append(d)
    return result

async def get_pnl_analytics(timeframe: str, exchange_filter: str, start_time: Optional[datetime] = None) -> List[dict]:
    """
    Get aggregated PnL by token, filtered by timeframe and exchange.
    timeframe: 'session', 'day', 'week', 'month', 'all'
    exchange_filter: 'all', or specific exchange name (e.g. 'binance')
    """
    pool = get_pool()
    if pool is None:
        return []

    query = """
        SELECT token,
               SUM(realized_pnl) as total_pnl,
               COUNT(*) as trade_count
        FROM trade_groups
        WHERE realized_pnl IS NOT NULL
          AND status = 'completed'
    """
    params = []
    param_idx = 1

    if timeframe != 'all':
        if timeframe == 'session' and start_time:
            query += f" AND created_at >= ${param_idx}"
            params.append(start_time)
            param_idx += 1
        elif timeframe == 'day':
            query += f" AND created_at >= NOW() - INTERVAL '1 day'"
        elif timeframe == 'week':
            query += f" AND created_at >= NOW() - INTERVAL '7 days'"
        elif timeframe == 'month':
            query += f" AND created_at >= NOW() - INTERVAL '30 days'"

    if exchange_filter and exchange_filter != 'all':
        query += f" AND route LIKE ${param_idx}"
        params.append(f"%{exchange_filter}%")
        param_idx += 1

    query += " GROUP BY token ORDER BY total_pnl DESC"

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]
