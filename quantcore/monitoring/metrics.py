import time
from collections import defaultdict, deque
from contextlib import contextmanager
from threading import RLock

import numpy as np


class Metrics:
    def __init__(self):
        self.samples = defaultdict(lambda: deque(maxlen=10000))
        self.errors = 0
        self.lock = RLock()

    @contextmanager
    def measure(self, name):
        start = time.perf_counter()
        try:
            yield
        except Exception:
            with self.lock:
                self.errors += 1
            raise
        finally:
            self.observe(name, (time.perf_counter()-start)*1000)

    def observe(self, name, milliseconds):
        with self.lock:
            self.samples[name].append(milliseconds)

    def report(self):
        with self.lock:
            samples = {name: list(data) for name, data in self.samples.items()}
            errors = self.errors
        return {'latency_ms': {name: {'count': len(values), **dict(zip(['p50', 'p95', 'p99', 'p99_9'],
            np.quantile(values, [.5, .95, .99, .999]).tolist()))} for name, values in samples.items() if values},
            'errors': errors, 'sample_limit': 10000}

    def prometheus(self):
        report = self.report()
        output = ["# TYPE quantcore_observed_errors_total counter",
                  f"quantcore_observed_errors_total {report['errors']}",
                  "# TYPE quantcore_recent_latency_seconds gauge",
                  "# TYPE quantcore_recent_latency_samples gauge"]
        for name, measurements in report["latency_ms"].items():
            label = name.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            output.append(f'quantcore_recent_latency_samples{{operation="{label}"}} {measurements["count"]}')
            for key, quantile in (("p50", ".50"), ("p95", ".95"), ("p99", ".99"), ("p99_9", ".999")):
                output.append(f'quantcore_recent_latency_seconds{{operation="{label}",quantile="{quantile}"}} {measurements[key]/1000}')
        return "\n".join(output) + "\n"
