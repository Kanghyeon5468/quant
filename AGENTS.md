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

- Subsequent authorization on 2026-11-25: integrate actual financial/13F/news evidence into paper allocation and prepare source-grounded news/earnings LLM analysis. Keep the same $100,000 ceiling, Momentum base signal, audit trail and risk limits. Audited policy activation may cancel/replace only own pending paper orders; do not delete history. The user chose to configure the model/key later: no actual paid-model call or model download is authorized now; do not fabricate substitute analysis.

- Latest authorization on 2026-11-25 supersedes the model deferral: the user requested connection of their existing LLM API key with Claude Opus. Native Anthropic model lookup and bounded real-source paid inference are now authorized under the existing 3-request refresh/20-request daily cap. Keep the key local/in memory; never send other-provider keys or use an unapproved proxy, and preserve paper execution timing and risk limits.

- Subsequent explicit request on 2026-11-25: rerun actual Claude analysis and paper trading. The user confirmed specific manual closing sales and authorized recording those actual fills followed by re-entry. Use the ignored local approval record for the exact scope. Keep the original orders, realized loss and risk latches. A separately audited one-off manual request may use fresh completed regular-session IEX minute execution references outside the daily opening window; the normal automation timing, daily signal, $100000 cash ceiling and all risk limits remain unchanged. Unknown/unconfirmed external trades still block execution.
