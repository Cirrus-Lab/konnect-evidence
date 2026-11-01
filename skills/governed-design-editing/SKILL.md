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
- the command they run: `edagov konnect window approve WIN-…`.

Do not approve it yourself, and do not change `EDAGOV_ACTOR` to someone else. Wait for the user to confirm approval, then check with `gov_window_status`.

If the approver decides in chat and tells you to record their decision, you may run the approve command on their behalf, under these conditions:
- they name the window ID in an explicit approval ("Approve WIN-…"); a general "continue" or "do it" is not approval;
- you set `EDAGOV_ACTOR` to the approver identity they gave you, only for that one command;
- you pass `--note` stating that the decision was made in chat and executed by you.

Never carry one approval over to another window, and never infer approval from silence.

"Work without stopping" or "I won't be here" doesn't approve windows either.
- Before a long run, check the open window's `expires_at`.
- Request the next window early, while the person can still approve it.
- When a window expires with no approval waiting, stop editing. Use the rest of the time for read-only work (plans, documentation, checks), and leave the requested window ID for the person.

Scope the files to everything the call names, not only what it changes. Governance treats every path argument as a target, so `update_pcb_from_schematic` needs the root `.kicad_sch` in the window's `files` as well as the board, even though it only reads the schematic.

Builds without the fix in Cirrus-Lab/konnect-evidence#16 read any argument containing `/` as a path, including KiCad net names. On those builds, assigning a hierarchical net such as `/RF synthesis/ROD_E1` to a net class is refused as "outside the governed root". If you see that refusal, assign the net by a slash-free wildcard instead (`*ROD_E1`). Check what each pattern matches against the board's net list first, because `*CLK?` also catches `Net-(J3-SWCLK)`. Confirm the result with `get_netclasses`. Refused calls do not use up the window's call budget.

Net classes and board minimums live in `.kicad_pro`, and Konnect writes them only while KiCad is fully closed. Ask the person to close KiCad, then check that no `*.lck` file remains next to the project.

## 3. Edit

Make the change with Konnect tools. If a call comes back as an error of kind `plan_blocked` with a governance reason:
- outside the window's scope, file globs or call budget: stop and request a new window for exactly what is missing;
- revision released, file outside the repository, or no permitted role: stop and report it; these need a human decision;
- "governance check could not run": edagov is not reachable; report it and run `gov_doctor`. Do not switch `KONNECT_GOVERNANCE` off to get past it.

Never work around a refusal with another tool, a shell command or a direct file edit.

Keep one window open at a time when you can. With several approved windows open, a call can be checked against a narrow one and refused even though a broader window would cover it, so close each window as soon as its job is done.

Live edits made over KiCad IPC exist only in KiCad's memory until saved. After an IPC change (`update_pcb_from_schematic`, placement, zones), call `save_project` and confirm the file on disk changed before closing the window, so the ledger's post-hashes describe the saved board.

## 4. Close and re-check

1. `gov_window_close` when the change is done (or the window will simply expire).
2. `gov_ledger` lists every authorized and refused call and the files each edit changed. Report that list to the user.
3. Re-run evidence that the edit made stale: `gov_run_check` for ERC and DRC (with the user's authorization reason), `gov_spice_run` for affected simulations. Konnect's own `run_erc`/`run_drc` and audit results were captured as unreviewed `konnect:<tool>` evidence; mention them, but they do not satisfy gates.
4. `gov_gates` and `gov_pending_human_actions`: tell the user which reviews or approvals are now needed.

For the effect classes, modes and environment variables see `../eda-kicad-cloud-evidence-governance/references/konnect-integration.md`.
