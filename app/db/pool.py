"""
app/db/pool.py — AsyncPG Connection Pool Manager
==================================================
Manages a singleton connection pool to TimescaleDB.
Tuned for low-memory EC2 (916 MB RAM).

Usage:
    from app.db import init_db, close_db, get_pool
    await init_db()
    pool = get_pool()
    async with pool.acquire() as conn:
        ...
    await close_db()
"""

import asyncpg
from typing import Optional

from app.config import get_config


_pool: Optional[asyncpg.Pool] = None


def _get_db_config() -> dict:
    """Extract DB connection params from app config."""
    cfg = get_config()
    return {
        "host":     cfg.DB_HOST,
        "port":     cfg.DB_PORT,
        "database": cfg.DB_NAME,
        "user":     cfg.DB_USER,
        "password": cfg.DB_PASSWORD,
        "min_size": cfg.DB_POOL_MIN,
        "max_size": cfg.DB_POOL_MAX,
    }


async def init_db() -> Optional[asyncpg.Pool]:
    """
    Initialize the asyncpg connection pool.
    Returns the pool, or None if DB is not available.
    """
    global _pool

    config = _get_db_config()
    try:
        _pool = await asyncpg.create_pool(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            min_size=config["min_size"],
            max_size=config["max_size"],
            command_timeout=10,
        )

        # Log connection info
        async with _pool.acquire() as conn:
            ts_version = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
            )
            pg_version = await conn.fetchval("SELECT version()")

        ts_str = f"TimescaleDB {ts_version}" if ts_version else "PostgreSQL (no TimescaleDB)"
        print(f"[db] Connected to {ts_str}")
        print(f"[db] {pg_version.split(',')[0] if pg_version else 'unknown'}")
        print(f"[db] Pool size: {config['min_size']}-{config['max_size']}")

        return _pool

    except Exception as e:
        print(f"[db] Failed to connect: {e}")
        _pool = None
        return None


async def close_db() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[db] Connection pool closed")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get the current connection pool (None if not initialized)."""
    return _pool
