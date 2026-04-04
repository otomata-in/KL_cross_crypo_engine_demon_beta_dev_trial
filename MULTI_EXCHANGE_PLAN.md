# Multi-Exchange Expansion Plan

> Expanding the Arbitrage Dashboard from 2 exchanges (Binance + Backpack)
> to 4 exchanges (Binance + Backpack + Bybit + Dex-Trade)

---

## Current State

The system currently monitors **1 exchange pair**:

```
Binance (USDT) ↔ Backpack (USDC)
```

All code is tightly coupled to exactly these two exchanges:
- `LiveState` has `.binance` and `.backpack` hard-coded fields
- `watch_binance_book()` and `watch_backpack_book()` are separate hard-coded functions
- `serialize_state()` builds spread pairs only between Binance and Backpack
- `opportunity_detector()` only computes `spread_buy_bin` and `spread_buy_bp`
- Frontend TypeScript types reference `binance` and `backpack` by name
- The CSV log columns are hard-coded to Binance/Backpack field names

---

## Target State

Monitor **6 exchange pairs** simultaneously (all possible combinations of 4 exchanges):

```
Binance   ↔ Backpack      (existing)
Binance   ↔ Bybit         (new — both USDT, no conversion)
Binance   ↔ Dex-Trade     (new)
Backpack  ↔ Bybit         (new)
Backpack  ↔ Dex-Trade     (new)
Bybit     ↔ Dex-Trade     (new)
```

---

## Architecture After Expansion

```
┌────────────────────────────────────────────────────────────────┐
│                    ws_server.py (backend)                       │
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Binance WS  │  │ Backpack WS │  │ Bybit WS │  │DexTrade │ │
│  │ (ccxt.pro)  │  │ (ccxt.pro)  │  │(ccxt.pro)│  │REST/WS  │ │
│  │ 21 streams  │  │ 21 streams  │  │21 streams│  │Adapter  │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘  └────┬────┘ │
│         │                │               │              │      │
│         └────────────────┴───────────────┴──────────────┘      │
│                          │                                      │
│                    ┌─────▼─────────────────────────────┐        │
│                    │      LiveState (generic)           │        │
│                    │  exchanges: dict[str, dict]        │        │
│                    │  • "binance"   → {token: ob}      │        │
│                    │  • "backpack"  → {token: ob}      │        │
│                    │  • "bybit"     → {token: ob}      │        │
│                    │  • "dextrade"  → {token: ob}      │        │
│                    └───────────────┬────────────────────┘        │
│                                   │                              │
│         ┌─────────────────────────▼──────────────────────┐      │
│         │           opportunity_detector()                 │      │
│         │  Checks ALL N*(N-1)/2 = 6 exchange pairs        │      │
│         │  Per-pair fee model                              │      │
│         └────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────┘
```

---

## Exchange Details

### Exchange Matrix

| Exchange | Type | API | Quote Currency | CCXT Support | Auth |
|----------|------|-----|---------------|--------------|------|
| **Binance** | CEX | WebSocket | USDT | `ccxt.pro.binance` ✅ | Optional for public feeds |
| **Backpack** | CEX | WebSocket | USDC | `ccxt.pro.backpack` ✅ | Optional for public feeds |
| **Bybit** | CEX | WebSocket | USDT | `ccxt.pro.bybit` ✅ | Optional for public feeds |
| **Dex-Trade** | CEX | REST + socket.io | USDT | ❌ Not in ccxt | API key required |

### Dex-Trade API Details

| Property | Value |
|----------|-------|
| **REST Base URL** | `https://api.dex-trade.com/v1/public/` |
| **WebSocket Host** | `socket.dex-trade.com` (socket.io protocol) |
| **Orderbook endpoint** | `GET /book?pair=SOLUSDT` |
| **Ticker endpoint** | `GET /ticker?pair=SOLUSDT` |
| **Symbols endpoint** | `GET /symbols` |
| **Rate limit (public)** | 10 requests/second |
| **Rate limit (private)** | 5 requests/second |
| **WS limit** | 1 connection per IP |
| **Data scaling** | ⚠️ Prices returned as integers × 10⁸, must divide |
| **Pair format** | e.g. `SOLUSDT`, `BTCUSDT` (no slash) |

