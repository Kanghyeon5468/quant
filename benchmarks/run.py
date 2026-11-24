"""Reproducible workload, machine/environment and actual elapsed percentiles."""
import asyncio
import json
import os
import platform
import resource
import statistics
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from apps.api.main import create_app
from quantcore.incremental.graph import Graph
from quantcore.research.service import ResearchService


def distribution(values):
    return {'n': len(values), **dict(zip(['p50_ms', 'p95_ms', 'p99_ms', 'p99_9_ms'],
        np.quantile(values, [.5, .95, .99, .999]).tolist()))}


def make_graph(assets=100, history=2000):
    graph = Graph()
    rng = np.random.default_rng(42)
    for i in range(assets):
        base = np.exp(np.cumsum(rng.normal(0, .01, history)))
        graph.input(f'p{i}', 100.)
        def volatility(price, base=base):
            prices = np.r_[base, price/100]
            returns = np.diff(np.log(prices))
            return float(np.std(returns, ddof=1)*np.sqrt(252))
        graph.derive(f'v{i}', [f'p{i}'], volatility)
        graph.derive(f'w{i}', [f'v{i}'], lambda vol: 1/(1+vol))
    graph.derive('portfolio', [f'w{i}' for i in range(assets)], lambda *w: sum(w))
    graph.stabilize()
    return graph


def main():
    cpu_start, wall_start = time.process_time(), time.perf_counter()
    full, incremental = make_graph(), make_graph()
    full_times, incremental_times = [], []
    max_error = 0.
    for i in range(160):
        price = 100+(i+1)*.01
        start = time.perf_counter()
        full.nodes['p0'].value = price
        full.stabilize(full=True)
        elapsed_full = (time.perf_counter()-start)*1000
        start = time.perf_counter()
        incremental.update({'p0': price})
        elapsed_incremental = (time.perf_counter()-start)*1000
        max_error = max(max_error, abs(full.get('portfolio')-incremental.get('portfolio')))
        if i >= 10:
            full_times.append(elapsed_full)
            incremental_times.append(elapsed_incremental)
    with tempfile.TemporaryDirectory() as directory:
        service = ResearchService(Path(directory)/'store')
        start = time.perf_counter()
        asyncio.run(service.bootstrap())
        ingestion_seconds = time.perf_counter()-start
        db_times = []
        for _ in range(100):
            start = time.perf_counter()
            service.store.prices('QALPHA')
            db_times.append((time.perf_counter()-start)*1000)
        service.store.engine.dispose()
        api_times = []
        with TestClient(create_app(Path(directory)/'api')) as client:
            for _ in range(100):
                start = time.perf_counter()
                response = client.get('/api/overview')
                assert response.status_code == 200
                api_times.append((time.perf_counter()-start)*1000)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss_mb = usage.ru_maxrss/(1024**2 if sys.platform == 'darwin' else 1024)
    report = {'environment': {'os': platform.platform(), 'machine': platform.machine(), 'processor': platform.processor(),
        'logical_cpus': os.cpu_count(), 'python': platform.python_version(),
        'packages': {p: version(p) for p in ['numpy', 'pandas', 'scipy', 'fastapi', 'sqlalchemy', 'duckdb']}},
        'dag': {'assets': 100, 'history_per_asset': 2000, 'nodes': len(full.nodes), 'changed_inputs_per_batch': 1,
            'full': distribution(full_times), 'incremental': distribution(incremental_times),
            'median_speedup': statistics.median(full_times)/statistics.median(incremental_times),
            'max_absolute_output_error': max_error, 'derived_computations_per_update': {'full': 201, 'incremental': 3}},
        'api_testclient': distribution(api_times), 'database_query_780_rows': distribution(db_times),
        'ingestion': {'rows': 4680, 'seconds_including_export_and_initialization': ingestion_seconds,
                      'rows_per_second': 4680/ingestion_seconds},
        'process': {'cpu_seconds': time.process_time()-cpu_start, 'wall_seconds': time.perf_counter()-wall_start,
                    'peak_rss_mb': rss_mb},
        'limitations': ['local single-process microbenchmark; not production load or network SLO',
                        'p99.9 interpolated from 100/150 samples; insufficient for tail guarantees',
                        'DAG workload recomputes NumPy volatility; performance depends on graph and workload',
                        'CPU seconds and peak RSS cover entire benchmark process; no hardware optimization claim']}
    Path('docs/benchmark_results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
