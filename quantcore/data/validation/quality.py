import numpy as np
import pandas as pd


def quality_report(frame):
    if frame.empty:
        return {'score': 0, 'status': 'missing', 'rows': 0}
    expected = pd.bdate_range(frame.index.min().normalize(), frame.index.max().normalize())
    observed = frame.index.normalize()
    missing = len(expected.difference(observed))
    returns = frame.close.pct_change()
    anomalies = int((returns.abs() > .3).sum())
    duplicates = int(frame.index.duplicated().sum())
    finite = bool(np.isfinite(frame[['open', 'high', 'low', 'close', 'volume']].to_numpy()).all())
    score = max(0., 1-(missing+duplicates+anomalies)/max(len(expected), 1)) if finite else 0.
    return {'score': score, 'status': 'ok' if score == 1 else 'review', 'rows': len(frame),
            'missing_synthetic_business_days': missing, 'outlier_returns': anomalies, 'duplicates': duplicates,
            'calendar': 'synthetic weekdays; not an exchange holiday calendar'}
