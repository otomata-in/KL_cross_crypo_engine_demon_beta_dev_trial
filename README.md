# Pippin Arbitrage Bot

A high-frequency, multi-exchange crypto arbitrage bot built with Python (asyncio) and React (TypeScript).

## Features
- **Multi-Exchange Support**: Binance, Backpack, Bybit, Dex-Trade.
- **Split-Wallet Execution**: Simultaneous buy/sell logic on two different exchanges with 5% position sizing.
- **Asymmetric Fill Safety**: Automatically reverts exposed positions if one leg of an arbitrage trade fails.
- **Solana Rebalancing**: Tracks inventory skew across exchanges to trigger Solana on-chain rebalancing. Rebalances both Quote (USDT) and Base Token inventory at a 20% imbalance threshold.
- **Trade Control UI**: Interactive dashboard to monitor active trades, rebalances, and execution history.
- **PnL Analytics Dashboard**: Granular Net Profit & Loss breakdown per token, filterable by Timeframe (Session/Day/Week/Month/Total) and by Exchange.
- **Wallet Persistence**: In Mock mode, mock trade history is stored in TimescaleDB and wallets dynamically reconstruct their balances on startup. 
- **Dynamic Mock Initialization**: Wallets can be hard-reset from the UI. Token balances lazily initialize to exactly $250-worth at the live market price right before the first trade.
- **Mock & Pro Modes**: Easily toggle between paper-trading and live execution from the UI.

---

## 🚀 Quick Start (Local Development)

### 1. Requirements
- Docker & Docker Compose (for TimescaleDB)
- Node.js (for the React Frontend)
- Python 3.9+ (for the Backend)

### 2. Start the Database
The bot requires TimescaleDB (PostgreSQL) to store opportunities, trades, and rebalance history.

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
*Note: `main.py` is the entry point that spins up the core execution engine and the `ws_server.py` websocket transport.*

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

The production deployment uses `pm2` for the Python backend and `nginx` for the static React frontend.

### 1. Deploying Updates
You can deploy updates from your local machine using the `deploy_remote.sh` script, or run it directly on the server:

```bash
# Run the deployment script on the remote server
bash ~/pippin_arb_bot/deploy_remote.sh
```

### 2. What `deploy_remote.sh` does:
1. Installs any new Python dependencies.
2. Removes `.env.local` to ensure the production WebSocket URL is dynamically generated based on the hosting IP.
3. Builds the production React bundle (`npm run build`).
4. Restarts the `arb-backend` PM2 process.
5. Copies the frontend build to `/usr/share/nginx/html/arbitrage/`.

### 3. Monitoring Production
```bash
# View live backend logs
pm2 logs arb-backend

# View PM2 process status
pm2 status
```

---

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