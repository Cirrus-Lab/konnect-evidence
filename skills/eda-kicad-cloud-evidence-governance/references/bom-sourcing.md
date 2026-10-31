# BOM, sourcing, lifecycle and alternates

## BOM line contents

Each line keeps: internal item and revision, exact manufacturer and orderable MPN (with packaging/temperature suffix), functional description, package/case, ratings/grade/temperature, quantity and references, effectivity, approved source/channel, lifecycle state with evidence date and source, PCN/EOL and last-buy data, compliance certificates, packaging/storage/ESD/moisture rules, lot/date-code/country-of-origin requirements, risk class, and links or hashes to authoritative evidence [1][2]. Keep raw received date and lot codes and cite the manufacturer's interpretation; distributor normalization can be wrong.

## Ingest

`edagov ingest bom bom.csv --project <kicad-dir>` maps common column names (see `src/edagov/bom.py` COLUMN_ALIASES), expands ranges like `R1-R4`, and cross-checks references against the schematic inventory. Findings per line:

| Code | Severity | Trigger |
|---|---|---|
| no_mpn / generic_mpn / no_manufacturer | blocking | no exact orderable part (values like `10k`, `TBD` are rejected) |
| qty_mismatch / duplicate_reference | blocking | quantity ≠ reference count; a reference on two lines |
| lifecycle_risk | blocking (warning if PCN/EOL recorded) | EOL, obsolete, NRND, last-time-buy, discontinued |
| lifecycle_unknown / lifecycle_source_missing / lifecycle_stale | warning | missing, unsourced or older than `freshness_days.lifecycle` |
| alternate_unsupported | blocking | engineering/production-approved alternate without equivalence matrix and qualification evidence |
| alternate_state_invalid / disallowed_part_in_bom | blocking | state outside the vocabulary; disallowed part in the build |
| headline_equivalence | attention | "drop-in", "pin-compatible", cross-reference language | <!-- claims:example -->
| broker_source | warning | broker/independent channel: escalate |
| source_not_allowlisted / no_approved_source | attention / warning | policy `approved_sources` allowlist |

## Lifecycle

Lifecycle status is manufacturer-specific and dated. IEC 62402 defines an obsolescence-management framework, not a guarantee [1]. Manufacturer longevity programs have stated scopes, conditions and exceptions; store the exact program, launch/evidence dates, status and notice source. PCN/EOL windows vary per manufacturer.

## Alternates

Alternates are states, not notes: `candidate`, `engineering_approved`, `production_approved`, `disallowed`. An approved alternate records replaced and replacement orderable numbers, an equivalence matrix (ratings, tolerances, package, pinout, firmware, process, environmental/regulatory differences), qualification evidence, sample/lot, approver/date, affected BOM revisions and rollback. "Drop-in", same package, a distributor cross-reference or matching headline parameters are not evidence.

## Procurement controls

Define approved-source allowlists, broker escalation, exact PO wording, certificate of conformance and traceability, receiving inspection, quarantine, counterfeit/suspect reporting, disposition, monitoring owner, retention, and separation of design, procurement and alternate approval. Authorized distribution reduces risk but does not prove authenticity or fit [2].

## References

[1]: https://webstore.iec.ch/en/publication/59531 "IEC 62402:2019 Obsolescence management"
[2]: https://www.digikey.com/-/media/PDF/Sitemap/DigiKey-Counterfeit-Control-Plan.pdf "DigiKey Counterfeit Control Plan"
