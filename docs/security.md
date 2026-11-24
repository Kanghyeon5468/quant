# Security and operational boundary

Default: local Demo/Research only. No exchange clients, broker credentials, order endpoints or live mode. API keys from previous projects are never read. `.env`, local databases, node_modules, generated browser artifacts are ignored.

`QUANTCORE_API_TOKEN` optionally protects `/api/*` with constant-time bearer comparison. Capability is a single researcher role: read data and request calculations; no administration or order submission API exists. This is not multi-user RBAC. `/health` is anonymous. Rate limit: 180 API requests per client/IP per minute, in-process memory. CORS restricts configured local dashboard origins.

Browser WebSocket obtains a 30-second, single-use random ticket via authenticated API; raw API secret is not embedded into browser code. Origin must be allowed, ticket is consumed, reused tickets fail. HTTP BFF stores API token server-side. The BFF is intended for a loopback single-user dashboard; it is **not** a substitute for browser user authentication. Before remote exposure, add user authentication/authorization, TLS/reverse proxy, persistent/distributed rate controls and secure audit retention.

Pydantic validates finite values and ranges; SQLAlchemy/DuckDB bind parameters. No user-provided URL fetch or arbitrary code execution. API computation inputs are bounded; long-running research requests should be queued before multi-user deployment.

Audit records ingestion insert counts and failures. SQLite online backup uses a new destination, integrity_check and digest; recovery should be rehearsed before production. Secrets must not be written to audit logs. Filesystem backup destination and environment config are operator privileges, not exposed through HTTP.
