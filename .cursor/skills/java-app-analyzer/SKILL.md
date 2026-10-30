---
name: java-app-analyzer
description: Analyze an existing Java codebase and build an evidence-backed model of what it does - Spring Batch jobs (steps, readers, processors, writers, chunking, skip/retry, partitioning, listeners), Spring Boot services (endpoints, schedulers, messaging listeners, persistence, external calls, configuration), Jakarta/JSR-352 batch XML jobs, and plain Java main-class or Quartz apps. Use when asked to understand, document, reverse-engineer, map, or explain a Java/Spring application or batch job, or as stage 1 of java-replicate. Read-only; never runs the app.
metadata:
  version: "1.0.0"
  stage: "1-analyze"
---

# Java App Analyzer

Turn source code into `.replication/APP-MODEL.md` plus one flow file per job or entry point. Facts come from files you read, not from memory of how such apps usually look.

Contract for outputs, IDs and evidence statuses: `../java-replicate/references/artifact-contract.md`.

## 1. Inventory (automatic, read-only)

Run the bundled scanner. It uses Python 3 stdlib only, reads files, runs no build, and redacts secret-looking values.

```bash
python3 <this-skill-dir>/scripts/java_inventory.py <source-root> --out .replication
```

`<this-skill-dir>` is the folder holding this file, usually `.cursor/skills/java-app-analyzer` or `~/.cursor/skills/java-app-analyzer`. If Python is unavailable, do the same sweep with search tools using the patterns in `references/detection-patterns.md`.

It writes `inventory.json` and `inventory.md` with: build tool and versions, detected app kinds, modules, main classes, batch jobs and step graphs (Java DSL and XML), JSR-352 job XML, readers/processors/writers/tasklets, endpoints, schedulers, messaging listeners, entities, repositories, SQL and migrations, external HTTP clients, config keys, and tests. Every item has `file:line` and status `CANDIDATE`.

## 2. Classify and load only what applies

Read `inventory.md` `kinds`. Then load the matching reference, not all of them:

| Kind detected | Read |
| --- | --- |
| `spring-batch` | `references/spring-batch.md` |
| `jakarta-batch` (JSR-352 XML in `META-INF/batch-jobs`) | `references/jakarta-batch.md` |
| `spring-boot-web`, `spring-boot-messaging`, `spring-boot-scheduler` | `references/spring-boot.md` |
| `plain-java`, `quartz` | `references/plain-java.md` |

Mixed apps are common (a Boot app with jobs and a REST trigger). Load each matching file.

## 3. Confirm by reading (promote CANDIDATE -> VERIFIED)

Scope: everything the ticket touches plus its direct dependencies. If no ticket yet, all jobs and entry points; if more than ~15, do the top level for all and deep traces only for the ones the user names.

For each job or entry point, trace end to end and fill a flow file from `assets/templates/flow-job.md` or `assets/templates/flow-entrypoint.md`:

1. Trigger: scheduler, REST call, CLI args, `spring.batch.job.name`, external scheduler (Control-M, Autosys, cron) found in scripts.
2. Parameters: job parameters, identifying vs non-identifying, defaults, `@Value("#{jobParameters[...]}")` late binding.
3. Input: source type, query or file layout (columns, delimiter, fixed widths, header/footer, encoding), paging/cursor, sort.
4. Processing: every rule in the processor/service as a `RULE-###` with the condition, the output, and `path:line`. Include filters (return `null`), validations, lookups, rounding, date/time zone handling.
5. Output: target, format, write mode (insert/upsert/append/overwrite), file naming, headers/footers/trailers with counts or totals.
6. Control: chunk size, commit interval, transaction boundaries, skip/retry/no-rollback exceptions and limits, restartability, `saveState`, partitioning/multi-threading, listeners and what they do.
7. Side effects: emails, events, audit rows, file moves/archives, calls to other services.
8. Configuration: every property used, per profile, with default. Never copy secret values.
9. Tests: which tests cover this flow and what they assert.

Write findings that matter for replication into the flow as `NOTE` lines: bugs, dead branches, hard-coded environment values, non-determinism (unordered queries, `HashMap` iteration, `now()`), and locale/time-zone dependence. These decide whether parity is achievable.

## 4. Write APP-MODEL.md

Use `assets/templates/app-model.md`. Keep it the index: one table row per job/endpoint linking to its flow file, plus stack, modules, data stores, integrations, config profiles, test inventory, and a `Remaining CANDIDATE` list. Add Mermaid diagrams only for edges you verified.

## 5. Done when

- Every in-scope job/entry point has a flow file with cited rules.
- Nothing is stated as fact without `path:line` or a status label.
- `APP-MODEL.md` lists what was not analyzed and why.

## Do not

- Run `mvn`/`gradle`, start the app, or connect to a database to "check" behavior. If runtime evidence would settle a question, ask, or record an `OQ-`.
- Treat inventory regex hits as proof. A class named `*Reader` is not necessarily an `ItemReader` bean used by a step.
- Summarize a processor as "transforms records". Each rule is listed or the flow is incomplete.
