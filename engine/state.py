"""
engine/state.py — Trade State Machine
Single source of truth for bot lifecycle. Prevents concurrent trades.
"""
import asyncio
from enum import Enum
from datetime import datetime, timezone
from typing import Optional
import structlog

log = structlog.get_logger(__name__)


class TradeState(Enum):
    IDLE        = "idle"
    SCANNING    = "scanning"
    LEG1_OPEN   = "leg1_open"
    LEG2_OPEN   = "leg2_open"
    HEDGING     = "hedging"
    FLAT        = "flat"
    REBALANCING = "rebalancing"
    PAUSED      = "paused"
    SHUTDOWN    = "shutdown"


class StateMachine:
    _ALLOWED: dict = {
        TradeState.IDLE:        {TradeState.SCANNING, TradeState.REBALANCING, TradeState.SHUTDOWN},
        TradeState.SCANNING:    {TradeState.IDLE, TradeState.LEG1_OPEN},
        TradeState.LEG1_OPEN:   {TradeState.LEG2_OPEN, TradeState.HEDGING},
        TradeState.LEG2_OPEN:   {TradeState.FLAT, TradeState.HEDGING},
        TradeState.HEDGING:     {TradeState.FLAT, TradeState.IDLE},
        TradeState.FLAT:        {TradeState.IDLE, TradeState.PAUSED},
        TradeState.REBALANCING: {TradeState.IDLE, TradeState.SHUTDOWN},
        TradeState.PAUSED:      {TradeState.IDLE, TradeState.SHUTDOWN},
        TradeState.SHUTDOWN:    set(),
    }

    def __init__(self) -> None:
        self._state:    TradeState    = TradeState.IDLE
        self._lock:     asyncio.Lock  = asyncio.Lock()
        self._since:    datetime      = datetime.now(timezone.utc)
        self._trade_id: Optional[str] = None

    @property
    def state(self) -> TradeState:
        return self._state

    @property
    def trade_id(self) -> Optional[str]:
        return self._trade_id

    def can_trade(self) -> bool:
        return self._state == TradeState.IDLE and not self._lock.locked()

    async def transition(self, new_state: TradeState, trade_id: str = None) -> None:
        async with self._lock:
            allowed = self._ALLOWED.get(self._state, set())
            if new_state not in allowed:
                raise RuntimeError(
                    f"Invalid transition: {self._state.value} → {new_state.value}. "
                    f"Allowed: {[s.value for s in allowed]}"
                )
            old = self._state
            self._state = new_state
            self._since = datetime.now(timezone.utc)
            if trade_id:
                self._trade_id = trade_id
            log.debug("state_transition",
                      old=old.value,
                      new=new_state.value,
                      trade_id=self._trade_id)

    def seconds_in_state(self) -> float:
        return (datetime.now(timezone.utc) - self._since).total_seconds()


sm = StateMachine()
