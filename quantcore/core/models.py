"""Validated point-in-time contracts. Prices are quotes, not account balances."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator


class AssetClass(StrEnum):
    EQUITY = 'equity'
    ETF = 'etf'
    INDEX = 'index'
    BOND = 'bond'
    FX = 'fx'
    COMMODITY = 'commodity'
    CRYPTO = 'crypto'
    FUTURE = 'future'
    OPTION = 'option'


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Asset(Contract):
    symbol: str = Field(pattern=r'^[A-Z0-9._-]{1,20}$')
    name: str
    asset_class: AssetClass = AssetClass.EQUITY
    currency: Literal['USD', 'KRW'] = 'USD'
    exchange_timezone: str = 'America/New_York'
    sector: str
    market_cap: FiniteFloat = Field(gt=0)


class Bar(Contract):
    symbol: str = Field(pattern=r'^[A-Z0-9._-]{1,20}$')
    timestamp: datetime
    available_at: datetime
    open: FiniteFloat = Field(gt=0)
    high: FiniteFloat = Field(gt=0)
    low: FiniteFloat = Field(gt=0)
    close: FiniteFloat = Field(gt=0)
    volume: int = Field(ge=0)
    currency: Literal['USD', 'KRW'] = 'USD'
    source: str
    mode: Literal['synthetic', 'historical', 'delayed', 'realtime']
    price_basis: Literal['raw'] = 'raw'

    @field_validator('timestamp', 'available_at')
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('timezone-aware timestamps required')
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def consistent(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
            raise ValueError('inconsistent OHLC envelope')
        if self.available_at < self.timestamp:
            raise ValueError('bar cannot be available before bar completion')
        return self


class Event(Contract):
    kind: str
    version: int = Field(ge=0)
    timestamp: datetime
    payload: dict = Field(default_factory=dict)
