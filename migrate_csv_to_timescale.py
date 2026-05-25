"""
migrate_csv_to_timescale.py — Historical CSV Data Migration
=============================================================
Reads the opportunities.csv file and bulk-inserts all rows into
the TimescaleDB hypertable using asyncpg's COPY protocol.

Usage:
    python migrate_csv_to_timescale.py
    python migrate_csv_to_timescale.py --csv logs/opportunities.csv
    python migrate_csv_to_timescale.py --dry-run

Features:
    - Streams the CSV in batches (default 1000 rows) to avoid memory overload
    - Uses asyncpg copy_records_to_table for 10-50x faster bulk insert
    - Handles edge cases: missing values, malformed timestamps, empty rows
    - Progress reporting every 10K rows
    - Dry-run mode to validate without inserting
"""

import asyncio
import csv
import os
import sys
import time
from datetime import datetime

from typing import Optional

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────

DEFAULT_CSV = "logs/opportunities.csv"
BATCH_SIZE = 1000
REPORT_EVERY = 10_000

# Column mapping: CSV column name → DB column name
CSV_TO_DB = {
    "timestamp_utc":    "timestamp_utc",
    "token":            "token",
    "ex_buy":           "ex_buy",
    "ex_sell":          "ex_sell",
    "direction":        "direction",
    "gross_spread_pct": "gross_spread",
    "net_spread_pct":   "net_spread",
    "pair_fees_pct":    "pair_fees",
    "buy_ask":          "buy_ask",
    "sell_bid":         "sell_bid",
    "usdt_usdc_rate":   "usdt_usdc_rate",
}

DB_COLUMNS = list(CSV_TO_DB.values())


# ── Parsing ──────────────────────────────────────────────────────

def parse_row(row: dict, line_num: int) -> Optional[tuple]:
    """
    Parse a CSV row dict into a tuple for COPY insertion.
    Returns None if the row is invalid.
    """
    try:
        ts_str = row.get("timestamp_utc", "").strip()
        if not ts_str:
            return None

        # Parse ISO 8601 timestamp
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

        token = row.get("token", "").strip()
        if not token:
            return None

        return (
            ts,
            token,
            row.get("ex_buy", "").strip(),
            row.get("ex_sell", "").strip(),
            row.get("direction", "").strip(),
            float(row.get("gross_spread_pct", 0) or 0),
            float(row.get("net_spread_pct", 0) or 0),
            float(row.get("pair_fees_pct", 0) or 0),
            float(row.get("buy_ask", 0) or 0),
            float(row.get("sell_bid", 0) or 0),
            float(row.get("usdt_usdc_rate", 1.0) or 1.0),
        )
    except (ValueError, TypeError) as e:
        print(f"  ⚠ Skipping line {line_num}: {e}")
        return None


# ── Migration ────────────────────────────────────────────────────

async def migrate(csv_path: str, dry_run: bool = False):
    """Run the full CSV → TimescaleDB migration."""
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return

    # Count total lines for progress
    with open(csv_path, "r") as f:
        total_lines = sum(1 for _ in f) - 1  # subtract header
    print(f"📄 CSV: {csv_path}")
    print(f"📊 Total rows to migrate: {total_lines:,}")

    if dry_run:
        print("🔍 DRY RUN — validating rows without inserting")

    # Connect to database
    config = {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "arb_bot"),
        "user":     os.getenv("DB_USER", "arb_user"),
        "password": os.getenv("DB_PASSWORD", "arb_dev_pass"),
    }

    if not dry_run:
        try:
            conn = await asyncpg.connect(**config)
            print(f"✅ Connected to {config['host']}:{config['port']}/{config['database']}")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return
    else:
        conn = None

    # Stream and batch
    inserted = 0
    skipped = 0
    batch = []
    start_time = time.monotonic()

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):  # line 1 is header
            parsed = parse_row(row, line_num)
            if parsed is None:
                skipped += 1
                continue

            batch.append(parsed)

            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    await conn.copy_records_to_table(
                        "opportunities",
                        records=batch,
                        columns=DB_COLUMNS,
                    )
                inserted += len(batch)
                batch.clear()

                if inserted % REPORT_EVERY == 0:
                    elapsed = time.monotonic() - start_time
                    rate = inserted / elapsed if elapsed > 0 else 0
                    pct = (inserted / total_lines) * 100
                    print(f"  ⏳ {inserted:>8,} / {total_lines:,} ({pct:.1f}%)  [{rate:,.0f} rows/sec]")

    # Flush remaining batch
    if batch:
        if not dry_run:
            await conn.copy_records_to_table(
                "opportunities",
                records=batch,
                columns=DB_COLUMNS,
            )
        inserted += len(batch)

    elapsed = time.monotonic() - start_time
    rate = inserted / elapsed if elapsed > 0 else 0

    print()
    print("═" * 50)
    print(f"  {'DRY RUN ' if dry_run else ''}MIGRATION COMPLETE")
    print("─" * 50)
    print(f"  Inserted : {inserted:,} rows")
    print(f"  Skipped  : {skipped:,} rows")
    print(f"  Time     : {elapsed:.1f}s")
    print(f"  Rate     : {rate:,.0f} rows/sec")

    if not dry_run and conn:
        # Verify
        count = await conn.fetchval("SELECT COUNT(*) FROM opportunities")
        print(f"  DB Total : {count:,} rows")
        await conn.close()

    print("═" * 50)


# ── Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    csv_path = DEFAULT_CSV
    dry_run = False

    args = sys.argv[1:]
    if "--csv" in args:
        idx = args.index("--csv")
        csv_path = args[idx + 1]
    if "--dry-run" in args:
        dry_run = True

    asyncio.run(migrate(csv_path, dry_run))
