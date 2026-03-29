"""
analyze_mock.py — Mock Trading Performance Analyzer
Run this after a paper trading session to get a full simulation report.
Usage: python analyze_mock.py [--days 7]
"""
import csv
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict


def load_trades(csv_path: str = "logs/trades.csv") -> list[dict]:
    if not os.path.exists(csv_path):
        print(f"No trade log found at {csv_path}")
        print("Run the bot in MOCK_MODE first to generate data.")
        sys.exit(1)
    with open(csv_path, "r") as f:
        return list(csv.DictReader(f))


def filter_mock(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("mock") == "True"]


def filter_live(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("mock") == "False"]


def daily_breakdown(trades: list[dict]) -> dict:
    by_day = defaultdict(list)
    for t in trades:
        day = t.get("timestamp_utc", "")[:10]
        if day:
            by_day[day].append(t)
    return dict(sorted(by_day.items()))


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}

    pnl_values = [float(t["net_pnl"]) for t in trades]
    latencies  = [float(t["latency_ms"]) for t in trades if t.get("latency_ms")]
    spreads    = [float(t["spread_pct"]) for t in trades if t.get("spread_pct")]
    wins       = [p for p in pnl_values if p > 0]
    losses     = [p for p in pnl_values if p < 0]
    ioc_misses = sum(1 for t in trades if t.get("ioc_miss") == "True")

    return {
        "total_trades":  len(trades),
        "total_pnl":     round(sum(pnl_values), 4),
        "avg_pnl":       round(sum(pnl_values) / len(pnl_values), 4),
        "win_rate":      round(len(wins) / len(trades) * 100, 1),
        "wins":          len(wins),
        "losses":        len(losses),
        "ioc_misses":    ioc_misses,
        "ioc_miss_rate": round(ioc_misses / len(trades) * 100, 1),
        "best_trade":    round(max(pnl_values), 4),
        "worst_trade":   round(min(pnl_values), 4),
        "avg_spread":    round(sum(spreads) / len(spreads), 4) if spreads else 0,
        "avg_latency_ms":round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "total_wins_usd": round(sum(wins), 4),
        "total_loss_usd": round(sum(losses), 4),
        "profit_factor":  round(abs(sum(wins) / sum(losses)), 2) if losses else float("inf"),
    }


def print_report(days: int = 7) -> None:
    all_trades   = load_trades()
    mock_trades  = filter_mock(all_trades)
    live_trades  = filter_live(all_trades)

    print("\n" + "═" * 60)
    print("  PAAL-V2  —  Mock Trading Analysis Report")
    print("═" * 60)

    print(f"\n  Total records : {len(all_trades)}")
    print(f"  Mock trades   : {len(mock_trades)}")
    print(f"  Live trades   : {len(live_trades)}")

    if not mock_trades:
        print("\n  No mock trades found. Run the bot with MOCK_MODE=true first.")
        return

    # ── Overall mock stats ────────────────────────────────────────
    stats = compute_stats(mock_trades)
    print("\n" + "─" * 60)
    print("  MOCK — Overall Performance")
    print("─" * 60)
    print(f"  Total trades    : {stats['total_trades']}")
    print(f"  Net PnL         : {'+'if stats['total_pnl']>=0 else ''}{stats['total_pnl']} USDT")
    print(f"  Avg per trade   : {stats['avg_pnl']} USDT")
    print(f"  Win rate        : {stats['win_rate']}%  ({stats['wins']}W / {stats['losses']}L)")
    print(f"  Profit factor   : {stats['profit_factor']}")
    print(f"  Best trade      : +{stats['best_trade']} USDT")
    print(f"  Worst trade     : {stats['worst_trade']} USDT")
    print(f"  IOC miss rate   : {stats['ioc_miss_rate']}%  ({stats['ioc_misses']} misses)")
    print(f"  Avg spread      : {stats['avg_spread']}%")
    print(f"  Avg latency     : {stats['avg_latency_ms']}ms")

    # ── Daily breakdown ───────────────────────────────────────────
    daily = daily_breakdown(mock_trades)
    recent_days = sorted(daily.keys())[-days:]

    print("\n" + "─" * 60)
    print(f"  Daily Breakdown (last {days} days)")
    print("─" * 60)
    print(f"  {'Date':<12} {'Trades':>7} {'PnL':>10} {'Win%':>7} {'IOC%':>7}")
    print(f"  {'─'*12} {'─'*7} {'─'*10} {'─'*7} {'─'*7}")

    cumulative = 0.0
    for day in recent_days:
        day_trades = daily[day]
        ds = compute_stats(day_trades)
        cumulative += ds["total_pnl"]
        pnl_str = f"{'+'if ds['total_pnl']>=0 else ''}{ds['total_pnl']}"
        print(f"  {day:<12} {ds['total_trades']:>7} {pnl_str:>10} "
              f"{ds['win_rate']:>6}% {ds['ioc_miss_rate']:>6}%")

    print(f"  {'─'*12} {'─'*7} {'─'*10}")
    cum_str = f"{'+'if cumulative>=0 else ''}{round(cumulative,4)}"
    print(f"  {'TOTAL':<12} {'':>7} {cum_str:>10}")

    # ── Projection ────────────────────────────────────────────────
    if len(recent_days) >= 2:
        avg_daily = cumulative / len(recent_days)
        print("\n" + "─" * 60)
        print("  Projection (based on mock data)")
        print("─" * 60)
        print(f"  Avg daily PnL   : {'+'if avg_daily>=0 else ''}{round(avg_daily,4)} USDT")
        print(f"  Projected /week : {'+'if avg_daily*7>=0 else ''}{round(avg_daily*7,2)} USDT")
        print(f"  Projected /month: {'+'if avg_daily*30>=0 else ''}{round(avg_daily*30,2)} USDT")

        if stats["ioc_miss_rate"] > 15:
            print(f"\n  WARNING: IOC miss rate {stats['ioc_miss_rate']}% > 15%.")
            print("  Consider raising TRIGGER_THRESHOLD — price moves too fast.")
        if stats["win_rate"] < 55:
            print(f"\n  WARNING: Win rate {stats['win_rate']}% < 55%.")
            print("  Review friction budget and slippage assumptions.")
        if stats["profit_factor"] > 1.5:
            print(f"\n  Profit factor {stats['profit_factor']} looks good.")
            print("  Consider live testing with minimum capital.")

    print("\n" + "═" * 60 + "\n")


if __name__ == "__main__":
    days = 7
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except (ValueError, IndexError):
            pass
    print_report(days=days)
