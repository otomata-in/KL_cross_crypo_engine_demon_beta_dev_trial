# PAAL-V2 — PIPPIN Automated Arbitrage Logic

High-frequency arbitrage bot for PIPPIN/USDT between Binance and MEXC.
Built with a full **Mock (Paper Trading) Mode** so you can simulate and
validate profitability before risking any real capital.

---

## Project Structure

```
pippin_arb_bot/
├── main.py               # Orchestrator — start here
├── config.py             # All settings (Pydantic-validated)
├── analyze_mock.py       # Performance report from mock data
├── requirements.txt
├── .env.example          # Copy to .env and fill in values
│
├── engine/
│   ├── scanner.py        # WebSocket orderbook mirror + REST fallback
│   ├── logic.py          # Spread evaluator + risk filters
│   ├── executor.py       # Order dispatcher (mock + live)
│   ├── mock_exchange.py  # Simulated exchange for paper trading
│   └── state.py          # Trade lifecycle state machine
│
├── utils/
│   ├── logger.py         # CSV + JSONL trade recorder
│   ├── notifier.py       # Telegram alerts
│   ├── fee_ledger.py     # Live fee refresh
│   ├── rate_limiter.py   # Token bucket (anti IP-ban)
│   └── rebalancer.py     # MEXC → Binance Solana transfer
│
├── infra/
│   ├── Dockerfile
│   └── paal-v2.service   # systemd unit
│
├── logs/
│   ├── trades.csv        # Every trade (mock + live, tagged)
│   └── paal_v2.jsonl     # Structured JSON logs
│
└── tests/
    └── test_core.py      # Unit tests
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — the critical fields:

```env
# Start in paper trading mode (safe)
MOCK_MODE=true

# Real API keys are needed for price feeds even in mock mode
API_KEY_BINANCE=your_key
API_SECRET_BINANCE=your_secret
API_KEY_MEXC=your_key
API_SECRET_MEXC=your_secret

# Telegram (optional but recommended)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Run tests

```bash
pytest tests/ -v
```

### 4. Start in Mock Mode (Paper Trading)

```bash
python main.py
```

The bot will:
- Connect to real Binance + MEXC price feeds
- Detect real spread opportunities
- Simulate trades with realistic fill rates and slippage
- Record every mock trade to `logs/trades.csv` with `mock=True`
- Send Telegram alerts tagged `[MOCK]`

### 5. Analyse mock performance

After running for 24+ hours:

```bash
python analyze_mock.py
python analyze_mock.py --days 7
```

Sample output:
```
══════════════════════════════════════════════════════════
  PAAL-V2  —  Mock Trading Analysis Report
══════════════════════════════════════════════════════════

  Total records : 143
  Mock trades   : 143
  Live trades   : 0

──────────────────────────────────────────────────────────
  Arbitrate — Overall Performance
──────────────────────────────────────────────────────────
  Total trades    : 143
  Net PnL         : +47.82 USDT
  Avg per trade   : +0.3344 USDT
  Win rate        : 78.3%  (112W / 31L)
  Profit factor   : 3.21
  Best trade      : +1.82 USDT
  Worst trade     : -0.54 USDT
  IOC miss rate   : 8.4%  (12 misses)
  Avg spread      : 2.14%
  Avg latency     : 47.3ms

  Daily Breakdown (last 7 days)
  Date         Trades       PnL    Win%    IOC%
  ──────────── ─────── ──────── ─────── ───────
  2026-03-22        18    +6.21   77.8%    5.6%
  2026-03-23        22    +7.84   81.8%    9.1%
  ...

  Projection (based on mock data)
  Avg daily PnL   : +6.83 USDT
  Projected /week : +47.82 USDT
  Projected /month: +204.9 USDT
```

---

## Mock Mode — How It Works

Mock mode uses **real price feeds** but **simulated order execution**.

| What's real | What's simulated |
|---|---|
| Binance + MEXC price feeds | Order placement |
| Spread detection | Fill amounts (97% fill rate) |
| All risk filters | Slippage (0.15%) |
| Trade logic | Execution latency (45ms + jitter) |
| PnL calculation | Wallet balances |
| IOC miss detection | Rebalance transfers |

