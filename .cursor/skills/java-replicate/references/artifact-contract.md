# `.replication/` artifact contract

Single source of truth for files the skills exchange. Every skill reads its inputs from here and writes its outputs here, so stages can run in separate chats, be resumed, or be reviewed in a PR.

## Layout

```text
.replication/
├── README.md               # scope, mode, source/target paths, assumptions, source commit
├── inventory.json          # machine inventory (java_inventory.py) - regenerate, never hand-edit
├── inventory.md            # human summary of inventory.json
├── APP-MODEL.md            # verified model of the source app (analyzer)
├── flows/
│   ├── JOB-<jobName>.md    # one per batch job: steps, reader/processor/writer, I/O, rules
│   └── EP-<name>.md        # one per traced endpoint / listener / scheduled task
├── requirements/
│   └── <KEY>.md            # normalized ticket (jira_to_spec.py + mapper)
├── REPLICATION-SPEC.md     # requirement x behavior traceability + gap matrix (mapper)
├── PLAN.md                 # ordered, checkable tasks (replicator)
├── decisions.md            # DEC-### records: choice, options, reason
├── open-questions.md       # OQ-### records: question, blocks which REQ, owner
├── parity/                 # fixtures, golden outputs, diff reports
└── PARITY-REPORT.md        # verification result (verifier)
```

Add `.replication/parity/**/output*` to `.gitignore` if outputs are large. Commit the rest: it is the design record for the ticket.

## IDs

| Prefix | Thing | Example |
| --- | --- | --- |
| `JOB-` | batch job | `JOB-invoiceExportJob` |
| `STEP-` | step inside a job | `STEP-invoiceExportJob.loadInvoices` |
| `EP-` | HTTP endpoint, listener, scheduled task, CLI entry | `EP-POST-/api/invoices` |
| `ENT-` | entity / table / file record layout | `ENT-INVOICE` |
| `RULE-` | business rule found in code | `RULE-007` |
| `REQ-` | requirement from ticket/user | `REQ-ABC-123-03` |
| `GAP-` | difference between current and requested | `GAP-004` |
| `DEC-` | decision | `DEC-002` |
| `OQ-` | open question | `OQ-001` |
| `T-` | plan task | `T-05` |

IDs are stable: never renumber, mark retired IDs `~~struck~~`.

## Evidence status (use on every claim about the source)

| Status | Meaning |
| --- | --- |
| `VERIFIED` | Read in source/config; cite `path:line` |
| `INFERRED` | Follows from verified facts but not directly read (say from what) |
| `CANDIDATE` | Pattern match from inventory, not yet confirmed by reading |
| `UNVERIFIED` | Stated by ticket, docs or a person; not found in source |
| `CONFLICT` | Sources disagree; keep both citations |

`inventory.json` entries start as `CANDIDATE`. The analyzer promotes them by reading the code.

## Gap statuses (REPLICATION-SPEC.md)

| Status | Meaning | Action |
| --- | --- | --- |
| `REUSE` | Existing behavior satisfies the requirement as is | replicate exactly |
| `ADAPT` | Existing behavior is close; parameter, mapping or rule differs | replicate then change |
| `NEW` | Nothing in source covers it | design new |
| `DROP` | Source behavior the target must not have | omit, note why |
| `UNCLEAR` | Cannot decide without an answer | raise `OQ-` |

## Hand-off checklist between stages

- Stage 1 done when: every job/endpoint in scope has a flow file, and `APP-MODEL.md` lists any `CANDIDATE` left unconfirmed.
- Stage 2 done when: every `REQ-` maps to at least one behavior or is `NEW`; every `UNCLEAR` has an `OQ-`.
- Stage 3 done when: every `REQ-` and every `REUSE`/`ADAPT` behavior is covered by a `T-` task with a verification step.
- Stage 5 done when: each `T-` is ticked or explicitly deferred, and parity results are recorded with commands.
