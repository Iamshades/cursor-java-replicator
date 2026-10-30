---
name: jira-requirement-mapper
description: Turn a Jira ticket (key, JSON export, or pasted text) plus any other user input - Confluence pages, chat instructions, sample files, emails - into numbered requirements, then map each one to the existing Java application's analyzed behavior to produce a replication spec with a REUSE / ADAPT / NEW / DROP / UNCLEAR gap matrix and open questions. Use when the user gives a Jira key or story and wants to know what to build, what can be copied from an existing job or service, or what is missing; stage 2 of java-replicate.
metadata:
  version: "1.0.0"
  stage: "2-map"
---

# Jira Requirement Mapper

Inputs: ticket + user input, and `.replication/APP-MODEL.md` from `java-app-analyzer`. If `APP-MODEL.md` is missing, run stage 1 first (read `../java-app-analyzer/SKILL.md`), at least for the flows the ticket names.

Outputs: `.replication/requirements/<KEY>.md`, `.replication/REPLICATION-SPEC.md`, `.replication/open-questions.md`. Layout and IDs: `../java-replicate/references/artifact-contract.md`.

## 1. Get the ticket (first source that works)

1. **Atlassian MCP connected in Cursor** - use its get-issue tool for the key (include comments, links, subtasks, and the parent epic). Save the raw JSON to `.replication/requirements/<KEY>.raw.json`, then normalize with the script below using `--json`.
2. **REST with the user's own token** - only if the user has set env vars (`JIRA_BASE_URL` plus `JIRA_EMAIL` + `JIRA_API_TOKEN` for Cloud, or `JIRA_PAT` for Server/Data Center). Never ask the user to paste a token into chat.
   ```bash
   python3 <this-skill-dir>/scripts/jira_to_spec.py --key ABC-123 --out .replication/requirements
   ```
3. **Export or paste** - `--json issue.json` (REST or MCP output) or `--text ticket.md` / `--text -` for pasted text.

The script is read-only (HTTP GET only), stdlib-only, converts Atlassian Document Format and wiki markup to Markdown, and extracts: summary, type, status, labels, components, fix versions, parent/epic, subtasks, links, attachments (names only), comments, acceptance criteria, Given/When/Then scenarios, and **hints** (class names, job names, endpoints, tables, file patterns, property keys, cron expressions) that seed mapping. Setup details: `references/jira-sources.md`.

Never write to Jira (comment, transition, edit) unless the user explicitly asks for that specific action.

## 2. Add the other inputs

Append each extra source to `requirements/<KEY>.md` under `## Additional input`, labeled by origin (`chat`, `confluence:<title>`, `email`, `file:<name>`). Linked tickets, epics and subtasks are context; pull them in only if they carry acceptance criteria for this work.

Sample input/output files attached to the ticket are the best parity evidence. Download them only with the user's go-ahead, into `.replication/parity/fixtures/`.

## 3. Normalize requirements

Read `references/requirement-extraction.md`. Produce one `REQ-<KEY>-NN` per testable statement, each with: text, type (`functional`, `data-format`, `integration`, `non-functional`, `operational`), priority (`MUST`/`SHOULD`/`COULD`), source, and acceptance check. Split compound sentences. Turn vague words ("fast", "same as before", "handle errors") into an `OQ-` unless the source code defines them.

## 4. Find the anchor

Most replication tickets say "like X": "same as the invoice export but for credit notes", "replicate job ABC for region EU". Name the anchor flow(s) (`JOB-`/`EP-` IDs from `APP-MODEL.md`). If none is stated, propose candidates by matching hints against the inventory (`.replication/inventory.json`) and ask the user to confirm before mapping.

## 5. Map in both directions

**Forward** - for each `REQ-`, find the behaviors that satisfy it (`RULE-`, `STEP-`, `EP-`, config keys) and set a gap status: `REUSE`, `ADAPT` (state the exact delta), `NEW`, `DROP`, or `UNCLEAR` (+ `OQ-`).

**Backward (the step people skip)** - for every rule, step, side effect, config key and output field of the anchor flow, decide whether the target keeps it. Unmentioned behavior of the anchor is an *implicit requirement*: mark it `REUSE` with source `implicit:anchor`, unless the ticket contradicts it. This is what makes a replica behave like the original.

## 6. Write REPLICATION-SPEC.md

Use `assets/templates/replication-spec.md`. It must contain: scope and mode, anchor(s), requirement table, behavior coverage matrix, precise delta list (old value -> new value, with `path:line` of the old), data contracts for inputs/outputs, non-functional and operational needs (schedule, volumes, SLAs, alerting), assumptions, open questions, and acceptance scenarios mapped to the tests that will prove them.

## 7. Gate

Report: counts per gap status, every `OQ-` that blocks a `MUST`, and assumptions taken. Stop for answers if any blocking `OQ-` exists, unless the user said to proceed with stated assumptions.

## Quality bar

- Every `REQ-` traces to a source quote; every behavior cites `path:line`.
- No `ADAPT` without an exact delta. "Change the filter" is not a delta; "`status = 'APPROVED'` -> `status IN ('APPROVED','REISSUED')` at `InvoiceExportJobConfig.java:88`" is.
- Ticket statements that contradict code are `CONFLICT`, raised as questions, never silently resolved either way.
