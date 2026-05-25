"""
app/execution/order_tracker.py — Order Tracker
================================================
Monitors order lifecycle, stores updates in the DB, computes PnL.
"""

from typing import List

from app.db import order_repo
from app.models.order import Order


class OrderTracker:
    """
    Manages order creation, status updates, and persistence.
    """

    @staticmethod
    async def create_trade_legs(
        trade_id: str,
        buy_exchange: str, buy_symbol: str, qty: float, buy_price: float,
        sell_exchange: str, sell_symbol: str, sell_price: float,
        is_mock: bool = True
    ) -> List[Order]:
        """Create and persist the buy and sell orders for a trade."""
        from app.models.order import OrderSide

        buy_order = Order(
            trade_id=trade_id,
            exchange=buy_exchange,
            side=OrderSide.BUY,
            symbol=buy_symbol,
            qty=qty,
            price=buy_price,
            is_mock=is_mock
        )

        sell_order = Order(
            trade_id=trade_id,
            exchange=sell_exchange,
            side=OrderSide.SELL,
            symbol=sell_symbol,
            qty=qty,
            price=sell_price,
            is_mock=is_mock
        )

        await order_repo.insert_order(buy_order.to_dict())
        await order_repo.insert_order(sell_order.to_dict())

        return [buy_order, sell_order]

    @staticmethod
    async def update_fill(order: Order, filled_qty: float, filled_price: float, fee: float) -> None:
        """Update an order with fill details and save to DB."""
        order.mark_filled(filled_qty, filled_price, fee)
        await order_repo.update_status(
            order.order_id,
            order.status.value,
            filled_qty,
            filled_price,
            fee
        )

    @staticmethod
    async def update_failed(order: Order, error: str) -> None:
        """Mark order as failed and save to DB."""
        order.mark_failed(error)
        await order_repo.update_status(
            order.order_id,
            order.status.value,
            error=error
        )

    @staticmethod
    async def compute_trade_pnl(buy_order: Order, sell_order: Order) -> float:
        """
        Compute net PnL for a completed trade and save to DB.
        """
        settled_qty = min(buy_order.filled_qty, sell_order.filled_qty)
        if settled_qty == 0:
            return 0.0

        gross_profit = settled_qty * (sell_order.filled_price - buy_order.filled_price)
        total_fees = buy_order.fee + sell_order.fee
        net_pnl = gross_profit - total_fees

        # Update both orders with the trade's net PnL
        buy_order.net_pnl = net_pnl
        sell_order.net_pnl = net_pnl

        await order_repo.update_status(buy_order.order_id, buy_order.status.value, net_pnl=net_pnl)
        await order_repo.update_status(sell_order.order_id, sell_order.status.value, net_pnl=net_pnl)

        return net_pnl
