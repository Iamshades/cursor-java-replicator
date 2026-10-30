# Parity strategies

| Situation | Best evidence | Fallback |
| --- | --- | --- |
| Batch job writing files | Run anchor + replica on one fixture, `compare_outputs.py` | Golden file from production sample (ticket attachment), compared to replica output |
| Batch job writing tables | Run both into separate schemas / Testcontainers, export ordered CSV, compare | Row-count + checksum per column query |
| Modernize-replicate (same behavior, new stack) | Characterization tests written against the old code, run unchanged against the new | Golden files captured from old version build |
| REST endpoint | Same requests against both (MockMvc / WebTestClient / recorded HTTP), compare JSON bodies with masks | Contract test from OpenAPI + example payloads |
| Messaging listener | Same input messages into both (embedded Kafka / Testcontainers), compare produced messages and DB effects | Unit tests of handler with captured payloads |
| Scheduled task | Clock-injected unit test of the trigger + parity of the work it calls | Config review: cron, zone, lock |
| Plain Java main | Same args + input files, compare outputs and exit code | Golden output files |

## Building fixtures

- Smallest set that hits every rule branch: one record per `RULE-` branch, each boundary (zero, negative, null, max length, rounding .5), each skip/retry exception, plus one empty-input run (empty file deletion, header-only behavior).
- Anonymize: synthetic data only; never copy production personal data into the repo.
- Store under `.replication/parity/fixtures/` with a README stating what each record exercises.

## Volatile fields

Mask before comparing: run timestamps, generated ids, job execution ids, host names. Prefer making the code deterministic in tests (inject `Clock`, fixed job parameters) over masking.

## Ordering

Outputs from cursor readers without `ORDER BY`, partitioned steps, multi-threaded steps and `HashMap` iteration have no stable order. Compare by `--key` or `--ignore-order`, and record this as a NOTE: the old system's order was never guaranteed either.

## Numeric and format traps

Rounding mode (`HALF_UP` vs `HALF_EVEN`), `BigDecimal` scale (`1.0` vs `1.00`), `double` artifacts, locale decimal separators, date patterns and time zones (DST), trailing whitespace and padding in fixed-width files, line endings (`\n` vs `\r\n`), file encoding and BOM. `compare_outputs.py` reports the first differing characters to make these visible; `--strip` trims cell whitespace if the target system ignores it (state that in the report).
