# Pippin Arbitrage Bot

A high-frequency, multi-exchange crypto arbitrage bot built with Python (asyncio) and React (TypeScript).

## Features
- **Multi-Exchange Support**: Binance, Backpack, Bybit, Dex-Trade.
- **Split-Wallet Execution**: Simultaneous buy/sell logic on two different exchanges.
- **Asymmetric Fill Safety**: Automatically reverts exposed positions if one leg of an arbitrage trade fails.
- **Solana Rebalancing**: Tracks inventory skew across exchanges to trigger Solana on-chain rebalancing.
- **Trade Control UI**: Interactive dashboard to monitor active trades, rebalances, and execution history.
- **Mock & Pro Modes**: Easily toggle between paper-trading and live execution.

---

## 🚀 Quick Start (Local Development)

### 1. Requirements
- Docker & Docker Compose (for TimescaleDB)
- Node.js (for the React Frontend)
- Python 3.9+ (for the Backend)

### 2. Start the Database
The bot requires TimescaleDB (PostgreSQL) to store opportunities and trade history.

```bash
# Start TimescaleDB locally
docker compose up -d

# NOTE: The database schema is initialized automatically via sql/init.sql on first start.
```

### 3. Start the Backend Engine
The backend engine monitors the exchanges and broadcasts opportunities.

```bash
# Activate your virtual environment
source venv/bin/activate

# Install dependencies (if you haven't already)
pip install -r requirements.txt

# Start the python backend
python main.py
```
*Note: `main.py` is the entry point that spins up the engine and `ws_server.py` automatically.*

### 4. Start the Frontend UI
The frontend provides the interactive Trade Control and monitoring dashboard.

Open a new terminal window:
```bash
cd frontend

# Install packages
npm install

# Run the development server
npm run dev
```
The frontend will be available at [http://localhost:5173](http://localhost:5173).

---

## ☁️ Deployment (AWS)

The bot is designed to run persistently using `pm2`.

```bash
# Restart the backend
pm2 restart arb-backend

# Restart the frontend
pm2 restart pippin_frontend

# View live logs
pm2 logs
```

## Environment Variables (`.env`)
Make sure your `.env` contains your API keys and the correct database credentials:

```ini
MOCK_MODE=true

# Database Credentials
DB_HOST=localhost
DB_PORT=5432
DB_USER=arb_user
DB_PASSWORD=arb_dev_pass
DB_NAME=arb_bot
```
*(On AWS, `DB_PORT` might be `5433` depending on your native PostgreSQL setup.)*