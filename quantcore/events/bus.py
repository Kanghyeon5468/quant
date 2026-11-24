import asyncio
from collections import defaultdict

from quantcore.core.models import Event


class EventBus:
    """Bounded fanout; consumer failure is observable and isolated."""
    def __init__(self, capacity=128):
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=capacity)
        self.handlers = defaultdict(list)
        self.failures = []

    def subscribe(self, kind, handler):
        self.handlers[kind].append(handler)

    async def publish(self, event):
        await self.queue.put(event)

    async def drain(self):
        while not self.queue.empty():
            event = self.queue.get_nowait()
            try:
                for handler in self.handlers[event.kind]:
                    try:
                        await handler(event)
                    except Exception as error:
                        self.failures.append({'kind': event.kind, 'error': type(error).__name__})
            finally:
                self.queue.task_done()
