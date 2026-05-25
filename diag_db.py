"""Diagnostic script to analyze mock trade data from TimescaleDB."""
import asyncio
import json
from app.db.pool import init_db, get_pool

async def main():
    await init_db()
    pool = get_pool()

    # 1. Order status breakdown
    rows = await pool.fetch("SELECT status, COUNT(*) as cnt FROM orders GROUP BY status ORDER BY cnt DESC")
    print("=== ORDER STATUS BREAKDOWN ===")
    for r in rows:
        print(f"  {r['status']}: {r['cnt']}")

    # 2. Mock trade summary per exchange/side
    rows = await pool.fetch("""
        SELECT exchange, side,
               SUM(filled_qty * filled_price) as total_value,
               SUM(filled_qty) as total_qty,
               SUM(fee) as total_fees,
               COUNT(*) as trade_count
        FROM orders
        WHERE is_mock = true AND status = 'filled'
        GROUP BY exchange, side
        ORDER BY exchange, side
    """)
    print("\n=== MOCK TRADE SUMMARY (per exchange/side) ===")
    for r in rows:
        print(f"  {r['exchange']} {r['side']}: value=${float(r['total_value']):.4f}, qty={float(r['total_qty']):.4f}, fees=${float(r['total_fees']):.6f}, count={r['trade_count']}")

    # 3. Rebalance transfers
    cnt = await pool.fetchval("SELECT COUNT(*) FROM rebalance_transfers")
    print(f"\n=== REBALANCE TRANSFERS (total: {cnt}) ===")
    rows = await pool.fetch("SELECT * FROM rebalance_transfers ORDER BY created_at DESC LIMIT 5")
    for r in rows:
        print(f"  {r['asset']} {float(r['amount']):.4f} {r['source_ex']}->{r['dest_ex']} status={r['status']} mock={r['is_mock']}")

    # 4. Trade groups summary
    rows = await pool.fetch("""
        SELECT status, COUNT(*) as cnt,
               SUM(COALESCE(realized_pnl, 0)) as total_pnl
        FROM trade_groups
        WHERE is_mock = true
        GROUP BY status
    """)
    print("\n=== TRADE GROUP SUMMARY ===")
    for r in rows:
        print(f"  {r['status']}: count={r['cnt']}, total_pnl=${float(r['total_pnl']):.6f}")

    # 5. Last 15 mock trades
    rows = await pool.fetch("""
        SELECT trade_id, token, COALESCE(realized_pnl, 0) as pnl, status, created_at
        FROM trade_groups WHERE is_mock = true
        ORDER BY created_at DESC LIMIT 15
    """)
    print("\n=== LAST 15 MOCK TRADES ===")
    for r in rows:
        print(f"  {r['trade_id']} {r['token']}: pnl=${float(r['pnl']):.6f} status={r['status']}")

    # 6. Check net wallet math: how much USDT left on buy side after all trades
    rows = await pool.fetch("""
        SELECT exchange,
               SUM(CASE WHEN side='buy' THEN -(filled_qty * filled_price) ELSE (filled_qty * filled_price) END) as usdt_delta,
               SUM(CASE WHEN side='buy' THEN filled_qty ELSE -filled_qty END) as token_delta,
               SUM(fee) as total_fees
        FROM orders
        WHERE is_mock = true AND status = 'filled'
        GROUP BY exchange
        ORDER BY exchange
    """)
    print("\n=== NET WALLET DELTAS (since start) ===")
    for r in rows:
        print(f"  {r['exchange']}: USDT delta={float(r['usdt_delta']):+.4f}, Token delta={float(r['token_delta']):+.4f}, Fees={float(r['total_fees']):.6f}")

asyncio.run(main())
