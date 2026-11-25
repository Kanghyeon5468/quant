.PHONY: setup demo api web test check benchmark report notebook-setup notebook-check real-setup real-backtest real-notebook-check
setup:
	python3.12 -m venv .venv
	.venv/bin/pip install -e '.[dev]' -c requirements.lock
	cd apps/web && npm ci
demo:
	.venv/bin/python -m apps.worker.main
api:
	.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8100
web:
	cd apps/web && npm run dev -- --port 3100
test:
	.venv/bin/pytest --cov --cov-report=term-missing --cov-report=json:artifacts/coverage.json
check:
	.venv/bin/ruff check .
	.venv/bin/mypy quantcore/core quantcore/events quantcore/incremental quantcore/security --follow-imports=skip
	cd apps/web && npm run build
benchmark:
	.venv/bin/python benchmarks/run.py
report:
	.venv/bin/python scripts/research_results.py
notebook-setup:
	[ -x .venv/bin/python ] || python3.12 -m venv .venv
	.venv/bin/pip install -e '.[notebook]' -c requirements.lock
	.venv/bin/python -m ipykernel install --user --name quantcore-py312 --display-name 'QuantCore (Python 3.12)'
notebook-check:
	.venv/bin/python scripts/execute_backtest_notebook.py --check-alternatives
real-setup:
	[ -x .venv/bin/python ] || python3.12 -m venv .venv
	.venv/bin/pip install -e '.[notebook,realdata]' -c requirements.lock
	.venv/bin/python -m ipykernel install --user --name quantcore-py312 --display-name 'QuantCore (Python 3.12)'
real-backtest:
	.venv/bin/python scripts/run_real_backtest.py
real-notebook-check:
	.venv/bin/python scripts/execute_real_notebook.py
