# PARITY-REPORT: <KEY>

| Field | Value |
| --- | --- |
| Verdict | PARITY / PARITY WITH APPROVED DELTAS / GAPS |
| Source (anchor) | path @ commit |
| Replica | path @ commit / working tree |
| Date | YYYY-MM-DD |

## Level 1 - Static coverage

| Behavior / REQ | Status in spec | Implemented at | Result |
| --- | --- | --- | --- |
| RULE-001 | REUSE | `CreditNoteProcessor.java:14` | PASS |

## Level 2 - Rule tests

| Item | Test | Result |
| --- | --- | --- |
| RULE-001 | `CreditNoteProcessorTest.filtersZeroAmount` | PASS |

Command: `./mvnw -q -o test` -> exit 0 (N tests, 0 failures)

## Level 3 - Output parity

| Flow | Fixture | Command | Expected diffs | Unexpected diffs | Result |
| --- | --- | --- | --- | --- | --- |

Diff reports: `.replication/parity/diff-*.md`

## Level 4 - Contracts and operations

| Check | Anchor | Replica | Result |
| --- | --- | --- | --- |
| Step names | | | |
| Exit codes | | | |
| Schedule + zone | | | |

## Requirement -> test traceability

| REQ | Priority | Test(s) | Result |
| --- | --- | --- | --- |

## NOT RUN

| Check | Reason | What unblocks it |
| --- | --- | --- |

## Follow-ups
