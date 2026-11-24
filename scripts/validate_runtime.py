"""Compare running Docker API with saved local synthetic research results."""
import json
import os
from pathlib import Path

import httpx
import numpy as np
import pandas as pd


def main():
    local = json.loads(Path('docs/research_results.json').read_text())
    prices = pd.read_parquet('datasets/prices.parquet')
    errors = []
    headers = {'Authorization': 'Bearer '+os.environ['QUANTCORE_API_TOKEN']} if os.getenv('QUANTCORE_API_TOKEN') else {}
    with httpx.Client(base_url=os.getenv('QUANTCORE_API_URL', 'http://127.0.0.1:8100'), headers=headers, timeout=30) as client:
        response = client.get('/api/overview')
        response.raise_for_status()
        overview = response.json()
        for asset in overview['assets']:
            response = client.get('/api/assets/'+asset['symbol']+'/prices?limit=2000')
            response.raise_for_status()
            remote = response.json()['prices']
            frame = prices[prices.symbol == asset['symbol']]
            errors.append(float(np.max(np.abs(frame.close.to_numpy()-np.array([r['close'] for r in remote])))))
        response = client.get('/api/backtests/QALPHA?strategy=momentum')
        response.raise_for_status()
        result = response.json()
        reference = next(r for r in local['strategy_results'] if r['symbol'] == 'QALPHA' and r['strategy'] == 'momentum')
        response = client.get('/api/portfolio')
        response.raise_for_status()
        risk = response.json()['risk']
        report = {'container_api_status': client.get('/health').json(), 'local_snapshot_sha256': local['dataset']['sha256'],
            'docker_snapshot_version': overview['dataset_version'], 'cross_platform_max_close_absolute_error': max(errors),
            'qalpha_momentum_net_return_difference': abs(result['metrics']['total_return']-reference['total_return']),
            'historical_var_difference': abs(risk['historical_var']-local['portfolio']['risk']['historical_var']),
            'note': 'Parquet bytes may differ by platform; numerical agreement measured independently.'}
        assert report['cross_platform_max_close_absolute_error'] < 1e-10
        assert report['qalpha_momentum_net_return_difference'] < 1e-10
        assert report['historical_var_difference'] < 1e-7  # solver/weight tolerance
    Path('docs/container_validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
