"""
utils/logger.py — Structured Trade Logger
Writes every trade (mock and live) to CSV and JSONL.
Mock trades are tagged with mock=True in every record.
"""
import asyncio
import csv
import json
import os
from datetime import datetime, timezone
from typing import Any
import aiofiles
import structlog

from config import cfg

log = structlog.get_logger(__name__)

# CSV column order — every trade record must have these keys
TRADE_COLUMNS = [
    "timestamp_utc",
    "trade_id",
    "mock",              # True = paper trade, False = real trade
    "direction",
    "spread_pct",
    "buy_exchange",
    "sell_exchange",
    "buy_price",
    "sell_price",
    "buy_filled",
    "sell_filled",
    "delta",
    "buy_fee",
    "sell_fee",
    "net_pnl",
    "latency_ms",
    "ioc_miss",
]


class TradeLogger:

    def __init__(self) -> None:
        self._csv_path  = cfg.TRADES_FILE
        self._jsonl_path = cfg.LOG_FILE
        self._lock       = asyncio.Lock()
        self._init_csv()

    def _init_csv(self) -> None:
        """Create CSV with headers if it doesn't exist."""
        os.makedirs(os.path.dirname(self._csv_path), exist_ok=True)
        os.makedirs(os.path.dirname(self._jsonl_path), exist_ok=True)
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
                writer.writeheader()
            log.info("csv_created", path=self._csv_path)

    async def write(self, record: dict) -> None:
        """Append one trade record to both CSV and JSONL."""
        async with self._lock:
            ts = datetime.fromtimestamp(
                record["timestamp"], tz=timezone.utc
            ).isoformat()

            row = {col: record.get(col, "") for col in TRADE_COLUMNS}
            row["timestamp_utc"] = ts

            # CSV append
            async with aiofiles.open(self._csv_path, "a", newline="") as f:
                # aiofiles doesn't support csv.DictWriter — build line manually
                line = ",".join(str(row[col]) for col in TRADE_COLUMNS)
                await f.write(line + "\n")

            # JSONL append (one JSON object per line — easy to parse/grep)
            json_record = {**record, "timestamp_utc": ts}
            async with aiofiles.open(self._jsonl_path, "a") as f:
                await f.write(json.dumps(json_record) + "\n")

    # ── Analytics helpers ─────────────────────────────────────────

    def load_all(self) -> list[dict]:
        """Load all trades from CSV into a list of dicts."""
        if not os.path.exists(self._csv_path):
            return []
        with open(self._csv_path, "r") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def daily_summary(self, mock_only: bool = None) -> dict:
        """
        Compute daily summary stats.
        mock_only=True  → only mock trades
        mock_only=False → only live trades
        mock_only=None  → all trades
        """
        trades = self.load_all()
        today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        filtered = [
            t for t in trades
            if t.get("timestamp_utc", "").startswith(today)
        ]
        if mock_only is True:
            filtered = [t for t in filtered if t.get("mock") == "True"]
        elif mock_only is False:
            filtered = [t for t in filtered if t.get("mock") == "False"]

        if not filtered:
            return {"date": today, "trades": 0, "net_pnl": 0.0,
                    "wins": 0, "losses": 0, "ioc_misses": 0}

        pnl_values = [float(t["net_pnl"]) for t in filtered]
        total_pnl  = sum(pnl_values)
        wins       = sum(1 for p in pnl_values if p > 0)
        losses     = sum(1 for p in pnl_values if p < 0)
        ioc_misses = sum(1 for t in filtered if t.get("ioc_miss") == "True")

        return {
            "date":       today,
            "trades":     len(filtered),
            "net_pnl":    round(total_pnl, 4),
            "avg_pnl":    round(total_pnl / len(filtered), 4),
            "wins":       wins,
            "losses":     losses,
            "win_rate":   round(wins / len(filtered) * 100, 1),
            "ioc_misses": ioc_misses,
            "best_trade": round(max(pnl_values), 4),
            "worst_trade":round(min(pnl_values), 4),
        }


# Module-level singleton
trade_logger = TradeLogger()