Every mock trade record in `logs/trades.csv` has `mock=True`.
Live trades have `mock=False`. Both coexist in the same file — you can
run mock mode alongside live mode and compare results.

### Tuning mock realism

In `.env`:

```env
MOCK_FILL_RATE=0.97       # lower = more IOC misses (pessimistic)
MOCK_SLIPPAGE_PCT=0.15    # higher = more slippage (pessimistic)
MOCK_LATENCY_MS=45.0      # higher = slower execution
```

For conservative estimates, use `MOCK_FILL_RATE=0.90` and
`MOCK_SLIPPAGE_PCT=0.25`.

---

## Go-Live Checklist

Run through this before switching `MOCK_MODE=false`:

### Security (do these first)
- [ ] IP whitelist API keys on Binance and MEXC (both exchanges)
- [ ] Binance API key: **trading only — NO withdrawal permission**
- [ ] MEXC API key: trading + withdrawal (rebalancer needs this)
- [ ] `.env` is in `.gitignore` — verify with `git status`
- [ ] Telegram alerts confirmed working in mock mode

### Validation
- [ ] Ran mock mode for minimum **72 hours** continuously
- [ ] Win rate > 55% in mock results
- [ ] IOC miss rate < 15% in mock results
- [ ] Profit factor > 1.5 in mock results
- [ ] Zero critical errors in `logs/paal_v2.jsonl`
- [ ] All unit tests passing: `pytest tests/ -v`

### Infrastructure
- [ ] SOL wallet funded with at least 0.05 SOL for gas
- [ ] Server has stable internet (< 50ms to exchange servers)
- [ ] systemd service installed and tested: `sudo systemctl start paal-v2`
- [ ] Log rotation configured (logrotate or similar)

### Switch to live
```env
MOCK_MODE=false
```

---

## Risk Controls Summary

| Control | Value | Behaviour |
|---|---|---|
| Kill switch | $450 | Hard shutdown if total capital drops below |
| Daily loss cap | $30 | Stop trading for the calendar day |
| Consecutive losses | 3 | Pause 15 minutes, then resume |
| Spread sanity | 5% max | Reject ticks above this (bad data) |
| Trigger threshold | 1.8% | Minimum spread to consider a trade |
| Friction budget | 0.4% | Fees + slippage combined |
| IOC orders | Always | Immediate-or-cancel — no resting orders |
| Concurrency lock | State machine | Only one trade at a time |

---

## Deployment (Linux VPS)

```bash
# Install service
sudo cp infra/paal-v2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable paal-v2
sudo systemctl start paal-v2

# Check status
sudo systemctl status paal-v2
sudo journalctl -u paal-v2 -f

# View trade log
tail -f logs/trades.csv
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `MOCK_MODE` | `true` | Paper trading mode |
| `TRADE_AMOUNT` | `100.0` | USD per trade leg |
| `STARTING_CAPITAL` | `500.0` | Total capital across both exchanges |
| `KILL_SWITCH_BALANCE` | `450.0` | Hard stop floor |
| `TRIGGER_THRESHOLD` | `1.8` | Min spread % to trade |
| `FRICTION_BUDGET` | `0.4` | Total fee + slippage % |
| `DAILY_LOSS_CAP` | `30.0` | Max daily loss in USD |
| `CONSEC_LOSS_MAX` | `3` | Consecutive losses before pause |
| `PAUSE_MINUTES` | `15` | Pause duration after loss streak |
| `MAX_VALID_SPREAD` | `5.0` | Reject ticks above this % |
| `MOCK_FILL_RATE` | `0.97` | Simulated order fill rate |
| `MOCK_SLIPPAGE_PCT` | `0.15` | Simulated slippage % |
| `MOCK_LATENCY_MS` | `45.0` | Simulated execution latency |

---

## Important Warnings

- This bot trades real money when `MOCK_MODE=false`. Use at your own risk.
- Past mock performance does not guarantee live performance.
- Arbitrage opportunities for PIPPIN may diminish as the market matures.
- Always monitor the first 24 hours of live trading manually.
- Keep exchange API withdrawal permissions minimal (Binance: none).
