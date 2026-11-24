import time
from collections import defaultdict, deque
from contextlib import contextmanager

import numpy as np


class Metrics:
    def __init__(self):
        self.samples = defaultdict(lambda: deque(maxlen=10000))
        self.errors = 0

    @contextmanager
    def measure(self, name):
        start = time.perf_counter()
        try:
            yield
        except Exception:
            self.errors += 1
            raise
        finally:
            self.samples[name].append((time.perf_counter()-start)*1000)

    def report(self):
        return {'latency_ms': {name: {'count': len(values), **dict(zip(['p50', 'p95', 'p99', 'p99_9'],
            np.quantile(values, [.5, .95, .99, .999]).tolist()))} for name, values in self.samples.items()},
            'errors': self.errors, 'sample_limit': 10000}