### Quote Currency Conversion Table

| Exchange | Quote | Conversion to USDT |
|----------|-------|--------------------|
| Binance | USDT | None (native) |
| Bybit | USDT | None (native) |
| Backpack | USDC | `÷ usdt_usdc_rate` |
| Dex-Trade | USDT | None (native) |

> **Simplification:** Binance, Bybit, and Dex-Trade all use USDT. Only Backpack needs USDC→USDT conversion.

### Fee Model (Per Exchange Pair)

| Exchange Pair | Buy Fee | Sell Fee | Network Gas | Total Cost |
|---------------|---------|----------|-------------|-----------|
| Binance ↔ Backpack | 0.10% | 0.10% | 0.01% (SOL) | **0.21%** |
| Binance ↔ Bybit | 0.10% | 0.10% | 0.00% | **0.20%** |
| Binance ↔ Dex-Trade | 0.10% | 0.20% | 0.00% | **0.30%** |
| Backpack ↔ Bybit | 0.10% | 0.10% | 0.01% (SOL) | **0.21%** |
| Backpack ↔ Dex-Trade | 0.10% | 0.20% | 0.01% (SOL) | **0.31%** |
| Bybit ↔ Dex-Trade | 0.10% | 0.20% | 0.00% | **0.30%** |

> **Note:** Dex-Trade taker fee is ~0.20% (verify on their fee schedule).
> Gas is `max(gas_a, gas_b)` — only applies when Backpack (Solana) is involved.

---

## Implementation Plan

### Phase 1 — Backend Refactoring (Generic Exchange Layer)

**Goal:** Make `ws_server.py` exchange-agnostic — add any exchange by config, not code changes.

#### 1.1 Exchange Configuration Registry

Replace the hard-coded `BINANCE_PAIRS`/`BACKPACK_PAIRS` with a single config dict:

```python
from dotenv import load_dotenv
load_dotenv()

EXCHANGES = {
    "binance": {
        "ccxt_id":    "binance",        # ccxt.pro class name
        "quote":      "USDT",
        "fee_taker":  0.10,             # %
        "gas":        0.00,             # % (no gas for CEX-to-CEX transfer)
        "enabled":    True,
        "options":    {"defaultType": "spot"},
        "api_key":    os.getenv("API_KEY_BINANCE"),
        "api_secret": os.getenv("API_SECRET_BINANCE"),
    },
    "backpack": {
        "ccxt_id":    "backpack",
        "quote":      "USDC",
        "fee_taker":  0.10,
        "gas":        0.01,             # Solana network tx
        "enabled":    True,
        "options":    {},
        "api_key":    os.getenv("API_KEY_BACKPACK"),
        "api_secret": os.getenv("API_SECRET_BACKPACK"),
    },
    "bybit": {
        "ccxt_id":    "bybit",
        "quote":      "USDT",
        "fee_taker":  0.10,
        "gas":        0.00,
        "enabled":    True,
        "options":    {"defaultType": "spot"},
        "api_key":    os.getenv("API_KEY_BYBIT"),
        "api_secret": os.getenv("API_SECRET_BYBIT"),
    },
    "dextrade": {
        "ccxt_id":    None,             # Not in ccxt — custom adapter
        "quote":      "USDT",
        "fee_taker":  0.20,             # Dex-Trade taker fee
        "gas":        0.00,
        "enabled":    True,
        "options":    {},
        "api_key":    os.getenv("API_KEY_DEX"),
        "api_secret": os.getenv("API_SECRET_DEX"),
    },
}
```

#### 1.2 Generalize `LiveState`

