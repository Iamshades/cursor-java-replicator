# REPLICATION-SPEC: <KEY> - <summary>

| Field | Value |
| --- | --- |
| Ticket(s) | <KEY> (+ linked) |
| Mode | extend-in-place / clone-new-app / modernize-replicate |
| Source app | path, commit |
| Target | path / new module / new repo |
| Target baseline | Java __, Spring Boot __, Spring Batch __ |
| Anchor flow(s) | JOB-... / EP-... |
| Status | draft / approved (by, date) |

## 1. Requirements

| ID | Requirement | Type | Priority | Source | Acceptance check |
| --- | --- | --- | --- | --- | --- |
| REQ-<KEY>-01 | | functional | MUST | AC #1 | Scenario S-01 |

## 2. Behavior coverage matrix

Every behavior of the anchor flow appears here, whether or not the ticket mentions it.

| Behavior (source) | Evidence | Status | Requirement | Target behavior |
| --- | --- | --- | --- | --- |
| RULE-003 zero-amount items skipped | `InvoiceProcessor.java:15` | REUSE | implicit:anchor | same |
| STEP-x reader SQL filter | `...Config.java:88` | ADAPT | REQ-<KEY>-02 | see D-01 |
| (none) | - | NEW | REQ-<KEY>-05 | trailer `T|<count>` |
| listener emails ops | `...Listener.java:22` | DROP | REQ-<KEY>-07 | no email; alert via ... |

Counts: REUSE _ / ADAPT _ / NEW _ / DROP _ / UNCLEAR _

## 3. Deltas (exact)

| ID | Where in source | Old | New | Requirement |
| --- | --- | --- | --- | --- |
| D-01 | `path:line` | `status = 'APPROVED'` | `type = 'CREDIT_NOTE' AND status = 'APPROVED'` | REQ-<KEY>-02 |

## 4. Data contracts

### Input
Source, query or layout, ordering, volume.

### Output
| # | Field | Type/format | Source | Same as anchor? |
| --- | --- | --- | --- | --- |

Header / trailer / file naming / encoding / line ending.

## 5. Non-functional and operational

Schedule + time zone, volumes, run window, chunk size, restart behavior, idempotency, alerting, retention/archival, security (credentials via ...), environments, parallel run plan.

## 6. Assumptions

| ID | Assumption | Risk if wrong |
| --- | --- | --- |

## 7. Open questions

| ID | Question | Blocks | Owner | Answer |
| --- | --- | --- | --- | --- |

## 8. Acceptance scenarios

```gherkin
Scenario: S-01 ...
```

| Scenario | Requirement(s) | Test (planned) |
| --- | --- | --- |
