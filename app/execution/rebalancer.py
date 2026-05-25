"""
app/execution/rebalancer.py — Split Wallet Rebalancing Engine
===============================================================
Monitors inventory skew across exchanges.
Triggers on-chain Solana transfers to rebalance USDT and Tokens.
"""

import asyncio
import uuid
import time
from typing import Optional

from app.engine.state import get_state
from app.db.order_repo import insert_rebalance_transfer
from app.models.order import RebalanceTransfer
import structlog

logger = structlog.get_logger("rebalancer")

async def trigger_mock_rebalance(token: str, ex_buy: str, ex_sell: str) -> None:
    """
    Calculates deficit and triggers transfers to restore exactly $250 / 50% split.
    """
    state = get_state()
    
    # 1. Rebalance USDT to $250 each
    buy_usdt = state.balances[ex_buy].get("USDT", 250.0)
    sell_usdt = state.balances[ex_sell].get("USDT", 250.0)
    total_usdt = buy_usdt + sell_usdt
    target_usdt = total_usdt / 2.0
    
    usdt_diff = target_usdt - buy_usdt
    if abs(usdt_diff) > 1.0: # threshold to avoid tiny dust transfers
        source_ex = ex_sell if usdt_diff > 0 else ex_buy
        dest_ex = ex_buy if usdt_diff > 0 else ex_sell
        
        await execute_solana_transfer("USDT", abs(usdt_diff), source_ex, dest_ex, mock=True)
        # Apply mock transfer to local state
        state.balances[source_ex]["USDT"] -= abs(usdt_diff)
        state.balances[dest_ex]["USDT"] += abs(usdt_diff)
        
    # 2. Rebalance Base Token to 50% each
    buy_token = state.balances[ex_buy].get(token, 250.0)
    sell_token = state.balances[ex_sell].get(token, 250.0)
    total_token = buy_token + sell_token
    target_token = total_token / 2.0
    
    token_diff = target_token - buy_token
    if abs(token_diff) > 0.001:
        source_ex = ex_sell if token_diff > 0 else ex_buy
        dest_ex = ex_buy if token_diff > 0 else ex_sell
        
        await execute_solana_transfer(token, abs(token_diff), source_ex, dest_ex, mock=True)
        # Apply mock transfer to local state
        state.balances[source_ex][token] -= abs(token_diff)
        state.balances[dest_ex][token] += abs(token_diff)

async def execute_solana_transfer(
    asset: str,
    amount: float,
    source_ex: str,
    dest_ex: str,
    mock: bool = True
) -> None:
    """
    Executes an on-chain transfer from source_ex to dest_ex.
    """
    transfer_id = str(uuid.uuid4())
    logger.info(f"[rebalance] Initiating {amount} {asset} transfer from {source_ex} to {dest_ex} via Solana")
    
    transfer = RebalanceTransfer(
        transfer_id=transfer_id,
        asset=asset,
        amount=amount,
        source_ex=source_ex,
        dest_ex=dest_ex,
        is_mock=mock
    )
    
    await insert_rebalance_transfer(transfer.to_dict())
    
    # Simulate on-chain delay
    await asyncio.sleep(2)
    logger.info(f"[rebalance] {transfer_id} confirmed on-chain.")
