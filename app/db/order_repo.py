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
        SELECT trade_id,
               MIN(created_at) AS trade_time,
               SUM(CASE WHEN side = 'buy' THEN filled_qty * filled_price ELSE 0 END) AS buy_value,
               SUM(CASE WHEN side = 'sell' THEN filled_qty * filled_price ELSE 0 END) AS sell_value,
               SUM(fee) AS total_fees,
               MAX(net_pnl) AS net_pnl,
               BOOL_AND(is_mock) AS is_mock
        FROM orders
        WHERE status IN ('filled', 'partial')
          AND trade_id != ''
        GROUP BY trade_id
        ORDER BY trade_time DESC
        LIMIT $1
        """,
        limit,
    )

    return [dict(row) for row in rows]
