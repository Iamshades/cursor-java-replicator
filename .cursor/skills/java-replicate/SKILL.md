---
name: java-replicate
description: End-to-end pipeline that analyzes an existing Java application (Spring Batch, Spring Boot, Jakarta/JSR-352 batch, or plain Java) and replicates its functionality into a new or changed implementation driven by a Jira ticket and other user input. Use when the user asks to clone, replicate, port, re-implement, "build the same as", extend a job/service "like the existing one", or implement a Jira story against an existing Java codebase. Orchestrates java-app-analyzer, jira-requirement-mapper, java-app-replicator and java-parity-verifier through a shared .replication/ workspace.
metadata:
  version: "1.0.0"
  pipeline: "analyze -> map -> plan -> replicate -> verify"
---

# Java Replicate (orchestrator)

Replicate what an existing Java app *does*, changed only where the ticket or the user says so, with proof that everything else still behaves the same.

## Pipeline

```text
 source app ──► 1 ANALYZE ──► .replication/APP-MODEL.md
 Jira / input ─► 2 MAP ──────► .replication/REPLICATION-SPEC.md   (requirements x behaviors x gaps)
                 3 PLAN ─────► .replication/PLAN.md               (user approves here)
                 4 REPLICATE ► code + tests in the target
                 5 VERIFY ───► .replication/PARITY-REPORT.md
```

Each stage is its own skill. Cursor cannot load one skill from another, so at each stage **read that skill's `SKILL.md` from the sibling folder** (same parent directory as this file) and follow it:

| Stage | Read | Produces |
| --- | --- | --- |
| 1 Analyze | `../java-app-analyzer/SKILL.md` | `inventory.json`, `APP-MODEL.md`, `flows/*.md` |
| 2 Map | `../jira-requirement-mapper/SKILL.md` | `requirements/<KEY>.md`, `REPLICATION-SPEC.md` |
| 3 Plan + 4 Replicate | `../java-app-replicator/SKILL.md` | `PLAN.md`, code, tests |
| 5 Verify | `../java-parity-verifier/SKILL.md` | `PARITY-REPORT.md` |

All stages read and write the layout in `references/artifact-contract.md`. Read it once at the start.

## Step 0 - Frame (always)

Settle these from the request and workspace. Ask only for items that change the outcome; state the rest as assumptions in `.replication/README.md`.

1. **Source** - path(s) of the existing app. Default: current workspace root.
2. **Target** - one of the replication modes below. Default: `extend-in-place` when the ticket adds a sibling job/endpoint; `clone-new-app` when it names a new service or repo.
3. **Requirement input** - Jira key, Jira JSON export, pasted ticket text, Confluence page, or chat description. Several can combine.
4. **Target baseline** - Java and Spring versions for new code. Default: match the source app. Upgrade only if the user or ticket asks.
5. **Run authority** - may the agent run `mvn`/`gradle` builds and tests? Default: ask once before the first build.

| Mode | Meaning |
| --- | --- |
| `extend-in-place` | Add a new job / step / endpoint in the same codebase, modeled on an existing one |
| `clone-new-app` | New project that replicates the source app (or a subset), with ticket changes applied |
| `modernize-replicate` | Same behavior on a newer stack (e.g. Boot 2 -> 3, XML -> Java config, JSR-352 -> Spring Batch) |
| `analyze-only` | Stop after stage 1 or 2; produce docs and a gap matrix, no code |

## Gates

- **After stage 2**: show the gap matrix summary (counts per status) and every `OPEN-QUESTION`. Do not start code while a question blocks a `MUST` requirement.
- **After stage 3**: show `PLAN.md` and wait for approval unless the user said to proceed without asking.
- **After stage 5**: report parity result honestly. A failed or skipped check is reported as such, with the command and output.

## Fast paths

- "Just analyze X" -> stage 1 only.
- "What does ticket ABC-1 need from this app?" -> stages 1-2, `analyze-only`.
- A `.replication/` folder already exists -> resume: read `README.md` and `PLAN.md` status, re-run `inventory` only if sources changed (`git status`/`git diff --stat` since the recorded commit).

## Non-negotiables

1. Evidence before claims: every statement about the source app cites `path:line` or is labeled `UNVERIFIED`.
2. Keep three registers apart: **Current** (in source), **Requested** (ticket/user), **Proposed** (agent's design).
3. Replicate behavior, not accidents: copy business rules, contracts and data formats exactly; flag (do not silently copy) bugs, hard-coded secrets and dead code.
4. Never print secret values; keep property names and secret references only.
5. Never start the app, connect to databases, brokers, Jira write APIs, or remote environments without explicit permission.
