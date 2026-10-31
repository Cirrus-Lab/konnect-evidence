---
name: governed-design-editing
description: Runs a KiCad design change through Konnect under evidence governance, using a reviewer-approved change window, Konnect edits, the call ledger and re-run checks. Use when the user asks to add, wire, place, move, route, delete or otherwise change schematic, PCB, library or rule content in a design that has an .edagov evidence store, or when a Konnect tool call is refused with a governance (plan_blocked) error.
---

# Governed design editing

In a governed design Konnect refuses every design-changing tool unless a change window covers it. A window is requested by the person doing the work and approved by someone else. Follow this loop exactly; it is how edits stay attributable and reviewable.

## 1. Orient

- Call `gov_status` for the design identity, your actor and roles, open windows and pending approvals.
- Read the current state with Konnect's read tools, and use dry runs of apply-mode tools (`update_pcb_from_schematic`, `place_decoupling_caps`, `fix_connectivity` with `dry_run: true`, …). Reads and dry runs are never blocked.
- Decide the smallest scope: which Konnect toolsets (`sch_wiring`, `sch_components`, `pcb_components`, `pcb_routing`, …) or single tools (`tool:add_power_symbol`), which files (globs relative to the repository root), how many calls, how many hours.

## 2. Request the window

Call `gov_window_request` with `scope`, `reason` (what and why, in one sentence), `issue` when one exists, `files`, `hours` and `max_calls`. Then tell the user, in one short message:
- the window ID and its scope;
- who may approve it (a design_reviewer or release_approver other than the requester);
- the command they run: `edagov konnect window approve WIN-…`, or, when they use the review console (`edagov-review.py`, started in their own terminal as the reviewer), that the window is waiting there.

Do not approve it yourself, and do not change `EDAGOV_ACTOR` to someone else. Never start the review console as the reviewer, read its decision PIN, or call its decision endpoint. Wait for the user to confirm approval, then check with `gov_window_status`.

## 3. Edit

Make the change with Konnect tools. If a call comes back as an error of kind `plan_blocked` with a governance reason:
- outside the window's scope, file globs or call budget: stop and request a new window for exactly what is missing;
- revision released, file outside the repository, or no permitted role: stop and report it; these need a human decision;
- "governance check could not run": edagov is not reachable; report it and run `gov_doctor`. Do not switch `KONNECT_GOVERNANCE` off to get past it.

Never work around a refusal with another tool, a shell command or a direct file edit.

## 4. Close and re-check

1. `gov_window_close` when the change is done (or the window will simply expire).
2. `gov_ledger` lists every authorized and refused call and the files each edit changed. Report that list to the user.
3. Re-run evidence that the edit made stale: `gov_run_check` for ERC and DRC (with the user's authorization reason), `gov_spice_run` for affected simulations. Konnect's own `run_erc`/`run_drc` and audit results were captured as unreviewed `konnect:<tool>` evidence; mention them, but they do not satisfy gates.
4. `gov_gates` and `gov_pending_human_actions`: tell the user which reviews or approvals are now needed.

For the effect classes, modes and environment variables see `../eda-kicad-cloud-evidence-governance/references/konnect-integration.md`.
