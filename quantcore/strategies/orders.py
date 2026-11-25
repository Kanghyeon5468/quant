"""Pure slot allocation, price collars and modeled costs shared by replay and paper."""
import hashlib
import json
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from quantcore.strategies.base import STRATEGIES


class OrderPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False, validate_default=True)
    target_fraction: float = Field(default=.95, gt=0, le=.95)
    collar: float = Field(default=.01, gt=0, le=.1)
    commission_bps: float = Field(default=1, ge=0, le=100)
    slippage_bps: float = Field(default=2, ge=0, le=100)
    spread_bps: float = Field(default=2, ge=0, le=100)
    impact_bps: float = Field(default=5, ge=0, le=100)
    minute_participation: float = Field(default=.01, gt=0, le=1)

    @property
    def version(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:16]


def money(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('finite financial value required')
    return result


def limit_price(reference, side, policy):
    multiplier = Decimal(1)+(1 if side == 'buy' else -1)*money(policy.collar)
    return (money(reference)*multiplier).quantize(Decimal('.01'),
        rounding=ROUND_CEILING if side == 'buy' else ROUND_FLOOR)


def modeled_cost(reference, quantity, volume, policy):
    notional = money(reference)*money(quantity)
    participation = float(money(quantity)/max(money(volume), Decimal(1)))
    bps = policy.slippage_bps+policy.spread_bps/2+policy.impact_bps*np.sqrt(participation)
    commission = (notional*money(policy.commission_bps)/10000).quantize(Decimal('.0001'))
    friction = (notional*money(bps)/10000).quantize(Decimal('.0001'))
    return {'commission': float(commission), 'modeled_execution_cost': float(friction),
            'modeled_total_cost': float(commission+friction), 'adverse_bps': float(bps)}


def slot_orders(histories, inventory, cash, budget, strategy, blocked=(), pending=(), policy=None):
    policy = policy or OrderPolicy()
    symbols = list(histories)
    decisions, candidates, prices, references = [], [], {}, {}
    for symbol, history in histories.items():
        reference = money(history.close.iloc[-1])
        if reference <= 0 or money(inventory[symbol]) < 0:
            raise ValueError('positive prices and long-only inventory required')
        signal_frame = history.copy()
        signal_frame['close'] = history.signal_close
        target = float(STRATEGIES[strategy]().targets(signal_frame).iloc[-1])
        if target not in (0., .95):
            raise ValueError('unexpected strategy target')
        limit = limit_price(reference, 'buy', policy)
        desired = (money(budget)/len(symbols)*money(policy.target_fraction if target else 0)/limit).to_integral_value(rounding=ROUND_FLOOR)
        delta = desired-money(inventory[symbol])
        decision = 'hold'
        if symbol in blocked:
            decision = 'existing_pending_or_processed'
        elif delta:
            side = 'buy' if delta > 0 else 'sell'
            candidates.append({'symbol': symbol, 'side': side, 'qty': str(int(abs(delta))),
                'limit_price': str(limit_price(reference, side, policy)), 'type': 'limit',
                'time_in_force': 'day', 'extended_hours': False})
            decision = side
        prices[symbol] = reference
        references[symbol] = {'reference_close': float(reference),
            'average_volume_20': float(history.volume.tail(20).mean()) if 'volume' in history else None}
        decisions.append({'symbol': symbol, 'target_weight_within_slot': str(target),
            'signal_available_at': str(history.available_at.iloc[-1]), 'held_qty': str(inventory[symbol]),
            'desired_qty': str(desired), 'decision': decision})
    reserved = sum((money(o['remaining_qty'])*money(o['limit_price'])*(1+money(policy.commission_bps)/10000)
                    for o in pending if o['side'] == 'buy'), Decimal(0))
    held = sum((money(inventory[s])*prices[s] for s in symbols), Decimal(0))
    capacity = max(Decimal(0), min(money(cash), money(budget)-reserved-held))
    selected = [o for o in candidates if o['side'] == 'sell']
    for order in (o for o in candidates if o['side'] == 'buy'):
        unit = money(order['limit_price'])*(1+money(policy.commission_bps)/10000)
        qty = min(money(order['qty']), (capacity/unit).to_integral_value(rounding=ROUND_FLOOR))
        if qty < money(order['qty']):
            next(d for d in decisions if d['symbol'] == order['symbol'])['decision'] = 'buy_limited_budget' if qty else 'deferred_budget'
        if qty:
            selected.append({**order, 'qty': str(int(qty))})
            capacity -= qty*unit
    return {'orders': selected, 'decisions': decisions, 'references': references,
            'order_policy': policy.model_dump(), 'order_policy_version': policy.version}
