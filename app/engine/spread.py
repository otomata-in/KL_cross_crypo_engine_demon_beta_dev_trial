"""
app/engine/spread.py — Spread Calculation Helpers
===================================================
Pure functions for calculating spreads, normalizing prices, and computing fees.
Extracted from ws_server.py.
"""

from typing import Dict, Tuple

from app.config import get_config


def get_pair_fees(ex_a: str, ex_b: str) -> float:
    """
    Total round-trip cost for a given exchange pair (buy on ex_a, sell on ex_b).
    Includes taker fees on both sides + max network gas fee.
    """
    cfg = get_config()
    a_cfg = cfg.exchanges[ex_a]
    b_cfg = cfg.exchanges[ex_b]
    
    buy_fee  = a_cfg.fee_taker
    sell_fee = b_cfg.fee_taker
    gas      = max(a_cfg.gas, b_cfg.gas)
    
    return buy_fee + sell_fee + gas


def precompute_pair_fees() -> Dict[Tuple[str, str], float]:
    """Precompute fees for all valid exchange pairs."""
    from itertools import combinations
    cfg = get_config()
    enabled = [name for name, ex in cfg.exchanges.items() if ex.enabled]
    pairs = list(combinations(enabled, 2))
    
    fees = {}
    for ex_a, ex_b in pairs:
        fee = get_pair_fees(ex_a, ex_b)
        fees[(ex_a, ex_b)] = fee
        fees[(ex_b, ex_a)] = fee  # symmetric
    return fees


def normalize_to_usdt(price: float, exchange_name: str, usdt_usdc_rate: float) -> float:
    """
    Convert any quote currency price to USDT equivalent.
    """
    cfg = get_config()
    quote = cfg.exchanges[exchange_name].quote
    
    if quote == "USDT":
        return price
    elif quote == "USDC":
        return price / usdt_usdc_rate if usdt_usdc_rate != 0 else price
    return price


def compute_spreads(
    a_bid: float, a_ask: float,
    b_bid: float, b_ask: float,
    ex_a: str, ex_b: str,
    usdt_usdc_rate: float
) -> Tuple[float, float]:
    """
    Compute gross spreads in both directions.
    Returns: (spread_a_to_b, spread_b_to_a)
    """
    a_bid_u = normalize_to_usdt(a_bid, ex_a, usdt_usdc_rate)
    a_ask_u = normalize_to_usdt(a_ask, ex_a, usdt_usdc_rate)
    b_bid_u = normalize_to_usdt(b_bid, ex_b, usdt_usdc_rate)
    b_ask_u = normalize_to_usdt(b_ask, ex_b, usdt_usdc_rate)

    # Direction 1: Buy on ex_a, sell on ex_b
    spread_a_to_b = ((b_bid_u - a_ask_u) / a_ask_u) * 100 if a_ask_u > 0 else 0
    # Direction 2: Buy on ex_b, sell on ex_a
    spread_b_to_a = ((a_bid_u - b_ask_u) / b_ask_u) * 100 if b_ask_u > 0 else 0

    return spread_a_to_b, spread_b_to_a
