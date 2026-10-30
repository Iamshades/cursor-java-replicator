# Requirement extraction rules

## Where requirements hide in a ticket

1. Acceptance-criteria field or section (`Acceptance Criteria`, `AC`, `Definition of Done`).
2. Given/When/Then scenarios.
3. Description bullet lists and tables (field mappings are often a table).
4. Comments - later comments override earlier text; record both and the date.
5. Subtasks and linked "is blocked by" / "relates to" tickets.
6. Attachments - sample files and mapping sheets.
7. Title - often names the anchor ("Clone invoice export for credit notes").

## Splitting

One `REQ-` per independently testable statement.

> "Export credit notes daily at 03:00 to the ERP folder as pipe-delimited with a trailer count"

becomes:

| ID | Text | Type |
| --- | --- | --- |
| REQ-ABC-123-01 | Export credit notes | functional |
| REQ-ABC-123-02 | Runs daily at 03:00 (time zone: OQ) | operational |
| REQ-ABC-123-03 | Output goes to the ERP outbound folder | integration |
| REQ-ABC-123-04 | Pipe-delimited format | data-format |
| REQ-ABC-123-05 | Trailer line with record count | data-format |

## Priority words

| Word in source | Priority |
| --- | --- |
| must, shall, required, has to, needs to, acceptance criterion | MUST |
| should, expected, ideally | SHOULD |
| could, nice to have, optional, if possible, later | COULD |

Ticket acceptance criteria default to `MUST`.

## Ambiguity triggers (raise an `OQ-` unless code settles it)

- Time without time zone; "daily" without time; "end of day".
- "Same as X" where X has profile-specific behavior.
- "All records" without a filter; "new records" without a watermark definition.
- Rounding, currency, and date formats not stated for numeric/date output.
- File naming without date pattern; overwrite vs append unstated.
- "Handle errors" / "retry" without counts, skip limits or alert target.
- Volumes, SLA, run window unstated for a batch job.
- Which environments; whether the old job keeps running (parallel run) or is replaced.

## Hints for mapping

The script lists tokens under `## Hints`. Treat them as search terms against `inventory.json` and source:

| Hint kind | Search |
| --- | --- |
| `classes` | class/file names |
| `jobs` | `batch.jobs[].name`, XML job ids, `spring.batch.job.name` values |
| `endpoints` | `web.endpoints[].path` |
| `upper_identifiers` | table names, status codes and roles: entity `table`, SQL text, migrations, enums, security config |
| `files` | writer `resource`, reader `resource`, scripts |
| `properties` | config keys, `@Value` keys |
| `cron` | `@Scheduled` specs, scheduler config |

## Acceptance scenario format

```gherkin
Scenario: REQ-ABC-123-05 trailer has record count
  Given 3 approved credit notes for 2026-10-29
  When creditNoteExportJob runs with businessDate=2026-10-29
  Then the file CN_2026-10-29.txt ends with "T|3"
```

Each scenario names the test class/method that will implement it in `PLAN.md`.
