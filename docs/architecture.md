# HumanityOS Architecture: first vertical slice

## Scope
The Opportunity Agent currently supports **user-supplied candidates** only.
It is not yet connected to search providers, crawlers, mail, calendars, or submission sites.
`run-once` is a bounded, triggerable worker pass, **not** an always-running scheduler.

## Security boundaries
- Bearer key is required on every data endpoint; no fallback credentials.
- Local-only development binding on 127.0.0.1.
- A successful keyword match is **not** verified eligibility or a validated source.
- The human approval state is a local decision record and never triggers external execution.
- No model-generated commands, network fetches, external tools, or application submission paths exist.
- Every candidate transition records an event. SQLite is a prototype audit log, not tamper-proof.
- Not production multi-user or internet-facing. Before deployment: identity/tenancy, migrations,
  CSRF/CORS policy, queue locking, key rotation, rate limiting, encrypted storage and backups.

## Workflow
1. Create a goal with explicit keywords.
2. Queue a manually supplied opportunity and source URL.
3. Run one worker pass or evaluate a specific candidate.
4. Review the explanatory screening and its limitations.
5. Approve or reject; approval only records a decision.

## Next release
- Official, allowlisted opportunity-source ingestion (with SSRF protection and source versioning).
- Background schedule with leases and recovery.
- Evidence retrieval, citation checking, and deadline extraction with error accounting.
- Human-authorized messaging/actions through a separate permission gateway.
- Additional negative authorization, fuzz, concurrency and integration testing.
