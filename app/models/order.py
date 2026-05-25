"""
app/models/order.py — Order/Trade Data Model
==============================================
Represents a trade order placed on an exchange.
Tracks lifecycle: PENDING → FILLED / PARTIAL / FAILED / CANCELLED.
Maps to the `orders` table in TimescaleDB.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING   = "pending"
    OPEN      = "open"
    FILLED    = "filled"
    PARTIAL   = "partial"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """
    A single order placed on an exchange as part of an arbitrage trade.

    A complete arbitrage trade consists of two orders:
    - A BUY order on the cheap exchange
    - A SELL order on the expensive exchange

    Both orders share the same `trade_id` for correlation.
    """
    exchange:     str                              # Exchange name, e.g. "binance"
    side:         OrderSide                        # BUY or SELL
    symbol:       str                              # Trading pair, e.g. "SOL/USDT"
    qty:          float                            # Requested quantity
    price:        float                            # Limit price
    order_id:     str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    trade_id:     str = ""                         # Correlates buy+sell legs
    status:       OrderStatus = OrderStatus.PENDING
    filled_qty:   float = 0.0                      # Actually filled quantity
    filled_price: float = 0.0                      # Average fill price
    fee:          float = 0.0                      # Trading fee paid
    net_pnl:      Optional[float] = None           # PnL (set after both legs complete)
    is_mock:      bool = True                      # Paper trade flag
    error:        Optional[str] = None             # Error message if failed
    created_at:   Optional[str] = None             # ISO 8601 UTC
    updated_at:   Optional[str] = None             # ISO 8601 UTC

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def mark_filled(self, filled_qty: float, filled_price: float, fee: float) -> None:
        """Mark order as filled (full or partial)."""
        self.filled_qty = filled_qty
        self.filled_price = filled_price
        self.fee = fee
        self.status = OrderStatus.FILLED if filled_qty >= self.qty * 0.99 else OrderStatus.PARTIAL
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, error: str) -> None:
        """Mark order as failed."""
        self.status = OrderStatus.FAILED
        self.error = error
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_cancelled(self) -> None:
        """Mark order as cancelled."""
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        d = asdict(self)
        d["side"] = self.side.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        """Create from a dict."""
        return cls(
            exchange=data["exchange"],
            side=OrderSide(data["side"]),
            symbol=data["symbol"],
            qty=float(data["qty"]),
            price=float(data["price"]),
            order_id=data.get("order_id", str(uuid.uuid4())[:12]),
            trade_id=data.get("trade_id", ""),
            status=OrderStatus(data.get("status", "pending")),
            filled_qty=float(data.get("filled_qty", 0)),
            filled_price=float(data.get("filled_price", 0)),
            fee=float(data.get("fee", 0)),
            net_pnl=float(data["net_pnl"]) if data.get("net_pnl") is not None else None,
            is_mock=data.get("is_mock", True),
            error=data.get("error"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class TradeGroup:
    """
    Links two simultaneous arbitrage orders (Leg 1 and Leg 2).
    """
    trade_id:      str
    token:         str
    route:         str
    target_spread: float
    status:        str = "executing"
    realized_pnl:  Optional[float] = None
    is_mock:       bool = True
    created_at:    Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()
            
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RebalanceTransfer:
    """
    Tracks an on-chain Solana transfer to rebalance inventory skew.
    """
    transfer_id: str
    asset:       str
    amount:      float
    source_ex:   str
    dest_ex:     str
    status:      str = "pending"
    tx_hash:     Optional[str] = None
    is_mock:     bool = True
    created_at:  Optional[str] = None
    updated_at:  Optional[str] = None

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
            
    def to_dict(self) -> dict:
        return asdict(self)


# ── DB SQL ───────────────────────────────────────────────────────

ORDER_INSERT_SQL = """
    INSERT INTO orders (
        created_at, order_id, trade_id, exchange, side, symbol,
        qty, price, status, filled_qty, filled_price, fee,
        net_pnl, is_mock, error
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
"""

ORDER_UPDATE_STATUS_SQL = """
    UPDATE orders
    SET status = $2, filled_qty = $3, filled_price = $4, fee = $5,
        net_pnl = $6, error = $7, updated_at = NOW()
    WHERE order_id = $1
"""
