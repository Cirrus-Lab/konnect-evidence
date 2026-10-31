# Evidence schema

Reference for the design-level record kept in `.edagov/`. Implemented in `src/edagov/schema.py` and `vocab.py`; this file is the human-readable contract.

## Storage model

- `.edagov/design.json` holds the **design identity**: `product_id`, `design_id`, `board_id`, `assembly_id`, `revision`, `variant`, `release_state`, `design_authority`, `repository`, `applicable_standards`, plus `previous_revision` after a `revision` move.
- `.edagov/records/<type>/<ID>.v0001.json` holds records. Versions are immutable: a change writes `v0002`, never edits `v0001`. `record_version` and `supersedes_version` link them.
- `.edagov/audit.jsonl` is a hash-chained, append-only log. Each event stores hashes of the before/after state, not raw payloads.
- `.edagov/runs/<RUN-ID>/` holds logs, reports, parsed output, frozen inputs and `provenance.intoto.json`.
- `.edagov/policy.json` (gate rules, freshness windows) and `roles.json` (actor → roles) are part of the reviewed record. Change them through a PR.

Commit `.edagov/` to the design repository. It is the evidence, so it is reviewed like code.

## Identity and linkage rules

- Every design-scoped record carries `design_id`, `revision` and `variant`. The store fills them from the identity at write time.
- Every file reference carries a content hash (`sha256:<hex>`). External URLs are recorded as `unhashed:external-reference` with a limitation, because their content can change.
- `source_revision` is the git commit (with `+dirty` when the tree had uncommitted changes) or `untracked`.
- IDs are stable and human readable. Prefixes: `PRD` product, `DES` design, `REQ` requirement, `BLK` architecture block, `ART` artifact, `RUN` run, `BOM` BOM line, `MFG` manufacturing package, `ISS` issue, `EXC` exception, `REV` review, `APR` approval, `ADR` decision, `ASM` assumption, `CON` connector, `ACT` connector action, `GH` GitHub PR, `GATE` gate evaluation.

## Entities and required fields

| Type | Required (beyond id/type/created_at and design identity) |
|---|---|
| requirement | text, source, owner, priority, verification_method (inspection/analysis/simulation/test/demonstration/supplier_confirmation/review), acceptance, status |
| architecture_block | name, purpose, owner, interfaces, allocated_requirements |
| artifact | kind, path, hash, source_revision, owner (optional: tags, claim_scope, reviewer, provenance, license) |
| run | tool, tool_version, inputs[{path,hash}], result_class, claim_scope, executed |
| bom_line | internal_item, manufacturer, mpn, references, quantity, lifecycle (optional alternate_state + evidence) |
| manufacturing_package | board_id, revision, variant, files[], completeness |
| issue | title, severity (low/medium/high/critical), state (open/contained/accepted/closed/superseded), owner, affected |
| exception | title, rationale, approver, approved_at, review_trigger, affected_claims |
| review | target, target_revision, reviewer, reviewer_role, state |
| approval | gate, decision, approver, approver_role, target_revision, evidence (+ evidence_fingerprint) |
| connector | provider, protocol, protocol_version, transport, scopes, trust_tier, sync_state |
| connector_action | connector, action, target, inputs, affected_revision, idempotency_key, action_state |
| github_pr | provider, repository, number, sync_state, last_sync_attempt, correlation_id |
| decision | title, rationale, alternatives, consequences, status |
| assumption | text, owner, review_condition |

Schema-level invariants:
- A run that was not executed and has no ingested report cannot be `clean`.
- A BOM line cannot hold `engineering_approved`/`production_approved` without `equivalence_matrix` and `qualification_evidence`. On ingest an unsupported claim is kept as `alternate_state_claimed` and the line is blocked.
- `approved_with_exception` must link exception IDs.

## Status envelope

Every status-bearing record also carries `state`, `severity`, `timestamp`, `source`, `owner`, `linked_evidence`, `next_action`. Severity vocabulary: `info`, `attention`, `warning`, `blocking`, `approved`. Issues use their own severity scale.

## Controlled vocabularies

- **Gate states:** not_started, in_progress, ready_for_review, approved, approved_with_exception, blocked, rejected, superseded, not_applicable (with rationale). Automation may set only the first three plus blocked.
- **Freshness:** current, stale, future-dated, unknown, missing. Freshness is independent of approval. Windows come from `policy.json` (`freshness_days`).
- **Run result classes:** clean, violations, converged_with_warnings, altered_settings, failed, tool_error, conflict, not_checked, invalid.
- **Review states:** not_started, in_progress, approved, requested_changes, blocked, abstained, expired, superseded.
- **Failure/uncertainty states:** loading, empty, not_configured, stale, partial, unavailable, unauthorized, conflict, invalid, timeout, queued/retrying, dead_lettered.
- **Alternate states:** candidate, engineering_approved, production_approved, disallowed.

Never collapse "no data", "not applicable", "not checked" and "passed" into one value.
