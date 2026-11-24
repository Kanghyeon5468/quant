"""Deterministic batch stabilization, cached values, atomic failure semantics."""
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass
class Node:
    dependencies: tuple[str, ...]
    compute: Callable | None
    value: object = None
    version: int = 0


class Graph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.dirty: set[str] = set()
        self.listeners = []
        self.computations = 0
        self.cache_hits = 0

    def input(self, name, value):
        if name in self.nodes:
            raise ValueError('duplicate node')
        self.nodes[name] = Node((), None, value)

    def derive(self, name, dependencies, compute):
        if name in self.nodes or name in dependencies or any(d not in self.nodes for d in dependencies):
            raise ValueError('duplicate, missing, or circular dependency')
        self.nodes[name] = Node(tuple(dependencies), compute)
        self.dirty.add(name)

    def topological(self):
        order, visiting, done = [], set(), set()
        def visit(name):
            if name in visiting:
                raise ValueError('circular dependency')
            if name in done:
                return
            visiting.add(name)
            for dep in self.nodes[name].dependencies:
                visit(dep)
            visiting.remove(name)
            done.add(name)
            order.append(name)
        for name in self.nodes:
            visit(name)
        return order

    def dependencies(self, name, dependencies):
        if name in dependencies or any(d not in self.nodes for d in dependencies):
            raise ValueError('invalid dependency')
        node = self.nodes[name]
        old = node.dependencies
        node.dependencies = tuple(dependencies)
        try:
            self.topological()
        except ValueError:
            node.dependencies = old
            raise
        self._invalidate({name})

    def _invalidate(self, changed):
        frontier = set(changed)
        while frontier:
            self.dirty.update(frontier)
            frontier = {name for name, node in self.nodes.items()
                        if name not in self.dirty and set(node.dependencies) & frontier}

    def update(self, values):
        for name in values:
            if name not in self.nodes or self.nodes[name].compute is not None:
                raise ValueError('only declared inputs can be updated')
        changed = set()
        for name, value in values.items():
            if self.nodes[name].value != value:
                self.nodes[name].value = value
                self.nodes[name].version += 1
                changed.add(name)
            else:
                self.cache_hits += 1
        self._invalidate(changed)
        self.stabilize()

    def stabilize(self, full=False):
        staged = {name: node.value for name, node in self.nodes.items()}
        calculated = []
        for name in self.topological():
            node = self.nodes[name]
            if node.compute and (full or name in self.dirty):
                staged[name] = node.compute(*(staged[d] for d in node.dependencies))
                calculated.append(name)
        for name in calculated:
            self.nodes[name].value = staged[name]
            self.nodes[name].version += 1
        self.computations += len(calculated)
        self.dirty.clear()
        for callback in self.listeners:
            callback(tuple(calculated))
        return staged

    def get(self, name):
        if name in self.dirty:
            raise RuntimeError('graph has unstabilized values')
        return self.nodes[name].value


class RollingStats:
    def __init__(self, window):
        if window < 2:
            raise ValueError('window must be >=2')
        self.window = window
        self.values: deque[float] = deque()
        self.total, self.squared = 0., 0.

    def append(self, value):
        import math
        if not math.isfinite(value):
            raise ValueError('nonfinite rolling input')
        if len(self.values) == self.window:
            old = self.values.popleft()
            self.total -= old
            self.squared -= old*old
        self.values.append(value)
        self.total += value
        self.squared += value*value
        n = len(self.values)
        mean = self.total/n
        variance = max(0., (self.squared-self.total*self.total/n)/(n-1)) if n > 1 else 0.
        return mean, variance
