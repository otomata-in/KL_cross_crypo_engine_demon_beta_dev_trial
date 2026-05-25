"""
db.py — TimescaleDB Connection Pool Manager
=============================================
Manages an asyncpg connection pool for the arbitrage bot.
Reads configuration from environment variables (.env).

Usage:
    from db import init_db, close_db, get_pool

    # At startup:
    await init_db()

    # Use the pool:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM opportunities LIMIT 10")

    # At shutdown:
    await close_db()
"""

import os
from typing import Optional

import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: Optional[asyncpg.Pool] = None


def _get_config() -> dict:
    """Read database configuration from environment variables."""
    return {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "arb_bot"),
        "user":     os.getenv("DB_USER", "arb_user"),
        "password": os.getenv("DB_PASSWORD", "arb_dev_pass"),
        "min_size": int(os.getenv("DB_MIN_POOL", "2")),
        "max_size": int(os.getenv("DB_MAX_POOL", "10")),
    }


async def init_db() -> Optional[asyncpg.Pool]:
    """
    Initialize the asyncpg connection pool.
    Returns the pool, or None if DB is not available.
    """
    global _pool


    config = _get_config()
    try:
        _pool = await asyncpg.create_pool(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            min_size=config["min_size"],
            max_size=config["max_size"],
            # Timeout for acquiring a connection from the pool
            timeout=10,
            # Statement cache for prepared statements (faster repeated queries)
            statement_cache_size=100,
        )
        # Verify connection
        async with _pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            ts_version = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
            )
            print(f"[db] Connected to TimescaleDB {ts_version or 'N/A'}")
            print(f"[db] PostgreSQL: {version.split(',')[0]}")
            print(f"[db] Pool size: {config['min_size']}-{config['max_size']}")

        return _pool
    except Exception as e:
        print(f"[db] ⚠ Failed to connect to TimescaleDB: {e}")
        print(f"[db] ⚠ Falling back to CSV-only mode")
        _pool = None
        return None


async def close_db():
    """Close the connection pool gracefully."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[db] Connection pool closed")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get the current connection pool (may be None if not initialized)."""
    return _pool
