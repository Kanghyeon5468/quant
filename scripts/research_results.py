"""Generate documented numerical results from the actual deterministic engine."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from quantcore.research.service import ResearchService, json_safe
from quantcore.statistics.research import statistical_report


async def main():
    service = ResearchService('datasets')
    await service.bootstrap()
    rows = []
    for symbol in service.frames:
        for strategy in ('momentum', 'mean_reversion'):
            result = service.backtest(symbol, strategy)
            rows.append({'symbol': symbol, 'strategy': strategy, 'period': result['period'],
                **result['metrics'], 'gross_total_return': result['gross_metrics']['total_return'],
                'benchmark_total_return': result['benchmark_metrics']['total_return']})
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'mode': 'synthetic', 'seed': 20261124,
        'dataset': service.manifest, 'strategy_results': rows, 'portfolio': service.portfolio(),
        'machine_learning': service.machine_learning('QALPHA'), 'statistics': statistical_report(service.returns()),
        'performance_claim': 'synthetic simulation only; not actual or prospective market performance'}
    Path('docs/research_results.json').write_text(json.dumps(json_safe(report), indent=2)+'\n')
    for row in rows:
        print(row['symbol'], row['strategy'], 'net', f"{row['total_return']:.4%}", 'gross', f"{row['gross_total_return']:.4%}")
    service.store.engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