```python
# BEFORE (hard-coded)
class LiveState:
    self.binance  = {}
    self.backpack = {}
    self.ws_status = {"binance": {}, "backpack": {}}

# AFTER (generic — any number of exchanges)
ENABLED_EXCHANGES = [name for name, cfg in EXCHANGES.items() if cfg["enabled"]]

class LiveState:
    def __init__(self):
        self.exchanges    = {ex: {} for ex in ENABLED_EXCHANGES}
        self.ws_status    = {ex: {} for ex in ENABLED_EXCHANGES}
        self.update_count = {ex: 0  for ex in ENABLED_EXCHANGES}
        self.usdt_usdc_rate = 1.0
        # ... (opp_count, opp_total etc remain unchanged)
```

#### 1.3 Generic `watch_orderbook()` Coroutine

Replace `watch_binance_book()` and `watch_backpack_book()` with **one** generic function:

```python
async def watch_orderbook(exchange_obj, exchange_name: str, token: str, symbol: str):
    """Generic WebSocket orderbook watcher for any ccxt.pro exchange."""
    while True:
        try:
            ob = await exchange_obj.watch_order_book(symbol, limit=10)
            state.exchanges[exchange_name][token] = parse_orderbook(ob)
            state.ws_status[exchange_name][token] = "connected"
            state.update_count[exchange_name] += 1
        except Exception as e:
            state.ws_status[exchange_name][token] = f"error:{str(e)[:30]}"
            await asyncio.sleep(2)
```

This one function replaces both `watch_binance_book()` and `watch_backpack_book()`, and works for Bybit too (since Bybit is also supported in ccxt.pro).

#### 1.4 Dex-Trade Custom Adapter

Since ccxt doesn't support Dex-Trade, we need a **lightweight adapter module**:

**File:** `adapters/dextrade_adapter.py`

```python
import aiohttp
import time

# Dex-Trade REST API
BASE_URL = "https://api.dex-trade.com/v1/public"
PRICE_SCALE = 10**8  # Dex-Trade returns prices as integers × 10⁸


class DexTradeAdapter:
    """
    Polls Dex-Trade REST API for orderbook data every 500ms per token.
    Writes results into state.exchanges["dextrade"][token] in the same
    format as parse_orderbook() for consistency.
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        self._session: aiohttp.ClientSession | None = None
        self._api_key = api_key
        self._api_secret = api_secret
    
    async def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def fetch_orderbook(self, pair: str) -> dict | None:
        """
        Fetch orderbook for a Dex-Trade pair.
        
        Args:
            pair: Dex-Trade format e.g. "SOLUSDT"
        Returns:
            Standardized orderbook dict matching parse_orderbook() output,
            or None if the pair does not exist on Dex-Trade.
        """
        session = await self._get_session()
        url = f"{BASE_URL}/book?pair={pair}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                
                # Parse Dex-Trade orderbook format
                bids = data.get("data", {}).get("buy", [])
                asks = data.get("data", {}).get("sell", [])
                
                best_bid = float(bids[0]["rate"]) / PRICE_SCALE if bids else None
                best_ask = float(asks[0]["rate"]) / PRICE_SCALE if asks else None
                
                bid_depth = sum(
                    (float(b["rate"]) / PRICE_SCALE) * (float(b["volume"]) / 10**6)
                    for b in bids[:5]
                ) if bids else 0
                ask_depth = sum(
                    (float(a["rate"]) / PRICE_SCALE) * (float(a["volume"]) / 10**6)
                    for a in asks[:5]
                ) if asks else 0
                
                return {
                    "bid": best_bid,
                    "ask": best_ask,
                    "bid_depth": bid_depth,
                    "ask_depth": ask_depth,
                    "updated": time.monotonic(),
                }
        except Exception:
            return None
    
    async def close(self):
        if self._session:
            await self._session.close()
```

**Feed coroutine for Dex-Trade:**

```python
async def watch_dextrade_book(adapter: DexTradeAdapter, token: str, pair: str):
    """Poll Dex-Trade REST API every 500ms for one token."""
    while True:
        try:
            ob = await adapter.fetch_orderbook(pair)
            if ob and ob["bid"] is not None:
                state.exchanges["dextrade"][token] = ob
                state.ws_status["dextrade"][token] = "connected"
                state.update_count["dextrade"] += 1
            else:
                state.ws_status["dextrade"][token] = "error:no_data"
        except Exception as e:
            state.ws_status["dextrade"][token] = f"error:{str(e)[:30]}"
        await asyncio.sleep(0.5)  # 2 polls/sec per token
```

