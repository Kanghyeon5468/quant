# QuantCore contributor instructions

- Work in this repository; preserve unrelated projects and existing user changes.
- Default to deterministic Demo/Research Mode. Never submit exchange orders.
- Do not reuse credentials or datasets from another project. Secrets belong in environment variables.
- Exception authorized by the user on 2026-11-25: the existing stock project's Alpaca settings may be read for market-data GET requests only. Do not copy secrets, reuse its datasets, or submit orders.
- Subsequent authorization on 2026-11-25: use that connection for Alpaca paper trading, including paper account/position/order queries and simulated order submission at https://paper-api.alpaca.markets only. The earlier market-data-only scope is extended for this task; live-money endpoints and orders remain prohibited. Keep credentials in memory and paper account records in ignored local artifacts.
- The user subsequently requested automatic paper buying and selling. Enable a persistent local scheduler using the same paper account, existing journal, Momentum strategy and $5,000 strategy ceiling; keep a documented pause/uninstall path. No real-money execution is authorized.
- Subsequent budget authorization on 2026-11-25: the user provided the $100,000 paper-cash balance for use. Increase the paper strategy ceiling to $100,000 and each of the five symbol slots to $20,000; use available cash, not the larger margin buying power. Preserve history, confirm own pending cancellations and audit the budget revision before sizing replacement paper orders. The previous $5,000 rollout ceiling is superseded.
- Keep provider provenance, UTC timestamps, currency, units, and availability time with data.
- A signal calculated at a bar close may execute only at a later bar.
- Use Decimal/integer quantities for the simulated cash ledger. Reject invalid data and infeasible constraints.
- Financial calculations belong in tested Python modules, not in language-model output.
- Update docs/progress.md and README.md with executed checks and measured results; label synthetic data explicitly.
- Prefer a modular monolith. Add dependencies only with a recorded reason.
- Run pytest, Ruff and the frontend build for relevant changes. Never describe unexecuted checks as passing.
