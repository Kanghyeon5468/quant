"""Thread-safe rolling covariance across immutable actual-market dataset versions."""
from threading import RLock

import numpy as np


class RollingCovariance:
    def __init__(self):
        self._lock = RLock()
        self._version = None
        self._frame = None
        self._sum = self._square = self._result = None
        self.appended = self.evicted = self.rebuilds = self.cache_hits = 0

    def update(self, frame, version):
        with self._lock:
            if self._version == version and self._result is not None:
                self.cache_hits += 1
                return self._result.copy()
            old = self._frame
            shared = frame.index.intersection(old.index) if old is not None else []
            if (len(shared) and frame.columns.equals(old.columns)
                    and frame.loc[shared].equals(old.loc[shared])):
                added = frame.loc[frame.index.difference(shared)].to_numpy()
                removed = old.loc[old.index.difference(shared)].to_numpy()
                self._sum += added.sum(axis=0) - removed.sum(axis=0)
                self._square += added.T @ added - removed.T @ removed
                self.appended += len(added)
                self.evicted += len(removed)
            else:
                raw = frame.to_numpy()
                self._sum = raw.sum(axis=0)
                self._square = raw.T @ raw
                self.rebuilds += 1
            self._frame, self._version = frame.copy(), version
            n = len(frame)
            self._result = (self._square - np.outer(self._sum, self._sum)/n) / (n - 1)
            return self._result.copy()

    def report(self):
        with self._lock:
            return {"rebuilds": self.rebuilds, "appended": self.appended, "evicted": self.evicted,
                    "cache_hits": self.cache_hits}
