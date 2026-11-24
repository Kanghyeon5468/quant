# Development log · 2026-11-24

## Phase 0 — inspection and comparison
- Target: fresh Git repository at `jane/quant`, no existing application. Remote exists but no commit/push performed for this task.
- Original/new requirement attachments were compared with `diff -u`: identical. Their final section explicitly prioritizes a working MVP over incomplete breadth.
- Read public Jane Street repository archives without executing them; 23 obtained, including 2 README-only repositories. Evidence manifests, license boundaries and 10-aspect summaries recorded.
- Files: AGENTS.md, pyproject.toml, docs/implementation_plan.md, reference_evidence.json/reference_analysis.md, requirements_comparison.md.

## Phase 1–2 — data and calculation foundation
- Built strict UTC/finite OHLCV contracts, async demo provider, source isolation, retry/rate limit, immutable bar insert, SQLite WAL, point-in-time financial revisions, atomic Parquet snapshot and DuckDB reads.
- Added event bus and dirty-node DAG with batch updates, cycle checks, cached values/versions, subscription, rolling statistics and full-recalculation equivalence tests.
- Added 17 financial metrics, 15 technical indicator families with explicit VWAP proxy, six factor families, FCFF DCF/sensitivity/Monte Carlo.
- Command: `.venv/bin/python -m apps.worker.main` → six assets ×780 bars=4,680 rows, ingestion errors0.

## Phase 3–4 — research and risk
- Two fixed strategies, comparable BuyHold, next-bar open execution, previous-volume liquidity caps, partial fills, Decimal cash/integer shares, fees/spread/slippage/impact, corporate action handlers and risk/optimization/option analytics.
- Added Ridge/mean-baseline walk-forward with target purge/embargo, statistics and macro vintage selector.
- Command: `.venv/bin/python scripts/research_results.py` → all 12 strategy results saved, losses retained. All are synthetic simulations.
- Command: `.venv/bin/python benchmarks/run.py` → actual DAG/API/storage/ingestion/CPU/RSS measurements written to docs/benchmark_results.json.

## Phase 5–6 — integration and UI
- Connected FastAPI routes, optional bearer and per-IP limits, one-use WebSocket tickets, read-only calculation report and monitoring.
- Built Next/React/TypeScript/Tailwind/ECharts dashboard with eight functioning views, symbol/strategy/optimizer controls, DCF/factor inputs, Korean/English, keyboard navigation and mobile layout.
- First `npm run build` completed. First Python suite:64 passed; after macro/statistics and event integration:67 passed,98.32% statement coverage.
- First real browser run discovered missing Uvicorn WebSocket transport despite TestClient WS passing. Added explicit wsproto dependency, updated lock and rebuilt containers.
- Fixed NumPy2.5/Pandas2.x deprecation flood by constraining NumPy<2.4; 5,000+ warnings reduced to one test-transport deprecation warning.
- Browser navigation exposed stale response races: first a shape mismatch, then a late factor POST overwriting a new strategy response. Added request identity checks at render and completion; late results from prior views are discarded.
- Backup test initially could not import development scripts via the pytest entry point. Added explicit project-root pythonpath and reran the entire suite:71 passed,98.40% statement coverage.
- Ruff flagged assigned lambdas/unused imports; corrected. Mypy core contract/events/DAG/security subset passed.

## Execution infrastructure
- Nonroot Docker API/web images, localhost-only Compose ports8100/3100, named data volume, healthcheck, pinned Python constraints/npm lock, GitHub Actions configuration and Make targets.
- Docker daemon available. Initial build blocked in local credential helper; terminated only this build's processes and built public images through temporary anonymous config. User Docker config unchanged.
- SQLite online backup utility provides integrity check and digest; new target required.

## Final verification
- Python71 tests passed in5.52s; statement coverage98.40% on quantcore/apps.api. Ruff passed; Mypy selected8 files passed. One Starlette/httpx TestClient deprecation warning remains.
- Docker Compose API healthy and web running on8100/3100. Next.js production TypeScript build passed. Containers remain available locally.
- Actual Chromium10 scenarios passed: snapshot WS/chart, asset, DCF, technical, factor weight, both strategies, optimizer/risk, ML, language/keyboard, mobile. Browser JS errors0; no mobile horizontal overflow.
- Compared Linux Docker and macOS local data: maximum close error9.95e-14 USD, QALPHA Momentum net-return difference2.22e-16, portfolio VaR difference1.18e-10. Parquet byte hashes differ across platforms; numerical tolerance verified separately.
- Evidence: test_results.json, browser_results.json, container_validation.json, benchmark_results.json, research_results.json and README/performance_report.md. Screenshots saved under docs/screenshots (desktop) and ignored artifacts (mobile/full).
- CI workflow is provided; it has not been run on GitHub by this local task. No commit/push or external publication performed.

