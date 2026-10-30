---
name: java-parity-verifier
description: Prove that a replicated or modernized Java implementation behaves like the source app except for the approved deltas - golden-file and output comparison for batch jobs (delimited, fixed-width, JSON, text), rule-by-rule test coverage checks, contract checks for endpoints and listeners, and a requirement-to-test traceability report. Use after implementing a replica, when asked "does the new job match the old one", to compare two batch outputs, or as stage 5 of java-replicate.
metadata:
  version: "1.0.0"
  stage: "5-verify"
---

# Java Parity Verifier

Inputs: `REPLICATION-SPEC.md`, `PLAN.md`, flow files, the new code. Output: `.replication/PARITY-REPORT.md` from `assets/templates/parity-report.md`. Contract: `../java-replicate/references/artifact-contract.md`.

Pick checks with `references/parity-strategies.md`. Run all four levels that apply; report each honestly as PASS, FAIL, or NOT RUN (with reason).

## Level 1 - Static coverage (always)

For every row of the spec's behavior coverage matrix with status `REUSE` or `ADAPT`, and every `NEW` requirement, find the implementing code and cite `path:line`. Missing ones are FAIL. For `DROP`, confirm the behavior is absent.

## Level 2 - Rule tests (always)

Every kept `RULE-`, every `D-` delta, and every `MUST` requirement has at least one test that would fail if it broke. List test class and method per item. Read the test: an assertion-free test or one that asserts the mock it set up does not count.

## Level 3 - Output parity (batch jobs, file/DB outputs)

Run the anchor and the replica on the **same fixture input** and compare outputs. Requires build/run permission and a safe local datasource (H2, Testcontainers, or a schema the user names). Never point at shared or production databases.

```bash
python3 <this-skill-dir>/scripts/compare_outputs.py old.txt new.txt \
  --format delimited --delimiter '|' --header-lines 1 --trailer-lines 0,1 \
  --key invoiceId --columns invoiceId,customerCode,amountCents,currency,issuedOn \
  --expect-diff amountCents,trailer --report .replication/parity/diff-exportCreditNotes.md
```

- `--expect-diff` lists columns (or `header`, `trailer`) the spec changes (`ADAPT`/`NEW` deltas); differences there are reported but do not fail the run. Any other difference fails. Exit 0 = pass, 1 = unexpected diffs.
- `--header-lines` / `--trailer-lines` take `N` or `OLD,NEW` when the replica adds or removes a header/trailer.
- `--mask REGEX` hides volatile values (timestamps, run ids) before comparison.
- `--ignore-order` or `--key` for unordered outputs (partitioned, multi-threaded).
- Formats: `delimited`, `fixed` (`--widths 10,8,12`), `json` / `jsonl`, `text`. Directories compare file by file (`--rename 'INV_(.*)=CN_\1'` maps names).
- DB outputs: export both result sets ordered by key to CSV first, then compare as `delimited`.

When the replica intentionally selects different records (e.g. credit notes instead of invoices), build a fixture where both select the same logical records, or compare the replica to an expected golden file derived from the anchor's output plus the deltas. State which approach you used.

## Level 4 - Contracts and operations (endpoints, listeners, schedules)

- Endpoint/listener: request and response field names, types, formats, status codes, error bodies vs the anchor's flow file and any OpenAPI spec.
- Operations: job and step names, parameters, exit codes, restart behavior, schedule and zone, config keys per profile, logging/alerts.

## Report

Fill `PARITY-REPORT.md`: summary verdict (`PARITY`, `PARITY WITH APPROVED DELTAS`, `GAPS`), table per level, commands run with exit codes, unexpected diffs with sample rows, NOT RUN items with what would unblock them, and the requirement -> test traceability table. Then tick verification tasks in `PLAN.md`.

Never call it parity when a level was skipped; say "static and rule checks pass; output parity NOT RUN (no fixture data)".
