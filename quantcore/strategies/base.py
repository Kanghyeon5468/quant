from typing import Protocol

import pandas as pd


class Strategy(Protocol):
    name: str
    def targets(self, frame: pd.DataFrame) -> pd.Series: ...


class Momentum:
    name = 'momentum'
    def targets(self, frame):
        return (frame.close > frame.close.rolling(60).mean()).astype(float)*.95


class MeanReversion:
    name = 'mean_reversion'
    def targets(self, frame):
        mean = frame.close.rolling(20).mean()
        std = frame.close.rolling(20).std()
        z = (frame.close-mean)/std
        holding, values = False, []
        for value in z:
            if value < -1:
                holding = True
            elif value >= 0:
                holding = False
            values.append(.95 if holding else 0.)
        return pd.Series(values, index=frame.index)


class BuyHold:
    name = 'buy_hold'
    def targets(self, frame):
        return pd.Series(.95, index=frame.index)


STRATEGIES = {'momentum': Momentum, 'mean_reversion': MeanReversion, 'buy_hold': BuyHold}
