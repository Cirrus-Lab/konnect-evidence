# MCP and connector safety

MCP is an interoperability protocol, not an authorization or safety guarantee. It does not enforce authorization, human approval, least privilege, event delivery semantics or audit policy [1].

## Version note (recorded conflict)

The source guidance cites the MCP architecture, authorization and tools pages at specification **2026-07-28** but the transports page at **2025-06-18**. The 2026-07-28 release moved to a stateless core (no required initialize handshake or server session IDs), routes requests by an `Mcp-Method` header, adds a `ttlMs` cache hint to `tools/list`, tightens OAuth/OIDC validation, moves tool input schemas to JSON Schema 2020-12, and deprecates Roots, Sampling and Logging [2][3]. Treat transport guidance as version-scoped: record the **negotiated** protocol version per connector and do not mix rules across versions without saying so.

## Registry

`edagov connector register` (connector_admin only) records provider, protocol and version, transport, endpoint (no credentials), scopes, data classes, trust tier (`untrusted` by default, then `verified_read` / `verified_write`), logical secret reference, owner, and governance notes. Also record host/client/server roles, the one-client-per-server connection map, token audience, expiry/revocation and data flows [1][4].

Transport rules:
- **STDIO:** stdout carries only protocol messages; credentials come from the environment, not HTTP authorization [5].
- **Streamable HTTP:** validate `Origin`, authenticate, bind local servers to localhost [5].
- Tool annotations and provider status are untrusted metadata. Validate inputs and outputs independently; servers validate, enforce access, rate-limit and sanitize; clients validate results, use timeouts, confirm sensitive operations, show inputs and log invocations [6].

Record sync attempts: `edagov connector sync --id CON-… --state synced|unauthorized|unavailable|timeout|partial|invalid --error … --correlation …`.

## Governed actions

1. Classify the action: read, create, change, publish, purchase, release, delete. publish/purchase/release/delete always need human approval; any non-read or irreversible action does too.
2. `edagov connector propose --id CON-… --verb … --target … --input k=v … --side-effect … [--reversible] [--compensation …] [--dry-run-available]`. Inputs containing credential-shaped values are rejected. Show the printed proposal to the user verbatim.
3. A different person with `release_approver` approves: `edagov connector approve --id ACT-…`. The proposer cannot approve a sensitive action. Approval expires after 24 h and is void if the design revision changes.
4. Immediately before invoking the tool, run `edagov connector check --id ACT-…`. Proceed only on `ALLOWED`. Prefer dry-run, read-only, reversible and idempotent calls; send the recorded idempotency key when the API supports one.
5. Record the outcome with evidence (response hash, external object ID/URL): `edagov connector outcome --id ACT-… --result success|failed|unknown|compensated|dead_lettered --evidence … --external-id …`. A success without evidence is rejected. A successful outcome consumes the idempotency key.

## Event-driven automation

Define event schema and version, owner, correlation and idempotency keys, delivery/ordering/duplication semantics, retries/backoff/timeouts, dead-letter and replay, compensation/rollback, and human escalation. Queues and workflow engines buffer and manage state; they do not guarantee exactly-once delivery, ordering or downstream success [7]. Distinguish notifications, reversible workflows and irreversible or regulated effects.

## References

[1]: https://modelcontextprotocol.io/specification/2026-07-28/architecture "MCP Architecture"
[2]: https://github.com/modelcontextprotocol/specification/releases/tag/2026-07-28 "MCP specification release 2026-07-28"
[3]: https://www.developersdigest.tech/blog/mcp-2026-07-28-breaking-changes "MCP 2026-07-28 breaking changes (secondary summary)"
[4]: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization "MCP Authorization"
[5]: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports "MCP Transports (2025-06-18)"
[6]: https://modelcontextprotocol.io/specification/2026-07-28/server/tools "MCP Tools"
[7]: https://aws.amazon.com/what-is/eda/ "AWS Event-Driven Architecture"