**Rate limit consideration:** At 2 req/sec × 21 tokens = 42 req/sec, which exceeds the 10 req/sec limit. Solutions:
- **Option A:** Poll tokens in round-robin batches (poll 5 tokens every 500ms = 10 req/sec)
- **Option B:** Only poll tokens with active spreads on other exchanges
- **Option C:** Use Dex-Trade WebSocket (socket.io) for real-time instead of REST

#### 1.5 Pair-wise Fee Computation

```python
def get_pair_fees(ex_buy: str, ex_sell: str) -> float:
    """Total round-trip cost for a given exchange pair."""
    buy_fee  = EXCHANGES[ex_buy]["fee_taker"]
    sell_fee = EXCHANGES[ex_sell]["fee_taker"]
    gas      = max(EXCHANGES[ex_buy]["gas"], EXCHANGES[ex_sell]["gas"])
    return buy_fee + sell_fee + gas
```

#### 1.6 USDC/USDT Normalization

```python
def normalize_to_usdt(price: float, exchange_name: str) -> float:
    """Convert any quote currency price to USDT equivalent."""
    quote = EXCHANGES[exchange_name]["quote"]
    if quote == "USDT":
        return price
    elif quote == "USDC":
        return price / state.usdt_usdc_rate
    return price
```

> Since Binance, Bybit, and Dex-Trade all quote in USDT, only Backpack needs conversion.

#### 1.7 Opportunity Detector — All Pairs

```python
# Generate all N*(N-1)/2 exchange pairs
EXCHANGE_PAIRS = [
    (a, b)
    for i, a in enumerate(ENABLED_EXCHANGES)
    for b in ENABLED_EXCHANGES[i+1:]
]
# → [("binance","backpack"), ("binance","bybit"), ("binance","dextrade"),
#    ("backpack","bybit"), ("backpack","dextrade"), ("bybit","dextrade")]

for ex_a, ex_b in EXCHANGE_PAIRS:
    pair_fees = get_pair_fees(ex_a, ex_b)
    for token in TOKENS:
        ob_a = state.exchanges[ex_a].get(token, {})
        ob_b = state.exchanges[ex_b].get(token, {})
        # ... compute spread in both directions, check threshold
```

#### 1.8 Serialized State — All Pairs

The JSON payload changes from hard-coded `spread_buy_bin`/`spread_buy_bp` to a generic list:

```python
token_data[token] = {
    "category": TOKEN_CATEGORY[token],
    "exchanges": {
        ex: {
            "bid": ..., "ask": ..., "bid_depth": ..., "ask_depth": ...,
            "age_ms": ..., "status": ...
        }
        for ex in ENABLED_EXCHANGES
    },
    "spread_pairs": [
        {
            "ex_buy":  "binance",
            "ex_sell": "backpack",
            "gross":   +0.345,
            "net":     +0.135,
            "fees":    0.21,
        },
        # ... 12 entries (6 pairs × 2 directions)
    ],
    "best_net":            +0.135,     # best net spread across ALL pairs
    "best_net_pair":       "BIN→BP",   # which pair
    "session_high_net":    +1.024,
    "opp_count":           12,
    "opp_best":            +1.234,
    "opp_last":            { ... },
}
```

---

### Phase 2 — Frontend Updates

#### 2.1 TypeScript Types (`types.ts`)

```typescript
// NEW generic types
interface SpreadPair {
  ex_buy:   string;    // "binance"
  ex_sell:  string;    // "dextrade"
  gross:    number | null;
  net:      number | null;
  fees:     number;    // pair-specific total fees
}

interface TokenData {
  category: string;
  exchanges: Record<string, ExchangeData>; // keyed by exchange name
  spread_pairs: SpreadPair[];              // 12 entries (6 pairs × 2 directions)
  best_net: number | null;                 // best net spread across all pairs
  best_net_pair: string | null;            // e.g. "BIN→BYBIT"
  session_high_net: number | null;
  opp_count: number;
  opp_best: number | null;
  opp_last: OppLast | null;
}

interface LiveState {
  // ... existing fields
  exchanges_list: string[];    // ["binance", "backpack", "bybit", "dextrade"]
  exchange_meta: Record<string, {
    quote: string;
    connected: number;
    total: number;
  }>;
}
```

