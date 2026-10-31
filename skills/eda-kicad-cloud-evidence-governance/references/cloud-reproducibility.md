# Cloud execution, storage, secrets and reproducibility

## What edagov captures automatically

Every executed run records: exact command, working directory, tool and version, platform, `TZ`/locale (forced to UTC and C.UTF-8 unless set), input file hashes, exit code and status (completed/timeout/tool_missing), stdout/stderr logs and their hashes, output hashes, and `provenance.intoto.json`: an unsigned in-toto Statement v1 with a SLSA provenance v1 predicate (`buildDefinition.externalParameters`, `resolvedDependencies`, `runDetails.metadata`) [1]. The statement is a record of what ran; it is not a SLSA build-level claim.

Reproducibility levels: **bit-for-bit** (never claimed for KiCad outputs, which embed timestamps), **exact rerun** (same inputs, tool build and command; the default promise), **scientifically equivalent** (same conclusions within stated tolerance; state the tolerance).

## Running in CI or a persistent machine

- Separate compute, storage, identity, execution, provenance and lifecycle. A persistent VM or volume does not make data durable by itself: document capacity, access mode, locality, backup/restore, reclaim policy, retention and deletion. Kubernetes PersistentVolumes have lifecycles independent of Pods [2].
- Prefer immutable or ephemeral compute with pinned images. Image tags are mutable; record the base-image digest and a patch policy [3]. Record source/workflow revision, engine version, OS/architecture, image digest, inputs and hashes, configuration, seeds, timezone/locale, floating-point policy, network policy, resource limits, retries/checkpoints, expected outputs, logs, attestation, retention and failure states [1][4].
- The design-repo GitHub Actions template (`governance/ci/design-repo/.github/workflows/eda-evidence.yml`) installs KiCad from the official PPA and ngspice from Ubuntu, sets `EDAGOV_EXECUTION=allow:ci`, runs checks, evaluates gates and uploads the evidence store. Pin the runner image and record the installed KiCad version (the workflow does) because PPA packages move.

## Secrets

- Never put secret values in source, images, logs or ordinary artifacts. Record only a logical secret ID and version/lease, owner, scope, rotation/revocation, injection path and audit trail [5][6].
- Kubernetes Secrets are stored unencrypted in etcd by default; require encryption at rest, least-privilege RBAC and container scoping, preferably an external secret store [5].
- Prefer workload identity federation or short-lived credentials over long-lived keys [7]. In GitHub Actions use OIDC where the target supports it, and the default `GITHUB_TOKEN` with least permissions.
- `edagov scan-secrets <paths>` flags private keys, cloud/API tokens, JWTs, bearer headers, password assignments and credentials embedded in URLs. Snapshots redact matches and list where they occurred.

## Before re-running an unsafe or unreproducible job

Check scopes, human approval, endpoint/origin, idempotency key, secret reference, image digest, input hashes, retry behaviour and provenance.

## References

[1]: https://slsa.dev/spec/v1.2/build-provenance "SLSA Build Provenance v1.2"
[2]: https://kubernetes.io/docs/concepts/storage/persistent-volumes/ "Kubernetes Persistent Volumes"
[3]: https://docs.docker.com/build/building/best-practices/ "Docker Build Best Practices"
[4]: https://reproducible-builds.org/docs/deterministic-build-systems/ "Deterministic Build Systems"
[5]: https://kubernetes.io/docs/concepts/configuration/secret/ "Kubernetes Secrets"
[6]: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html "OWASP Secrets Management Cheat Sheet"
[7]: https://cloud.google.com/iam/docs/workload-identity-federation "Google Cloud Workload Identity Federation"
