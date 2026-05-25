"""
app/execution/split_wallet.py — Split Wallet Execution Engine
===============================================================
Executes simultaneous arbitrage trades across two exchanges.
Requires inventory on both exchanges prior to the trade.
"""

import asyncio
import uuid
import time
from typing import Optional
from dataclasses import asdict

from app.config import get_config
from app.engine.state import get_state
from app.db.order_repo import insert_trade_group, update_trade_group_status, insert_order, update_status
from app.models.order import Order, OrderSide, OrderStatus, TradeGroup
from app.lib.logger import get_logger

logger = get_logger("split_wallet")

async def execute_simultaneous_arb(
    token: str,
    ex_buy: str,
    ex_sell: str,
    target_spread: float,
    buy_price: float,
    sell_price: float,
    mock: bool = True
) -> None:
    """
    Executes a split-wallet arbitrage trade by firing Buy and Sell orders simultaneously.
    Sizes the trade at 5% of the available inventory across both wallets.
    """
    state = get_state()
    cfg = get_config()
    
    trade_id = str(uuid.uuid4())[:12]
    
    # 1. Position Sizing (5% of split wallet)
    # In a real implementation, we fetch actual balances. 
    # Here we mock the balance if missing.
    buy_quote_balance = state.balances.get(ex_buy, {}).get("USDT", 1000.0)
    sell_base_balance = state.balances.get(ex_sell, {}).get(token, 100.0)
    
    # We want to use 5% of available capital
    trade_capital_usdt = buy_quote_balance * 0.05
    qty = trade_capital_usdt / buy_price
    
    # Ensure we don't try to sell more tokens than we have on the sell exchange
    if qty > sell_base_balance * 0.05:
        qty = sell_base_balance * 0.05
        
    if qty < 1.0: # Minimum trade size check
        logger.warning(f"[{trade_id}] Insufficient split-wallet balance for {token}")
        return

    # 2. Record Trade Group
    route = f"{ex_buy}->{ex_sell}"
    trade_group = TradeGroup(
        trade_id=trade_id,
        token=token,
        route=route,
        target_spread=target_spread,
        status="executing",
        is_mock=mock
    )
    await insert_trade_group(trade_group.to_dict())
    state.active_trades[trade_id] = trade_group.to_dict()

    # 3. Prepare Orders
    buy_order = Order(
        exchange=ex_buy, side=OrderSide.BUY, symbol=f"{token}/USDT",
        qty=qty, price=buy_price, trade_id=trade_id, is_mock=mock
    )
    sell_order = Order(
        exchange=ex_sell, side=OrderSide.SELL, symbol=f"{token}/USDT",
        qty=qty, price=sell_price, trade_id=trade_id, is_mock=mock
    )
    
    await insert_order(buy_order.to_dict())
    await insert_order(sell_order.to_dict())

    # 4. Execute Simultaneously
    logger.info(f"[{trade_id}] Firing simultaneous split-wallet orders: BUY {ex_buy} / SELL {ex_sell}")
    
    # In a real engine, these would call exchange.create_order()
    # For now, we mock the network delay and fill.
    results = await asyncio.gather(
        mock_execute_leg(buy_order),
        mock_execute_leg(sell_order),
        return_exceptions=True
    )
    
    buy_result = results[0]
    sell_result = results[1]
    
    # 5. Asymmetric Fill Safety Protocol
    buy_filled = isinstance(buy_result, Order) and buy_result.status == OrderStatus.FILLED
    sell_filled = isinstance(sell_result, Order) and sell_result.status == OrderStatus.FILLED
    
    if buy_filled and not sell_filled:
        logger.error(f"[{trade_id}] ASYMMETRIC FILL: Buy filled on {ex_buy}, Sell failed on {ex_sell}. Reverting Buy!")
        # Trigger market sell on ex_buy to flatten inventory exposure
        await emergency_revert(buy_result)
        await update_trade_group_status(trade_id, "failed", 0)
        
    elif sell_filled and not buy_filled:
        logger.error(f"[{trade_id}] ASYMMETRIC FILL: Sell filled on {ex_sell}, Buy failed on {ex_buy}. Reverting Sell!")
        # Trigger market buy on ex_sell to restore token inventory
        await emergency_revert(sell_result)
        await update_trade_group_status(trade_id, "failed", 0)
        
    elif not buy_filled and not sell_filled:
        logger.warning(f"[{trade_id}] Both legs failed to fill.")
        await update_trade_group_status(trade_id, "failed", 0)
        
    else:
        # Success!
        buy_value = buy_result.filled_qty * buy_result.filled_price
        sell_value = sell_result.filled_qty * sell_result.filled_price
        fees = buy_result.fee + sell_result.fee
        net_pnl = sell_value - buy_value - fees
        
        logger.info(f"[{trade_id}] SPLIT-WALLET ARB SUCCESS! PnL: +{net_pnl:.2f} USDT")
        await update_trade_group_status(trade_id, "completed", net_pnl)
        
    # Cleanup state
    if trade_id in state.active_trades:
        del state.active_trades[trade_id]


async def mock_execute_leg(order: Order) -> Order:
    """Mock execution with simulated latency."""
    await asyncio.sleep(0.2) # Network latency
    order.mark_filled(order.qty, order.price, (order.qty * order.price) * 0.001)
    await update_status(order.order_id, order.status.value, order.filled_qty, order.filled_price, order.fee)
    return order


async def emergency_revert(filled_order: Order) -> None:
    """
    Market closes a directional exposure if the other leg failed.
    """
    logger.warning(f"[{filled_order.trade_id}] Emergency reverting {filled_order.qty} on {filled_order.exchange}")
    await asyncio.sleep(0.3)
    # Simulated revert success
    pass