## Next work
Real provider/license review and explicit credentials, exchange calendars/corporate actions/versioned bars, real-market independent evaluation, remaining original feature families and production multi-user security. No unsupported capability is represented as completed.

## Backtest notebook — 2026-11-24
- Added `notebooks/QuantCore_Backtest.ipynb`:9 code cells,5 saved PNG figures,6 assets ×3 strategies including benchmark=18 comparisons. Whole-period returns, gross/net curves, drawdowns, next-open trade markers, monthly compounding, modeled-cost sensitivity and cash/inventory ledger are visible.
- Reused the existing backtest engine; no strategy, execution rule or prior research result changed. Reads local Parquet and verifies its manifest; missing files use the existing seeded provider in memory without changing the DB. Optional generated CSV/JSON go to ignored artifacts/notebook_backtest.
- Added optional notebook dependencies and lock entries, a dedicated user kernelspec `quantcore-py312` / `QuantCore (Python 3.12)`, Make notebook-setup/notebook-check targets, and `scripts/execute_backtest_notebook.py`.
- Commands: `.venv/bin/python -m pip install -e '.[dev,notebook]' -c requirements.lock`; `.venv/bin/python -m ipykernel install --user --name quantcore-py312 --display-name 'QuantCore (Python 3.12)'`; `.venv/bin/python scripts/execute_backtest_notebook.py --check-alternatives`; `.venv/bin/pytest`; `.venv/bin/ruff check .`; `.venv/bin/python -m pip check`.
- Initial execution exposed a missing Jinja2 dependency for pandas Styler; added it to notebook extras. The headless widget callback needed nbclient widget state tracking during execution; enabled tracking and removed transient widget state from the saved static notebook afterward.
- Validated3 scenarios:default252-bar QALPHA momentum; missing-data in-memory generation; QBETA mean_reversion126 bars with commission2bp. Each ran all9 cells, produced5 PNG outputs and0 cell errors. Actual dropdown/button callbacks were triggered during the audit.
- Default run matched all12 previously saved strategy returns exactly; QALPHA Momentum net+7.345436%. Fallback generation gave the same return. Custom case net−9.768125% is a different configuration and is explicitly not compared as the same saved experiment.
- Existing71 automated tests passed again. Ruff and pip dependency checks passed. Frontend and APIs were unchanged; no new frontend build was required for this notebook-only addition.
- Evidence:docs/notebook_validation.json. Synthetic data is prominently labeled in cells and plots; no real-market validation or automatic trading was added.

## Selected-kernel dependency repair — 2026-11-24
- Reported interpreter was the parent workspace `.venv312/bin/python`, rather than the fully prepared project `.venv/bin/python`. Missing pandas/ipywidgets/SQLAlchemy/PyArrow/Jinja2 explained the first-cell RuntimeError.
- Confirmed dedicated kernelspec still points to the project interpreter. Added project-local VS Code interpreter preference and expanded the notebook diagnostic with the exact recommended executable and restart steps. Existing parent workspace settings were not changed.
- Parent environment uses NumPy1.26.4 with computer-vision packages. Changed QuantCore's lower NumPy bound to1.26 because its numerical code is compatible; kept the <2.4 upper bound and the dedicated environment's NumPy2.3.5 lock unchanged.
- Snapshotted all71 existing parent package versions, performed a constrained pip dry-run, confirmed zero existing-version updates, then installed missing notebook/runtime dependencies with those versions pinned. Post-install check found zero changed/missing existing versions and zero missing notebook modules.
- Executed the actual selected interpreter through an in-memory KernelManager argv override without changing the registered kernelspec. Added --kernel-python/--no-save/--report options and explicit kernel cleanup to the execution helper.
- Selected NumPy1.26.4/Pandas2.3.3 environment:default/fallback/custom all passed,9 code cells and5 PNG per case,0 cell errors, widget callbacks passed. Default12 stored strategy returns matched exactly. Existing71 regression tests passed in3.55s in the dedicated environment; Ruff passed.
- Audit files:notebook_kernel_repair.json and notebook_selected_kernel_validation.json. The pre-existing MediaPipe platform diagnostic is unrelated to these additions; no claim that the whole shared environment has no prior issues is made.
- User action after package installation:restart the existing kernel, then Run All. No additional package installation or kernel switch is required for the reported `.venv312` interpreter.

## Dated notebook status in README — 2026-11-24 (KST)
- Checked the saved notebook and existing validation JSON, then added a dated status table to README:9 executed code cells,5 saved figures,0 cell errors,18 comparisons and12 matching strategy returns.
- Recorded the latest dedicated-kernel execution time as19:44 KST from the UTC validation timestamp, separately from the document date and the synthetic data period.
- Included both verified Python environments, dependency repair preserving71 package versions, latest regression results and links to source evidence. Consolidated repeated status paragraphs while retaining usage instructions.
- Documentation-only update; numerical results and notebook source were unchanged. Checked local Markdown links and consistency with recorded validation data.
