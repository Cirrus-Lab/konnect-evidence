# Gitflow, GitHub reviews and traceability

## Choosing Gitflow

Use Gitflow only when scheduled release stabilization, parallel release work or hotfix isolation outweighs its divergence and CI cost; record that decision as an ADR. Lanes: production `main`/`master`, integration `develop`, short-lived `feature/*`, `release/*`, `hotfix/*`. Features merge to develop; releases merge to production and back to develop; hotfixes merge to both [1][2]. Gitflow is a convention, not a Git object type; topic branches with small logical commits are often preferred [3][4].

`edagov` classifies branches into lanes and flags a PR whose base breaks the convention (`merge_target_matches_convention: false`).

## Repository controls

Define: controlled artifact types; branch naming, base and merge targets; deletion and tag rules (tag released revisions, e.g. `hw/PCB-X/B`); issue and revision IDs; required commit/PR references; design-review entry/exit criteria; independent reviewer roles; approve/request-changes/abstain/re-review/exception rules; required checks; CODEOWNERS; protected branches; signed commits; conversation resolution; override audit [4][5].

Protected branches can require approving reviews (optionally from code owners), dismissal of stale approvals on new commits, passing status checks, conversation resolution and signed commits. Approvals relate to a specific diff. Administrator overrides need recorded authority and reason [5]. The plugin ships `governance/ci/design-repo/.github/CODEOWNERS.example`, a PR template and an issue template to copy into the design repository; adapt owners per path (schematics, layout, BOM, fab outputs, `.edagov/policy.json`, `.edagov/roles.json`).

## PR content

Use the PR template from `governance/ci/design-repo/.github/pull_request_template.md`: issue ID, purpose, affected artifacts, design revision/variant, risk, validation evidence (record IDs), reviewers, unresolved issues, release impact, and the claim-scope checklist. Run `edagov lint-claims` on the PR body.

Issue-closing keywords (`Closes #17`) auto-close only when the PR merges into the **default branch**. In Gitflow most PRs target `develop`, so the issue is only linked; close it explicitly at release [6]. `edagov ingest github` marks each reference as `auto_close` or `linked only`.

## Read-only sync

`edagov ingest github owner/repo <PR>` (uses `gh api` if authenticated, else `GITHUB_TOKEN`/`GH_TOKEN` from the environment; never stores the token) records repository, number, URL, title, observed state, base/head, Gitflow lane, latest review per reviewer (approvals on an older commit are `stale_dismissed`), required approvals versus approvals on the current diff, code-owner requirement, required and blocking checks, conversation and signature requirements, issue links, `sync_state` and correlation ID. A 401/403/404 or network failure is recorded as `unauthorized`/`unavailable`/`timeout`; the previous observation is kept and marked provisional. The toolkit never writes to GitHub.

## Projects

GitHub Projects provide views, fields, charts and linked issue/PR state but impose no method [7]. Document project scope, field and state definitions (map them to the gate and issue vocabularies), and any repository automation and its authentication.

## CI gate

`governance/ci/design-repo/.github/workflows/eda-evidence.yml` (copy it into the design repository and pin `EDAGOV_REF` to a tag) runs on PRs to `develop`, `main`, `release/**`, `hotfix/**`: installs KiCad 10 and ngspice, runs `edagov doctor`, executes ERC/DRC with `EDAGOV_EXECUTION=allow:ci`, lints claims in the PR body, scans for secrets, evaluates gates, verifies the audit chain, renders the dashboard and uploads the store as an artifact (CI never pushes evidence; a human commits what they accept). It fails on blocked gates for PRs into `main` and `release/*`. Make the `edagov-gates` job a required status check on protected branches. CI identity is recorded as unverified unless you set `EDAGOV_ACTOR_VERIFIED_BY` from a verified OIDC claim.

## Traceability path

requirement → architecture decision → issue → branch/commit → PR/review → artifact/run → release package → approval. Every record carries design ID, revision, variant and evidence links, so `edagov snapshot` + `edagov diff` can compare two revisions without opening KiCad files.

## References

[1]: https://nvie.com/posts/a-successful-git-branching-model/ "A Successful Git Branching Model"
[2]: https://github.com/petervanderdoes/gitflow-avh "gitflow-avh"
[3]: https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow "Gitflow Workflow"
[4]: https://git-scm.com/docs/gitworkflows "Git Workflows"
[5]: https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches "GitHub Protected Branches"
[6]: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue "Linking Pull Requests to Issues"
[7]: https://docs.github.com/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects "GitHub Projects"
