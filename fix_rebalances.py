import asyncio
from app.db.pool import init_db, get_pool

async def fix():
    await init_db()
    pool = get_pool()
    # Mark old test rebalances as completed
    await pool.execute("UPDATE rebalance_transfers SET status = 'completed', updated_at = NOW() WHERE status = 'pending'")
    rows = await pool.fetch("SELECT transfer_id, status FROM rebalance_transfers")
    for r in rows:
        print(f"  {r['transfer_id'][:12]}: {r['status']}")

asyncio.run(fix())
