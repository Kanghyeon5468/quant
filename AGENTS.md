# QuantCore contributor instructions

- Work in this repository; preserve unrelated projects and existing user changes.
- Default to deterministic Demo/Research Mode. Never submit exchange orders.
- Do not reuse credentials or datasets from another project. Secrets belong in environment variables.
- Keep provider provenance, UTC timestamps, currency, units, and availability time with data.
- A signal calculated at a bar close may execute only at a later bar.
- Use Decimal/integer quantities for the simulated cash ledger. Reject invalid data and infeasible constraints.
- Financial calculations belong in tested Python modules, not in language-model output.
- Update docs/progress.md and README.md with executed checks and measured results; label synthetic data explicitly.
- Prefer a modular monolith. Add dependencies only with a recorded reason.
- Run pytest, Ruff and the frontend build for relevant changes. Never describe unexecuted checks as passing.