#### 2.2 `TokenCard` Component Rework

**Before (2 exchanges):**
```
┌──────────────────────────────┐
│  SOL              💎 Big Three │
│  ████████░ +0.24% net         │
│  gross: +0.45% − 0.21% = net │
│  BIN: bid 142.5 / ask 142.6  │
│  BP:  bid 143.1 / ask 143.2  │
│  3 opps | best +1.2% | hi +1.0% │
└──────────────────────────────┘
```

**After (4 exchanges):**
```
┌──────────────────────────────────────┐
│  SOL                   💎 Big Three   │
│  Best: BIN→BP +0.24%  ████████░ net  │
│  ┌─────────┬────────┬────────┬──────┐│
│  │         │ BIN    │ BP     │ BYBIT││
│  │ bid     │ 142.50 │ 143.10 │142.55││
│  │ ask     │ 142.60 │ 143.20 │142.65││
│  └─────────┴────────┴────────┴──────┘│
│  BIN↔BP: +0.24%  BIN↔BYB: +0.01%   │
│  BP↔BYB:  -0.12%  BP↔DEX: -0.40%   │
│  3 opps | best +1.2% | hi +1.0%     │
└──────────────────────────────────────┘
```

Key changes:
- **Best spread banner** at top (highest net spread across all pairs)
- **Multi-exchange price table** (dynamic columns from `exchanges_list`)
- **Spread pairs summary** (compact net % for each pair)
- Card highlight driven by `best_net >= threshold` (not a single pair)

#### 2.3 `HeaderHUD` — Exchange Status

Dynamically generate one status dot per exchange:

```
● BIN 21/21   ● BP 21/21   ● BYBIT 18/21   ● DEX 15/21
```

Loop over `liveState.exchanges_list` instead of hardcoding.

#### 2.4 `ActionFeed` — Multi-Pair Events

Each feed entry now includes which pair triggered:
```
SOL  BIN→BYBIT  gross: +0.45%  net: +0.25%  14:23:05
```

---

### Phase 3 — Dex-Trade WebSocket (Optional Enhancement)

If REST polling hits rate limits for 21 tokens, upgrade to Dex-Trade's **socket.io** WebSocket:

```python
# Requires: pip install python-socketio aiohttp
import socketio

sio = socketio.AsyncClient()

@sio.on('message')
async def on_message(data):
    # Parse orderbook update
    # data contains bids/asks with prices × 10⁸
    ...

await sio.connect('https://socket.dex-trade.com')
# Subscribe to orderbook streams
for pair_id in DEXTRADE_PAIR_IDS:
    await sio.emit('subscribe', {'type': 'book', 'event': f'book_{pair_id}'})
```

**Note:** Dex-Trade allows only **1 WebSocket connection per IP**, so all 21 tokens must share a single connection (multiplexed via subscription rooms).

---

## Files to Create / Modify

| File | Action | Description |
|------|--------|-------------|
| `ws_server.py` | **MODIFY** | Refactor to generic `EXCHANGES` config, generic `watch_orderbook()`, all-pairs detector and serializer |
| `adapters/__init__.py` | **CREATE** | Package init |
| `adapters/dextrade_adapter.py` | **CREATE** | Dex-Trade REST/WS orderbook adapter |
| `frontend/src/types.ts` | **MODIFY** | Generic `TokenData` with `exchanges` map + `spread_pairs[]` |
| `frontend/src/components/TokenCard.tsx` | **MODIFY** | Multi-exchange price table + best-pair spread display |
| `frontend/src/components/HeaderHUD.tsx` | **MODIFY** | Dynamic per-exchange status dots |
| `frontend/src/components/TokenSpreadBar.tsx` | **MODIFY** | Show best spread pair label |
| `frontend/src/components/ActionFeed.tsx` | **MODIFY** | Show which pair triggered the opportunity |
| `.env.example` | **MODIFY** | Add Bybit and Dex-Trade key placeholders |
| `ARCHITECTURE.md` | **MODIFY** | Update to reflect multi-exchange architecture |
| `requirements.txt` | **MODIFY** | Add `aiohttp`, `python-dotenv` dependencies |

