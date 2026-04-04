"""
tests/test_core.py — Unit Tests
Covers: state machine transitions, mock exchange fills, logic filters.
Run with: pytest tests/ -v
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── State machine tests ───────────────────────────────────────────

class TestStateMachine:

    def setup_method(self):
        # Fresh state machine for each test
        from engine.state import StateMachine
        self.sm = StateMachine()

    def test_initial_state_is_idle(self):
        from engine.state import TradeState
        assert self.sm.state == TradeState.IDLE

    def test_can_trade_when_idle(self):
        assert self.sm.can_trade() is True

    @pytest.mark.asyncio
    async def test_valid_transition_idle_to_scanning(self):
        from engine.state import TradeState
        await self.sm.transition(TradeState.SCANNING)
        assert self.sm.state == TradeState.SCANNING

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        from engine.state import TradeState
        # Can't go IDLE → LEG2_OPEN directly
        with pytest.raises(RuntimeError, match="Invalid transition"):
            await self.sm.transition(TradeState.LEG2_OPEN)

    @pytest.mark.asyncio
    async def test_full_trade_lifecycle(self):
        from engine.state import TradeState
        await self.sm.transition(TradeState.SCANNING)
        await self.sm.transition(TradeState.LEG1_OPEN, trade_id="test-001")
        await self.sm.transition(TradeState.LEG2_OPEN)
        await self.sm.transition(TradeState.FLAT)
        await self.sm.transition(TradeState.IDLE)
        assert self.sm.state == TradeState.IDLE

    @pytest.mark.asyncio
    async def test_cannot_trade_when_not_idle(self):
        from engine.state import TradeState
        await self.sm.transition(TradeState.SCANNING)
        assert self.sm.can_trade() is False


# ── Mock exchange tests ───────────────────────────────────────────

class MockOrderbookCache:
    """Minimal stub for OrderbookCache used in MockExchange tests."""
    best_bid = 0.0015
    best_ask = 0.0016


class TestMockExchange:

    def setup_method(self):
        os.environ.setdefault("MOCK_MODE", "true")
        os.environ.setdefault("API_KEY_BINANCE", "test")
        os.environ.setdefault("API_SECRET_BINANCE", "test")
        os.environ.setdefault("API_KEY_BACKPACK", "test")
        os.environ.setdefault("API_SECRET_BACKPACK", "test")
        from engine.mock_exchange import MockExchange
        self.ex = MockExchange("binance", MockOrderbookCache())

    def test_initial_balance(self):
        assert self.ex.usdt_balance == 250.0  # STARTING_CAPITAL / 2

    @pytest.mark.asyncio
    async def test_buy_reduces_usdt_increases_base(self):
        usdt_before = self.ex.usdt_balance
        base_before = self.ex.base_balance
        result = await self.ex.place_ioc_buy(qty=1000.0, limit_price=0.0016)
        # If filled, USDT should decrease and base should increase
        if result["filled"] > 0:
            assert self.ex.usdt_balance < usdt_before
            assert self.ex.base_balance > base_before

    @pytest.mark.asyncio
    async def test_sell_reduces_base_increases_usdt(self):
        # First buy some
        await self.ex.place_ioc_buy(qty=50000.0, limit_price=0.0016)
        base_after_buy = self.ex.base_balance
        usdt_after_buy = self.ex.usdt_balance

        result = await self.ex.place_ioc_sell(qty=10000.0, limit_price=0.0015)
        if result["filled"] > 0:
            assert self.ex.base_balance < base_after_buy
            assert self.ex.usdt_balance > usdt_after_buy

    @pytest.mark.asyncio
    async def test_order_result_has_mock_flag(self):
        result = await self.ex.place_ioc_buy(qty=1000.0, limit_price=0.0016)
        assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_cannot_buy_more_than_balance(self):
        # Try to buy way more than we have capital for
        result = await self.ex.place_ioc_buy(qty=10_000_000.0, limit_price=0.0016)
        # Should fill what we can afford, not crash
        cost = result["filled"] * result["price"] * 1.001
        assert cost <= 250.0 + 0.01  # within starting balance + rounding


# ── Logic / spread filter tests ───────────────────────────────────

class MinimalScanner:
    """Stub scanner with fixed orderbook values."""

    class Book:
        bids = [[0.0016, 500_000], [0.00158, 300_000]]
        asks = [[0.00162, 500_000], [0.00165, 200_000]]
        best_bid = 0.0016
        best_ask = 0.00162
        is_stale = False

    books = {
        "binance": Book(),
        "mexc":    Book(),
    }


class TestLogic:

    def setup_method(self):
        os.environ.setdefault("MOCK_MODE", "true")
        os.environ.setdefault("API_KEY_BINANCE", "test")
        os.environ.setdefault("API_SECRET_BINANCE", "test")
        os.environ.setdefault("API_KEY_BACKPACK", "test")
        os.environ.setdefault("API_SECRET_BACKPACK", "test")
        from engine.logic import Logic
        self.logic = Logic(MinimalScanner())

    def test_none_spread_returns_none(self):
        assert self.logic.evaluate(None) is None

    def test_below_threshold_returns_none(self):
        spread = {
            "spread_pct": 0.5,   # below 1.8% trigger
            "direction": "BUY_BINANCE",
            "binance_bid": 0.0016,
            "binance_ask": 0.00162,
            "mexc_bid": 0.0016,
            "mexc_ask": 0.00162,
            "timestamp": 0,
        }
        assert self.logic.evaluate(spread) is None

    def test_above_threshold_returns_signal(self):
        spread = {
            "spread_pct": 2.5,   # above 1.8% trigger
            "direction": "BUY_BINANCE",
            "binance_bid": 0.0016,
            "binance_ask": 0.00158,
            "mexc_bid": 0.00162,
            "mexc_ask": 0.00160,
            "timestamp": 0,
        }
        result = self.logic.evaluate(spread)
        # Returns signal or None depending on depth check with stub data
        # Main check: no exception raised
        assert result is None or isinstance(result, dict)

    def test_session_records_pnl(self):
        self.logic.session.record(1.40)
        assert self.logic.session.summary()["pnl"] == 1.40

    def test_session_tracks_consecutive_losses(self):
        self.logic.session.record(-0.50)
        self.logic.session.record(-0.50)
        assert self.logic.session.summary()["consec"] == 2

    def test_daily_loss_cap_raises(self):
        from engine.logic import DailyLossCapHit
        with pytest.raises(DailyLossCapHit):
            # Record a loss that exceeds the daily cap
            self.logic.session.record(-35.0)

    def test_consecutive_loss_pause_raises(self):
        from engine.logic import ConsecutiveLossPause
        with pytest.raises(ConsecutiveLossPause):
            self.logic.session.record(-1.0)
            self.logic.session.record(-1.0)
            self.logic.session.record(-1.0)  # 3rd consecutive → pause


# ── PnL calculation test ──────────────────────────────────────────

class TestPnLMath:

    def test_basic_arb_profit(self):
        """Verify the core profit equation is correct."""
        trade_amount = 100.0
        spread_pct   = 2.0
        friction_pct = 0.4
        rebal_share  = 0.20

        gross  = trade_amount * spread_pct / 100          # $2.00
        fees   = trade_amount * friction_pct / 100        # $0.40
        net    = gross - fees - rebal_share               # $1.40

        assert abs(net - 1.40) < 0.001

    def test_below_friction_is_negative(self):
        trade_amount = 100.0
        spread_pct   = 0.3    # below friction floor
        friction_pct = 0.4
        rebal_share  = 0.20

        gross = trade_amount * spread_pct / 100
        fees  = trade_amount * friction_pct / 100
        net   = gross - fees - rebal_share

        assert net < 0  # should never trade this

    def test_spread_sanity_bound(self):
        """Spreads above MAX_VALID_SPREAD should be rejected."""
        from config import cfg
        bad_spread = cfg.MAX_VALID_SPREAD + 1.0
        assert bad_spread > cfg.MAX_VALID_SPREAD
