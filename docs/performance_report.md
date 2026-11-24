# 실제 실행·성능 보고서

기록일:2026-11-24. 합성 데이터 기반 로컬 MVP 실행 검증. 기관급 운영 성능이나 실제 투자 수익률을 뜻하지 않는다.

## 실행 환경

- Host: Apple M3 Pro, macOS-15.6.1-arm64-arm-64bit, 12 logical CPUs, Python 3.12.12.
- Packages: {'numpy': '2.3.5', 'pandas': '2.3.3', 'scipy': '1.18.1', 'fastapi': '0.165.0', 'sqlalchemy': '2.1.9', 'duckdb': '1.5.6'}.
- Docker daemon27.4.0, Compose2.31.0, API Python3.12 slim, web Node24 Alpine/Next16.4.6.
- Docker image build/TypeScript compilation completed; API healthy, web running. Ports127.0.0.1:8100 and3100.
- Initial desktop credential helper hung; public images built via temporary anonymous config. Existing Docker credentials unchanged.

## 자동 검증

- Pytest: 71 passed / 5.52s; 1 deprecation warning.
- Statement coverage: 98.40% (1171/1190), quantcore/apps.api only.
- Unit/integration/property/regression/performance-budget/financial/leakage tests; backup and module cycle checks included.
- Ruff passed. Mypy core/events/incremental/security8 files passed. Frontend production build passed.
- Actual Chromium: 10 user scenarios passed; page errors=0.
- Checks: overview_price_chart_and_websocket, asset_selection, valuation_compute, technical_indicators, factor_weights, two_strategy_views, portfolio_optimization, ml_baseline_and_split_audit, language_and_keyboard_navigation, mobile_layout.
- GitHub-hosted CI was not executed; workflow is supplied.

## 측정한 지연 분포

| Workload | n | p50 ms | p95 ms | p99 ms | p99.9 ms |
|---|---:|---:|---:|---:|---:|
| Full DAG | 150 | 1.9035 | 1.9966 | 2.0585 | 2.0742 |
| Incremental DAG | 150 | 0.2638 | 0.2973 | 0.5184 | 1.0086 |
| API TestClient | 100 | 19.6837 | 20.6500 | 26.4316 | 30.4714 |
| SQLite780 rows | 100 | 6.5076 | 7.7069 | 8.4102 | 11.1004 |

DAG:100 assets ×2,000 price-history values;301 nodes;one changed input per batch. Full derived computations201 vs incremental3. Median ratio=7.2161×; maximum absolute output difference=0.0.
Ingestion:4,680 rows including setup and Parquet export in 0.6503s, 7196.9 rows/s.
Benchmark process:CPU 4.2642s, wall 4.3440s, peak RSS 247.25MiB.

These are in-process sequential workload measurements, not network load tests. p99.9 is interpolated from100/150 observations and cannot establish a production tail SLO. The simple live demo DAG and other workloads can have different speed ratios. Memory covers the benchmark process, not all Docker/browser processes.

## 플랫폼 간 수치 대조

- Max close-price difference: 9.9476e-14 USD; tolerance1e-10.
- QALPHA Momentum net-return difference: 2.2204e-16; tolerance1e-10.
- Optimized portfolio Historical VaR difference: 1.1823e-10; solver-related tolerance1e-7.
- Parquet byte hashes differ across platforms. Byte identity is used for each local snapshot; cross-platform numerical agreement is checked independently. Same-environment repeated ingestion preserves the snapshot hash.

## 재현 명령

```bash
make test
make check
make report
make benchmark
docker compose up -d --no-build
.venv/bin/python scripts/validate_runtime.py
.venv/bin/playwright install chromium
.venv/bin/python tests/end_to_end/browser.py
```

Browser download used a temporary cache in this restricted execution environment: `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/quantcore-browsers`. Standard user-terminal Playwright installation can use its default cache.

## 검증하지 않은 범위

External provider/real-market profitability, full original feature inventory, exchange calendars/short borrowing/funding, historical crisis stress, public multi-user deployment, large-scale concurrent load, network WebSocket RTT, Prometheus/Grafana/OTel, memory leak soak tests and remote CI remain unverified or unimplemented. See requirements_comparison.md and known_issues.md.