---

## Implementation Order

```
Phase 1 (Backend — Generic Exchange Layer):
  Step 1   Add EXCHANGES config registry
  Step 2   Refactor LiveState to generic exchanges dict
  Step 3   Create generic watch_orderbook() coroutine
  Step 4   Add get_pair_fees() and normalize_to_usdt()
  Step 5   Refactor opportunity_detector() for all pairs
  Step 6   Refactor serialize_state() for new payload shape
  Step 7   Add Bybit to main() (ccxt.pro — straightforward)
  Step 8   Test backend with 3 exchanges (Binance + Backpack + Bybit)

Phase 2 (Dex-Trade Adapter):
  Step 9   Create adapters/dextrade_adapter.py (REST polling)
  Step 10  Wire Dex-Trade into main() task list
  Step 11  Test backend with 4 exchanges
  Step 12  (Optional) Upgrade to socket.io WebSocket

Phase 3 (Frontend):
  Step 13  Update TypeScript types.ts
  Step 14  Update TokenCard for multi-exchange display
  Step 15  Update HeaderHUD with dynamic exchange status
  Step 16  Update ActionFeed with pair labels
  Step 17  End-to-end integration test
```

---

## Risk & Considerations

| Risk | Mitigation |
|------|-----------|
| **Bybit token support gap** — some of our 21 tokens may not trade on Bybit (e.g. `BP`, `HONEY`, `CLOUD`) | Add per-exchange `supported_tokens` set; gracefully skip unsupported pairs |
| **Dex-Trade REST rate limit** — 10 req/sec shared across all tokens | Use round-robin batching (5 tokens × 2/sec = 10 req/sec) or switch to socket.io WebSocket |
| **Dex-Trade price scaling** — prices are integers × 10⁸ | Division applied in adapter layer before storing in `LiveState` |
| **Dex-Trade token availability** — may not have all 21 tokens | Pre-check via `GET /symbols` at startup; skip missing tokens |
| **Staggered data ages** — REST-polled Dex-Trade data is 500ms+ stale vs WebSocket feeds | Show `age_ms` per exchange; fade/dim stale data in frontend |
| **More pairs = more compute** — 6 pairs × 21 tokens × 20/sec = 2520 spread checks/sec | Still trivial; pure arithmetic, no I/O |
| **Frontend complexity** — card layout gets wider with 4 exchanges | Responsive design: collapse to "best pair" on small screens, full matrix on large |

---

## Token Availability (To Be Verified at Startup)

| Token | Binance | Backpack | Bybit | Dex-Trade |
|-------|---------|----------|-------|-----------|
| SOL | ✅ | ✅ | ✅ | ❓ |
| ETH | ✅ | ✅ | ✅ | ✅ likely |
| BTC | ✅ | ✅ | ✅ | ✅ likely |
| JUP | ✅ | ✅ | ✅ | ❓ |
| PYTH | ✅ | ✅ | ✅ | ❓ |
| BP | ❌ | ✅ | ❌ | ❌ likely |
| HONEY | ✅ | ✅ | ❌ | ❓ |
| CLOUD | ❌ | ✅ | ❌ | ❌ likely |
| WIF | ✅ | ✅ | ✅ | ❓ |
| BONK | ✅ | ✅ | ✅ | ❓ |

> Pairs with missing tokens are simply skipped — no error.
> The system will auto-detect available markets at startup using `exchange.load_markets()`.

---

## Decision Required

> [!IMPORTANT]
> **Dex-Trade taker fee:** The plan assumes **0.20%** — please verify your actual fee tier
> on https://dex-trade.com/account → Fee schedule. Update `EXCHANGES["dextrade"]["fee_taker"]` accordingly.
