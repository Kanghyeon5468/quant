import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def walk_forward(frame, horizon=5, embargo=5):
    if horizon < 1 or embargo < 0:
        raise ValueError('invalid horizon/embargo')
    features = pd.DataFrame({'return_1': frame.close.pct_change(), 'return_5': frame.close.pct_change(5),
        'return_20': frame.close.pct_change(20), 'volatility_20': frame.close.pct_change().rolling(20).std()}, index=frame.index)
    features['y'] = frame.close.shift(-horizon)/frame.close-1
    features['target_at'] = pd.Series(frame.index, index=frame.index).shift(-horizon)
    data = features.dropna()
    predictions, audits = [], []
    for start in range(300, len(data), 63):
        test = data.iloc[start:start+63]
        cutoff = test.index[0]
        train = data.iloc[:max(0, start-embargo)]
        train = train[train.target_at < cutoff]
        if len(train) < 100:
            continue
        columns = ['return_1', 'return_5', 'return_20', 'volatility_20']
        for name, model in [('baseline_mean', DummyRegressor(strategy='mean')),
                            ('ridge', make_pipeline(StandardScaler(), Ridge(alpha=10.)))]:
            model.fit(train[columns], train.y)
            predicted = model.predict(test[columns])
            predictions.extend({'timestamp': str(t), 'model': name, 'prediction': float(p), 'actual': float(y)}
                               for t, p, y in zip(test.index, predicted, test.y))
        audits.append({'train_last_target': str(train.target_at.max()), 'test_start': str(cutoff),
                       'train_rows': len(train), 'test_rows': len(test), 'embargo_bars': embargo})
    if not predictions:
        raise ValueError('insufficient walk-forward history')
    results = pd.DataFrame(predictions)
    metrics = [{'model': model, 'mse': float(mean_squared_error(group.actual, group.prediction)),
                'direction_accuracy': float((np.sign(group.prediction) == np.sign(group.actual)).mean()), 'samples': len(group)}
               for model, group in results.groupby('model')]
    return {'metrics': metrics, 'splits': audits, 'horizon_bars': horizon, 'mode': 'synthetic',
            'limitations': ['no tuning or model selection on test', 'overlapping test targets; samples not independent',
                            'basic return forecast; no trading-profit claim']}
