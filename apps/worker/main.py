"""Explicit idempotent demo ingestion; no external accounts or background orders."""
import asyncio
import json
import os

from quantcore.research.service import ResearchService


async def main():
    service = ResearchService(os.getenv('QUANTCORE_DATA_DIR', 'datasets'))
    result = await service.bootstrap()
    print(json.dumps({'ingestion': result, 'manifest': service.manifest}, indent=2))
    service.store.engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
