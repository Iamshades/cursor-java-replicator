---
name: java-app-replicator
description: Plan and implement a replica of existing Java functionality - a new Spring Batch job, step, Spring Boot endpoint, listener, scheduled task, or a whole new app - from an approved replication spec, keeping the source app's business rules, data contracts and operational behavior and applying only the requested deltas. Covers extend-in-place, clone-new-app and modernize-replicate (Boot 2 to 3, XML or JSR-352 to Java config, plain Java to Spring Batch). Use after the mapping stage of java-replicate, or when asked to "build the same job/service as X but ...".
metadata:
  version: "1.0.0"
  stage: "3-plan,4-replicate"
---

# Java App Replicator

Inputs: `.replication/REPLICATION-SPEC.md` (approved), `APP-MODEL.md`, flow files. Outputs: `.replication/PLAN.md`, code, tests, `decisions.md`. Contract: `../java-replicate/references/artifact-contract.md`.

If the spec is missing or has a blocking `OQ-`, stop and run or finish stage 2 (`../jira-requirement-mapper/SKILL.md`).

## 1. Choose the target shape

| Mode | Default shape |
| --- | --- |
| `extend-in-place` | New config class / package next to the anchor, same conventions, shared components reused (not copied) when their behavior is identical |
| `clone-new-app` | New Maven/Gradle module or repo with the same baseline as the source unless the spec sets one; copy only what the coverage matrix keeps |
| `modernize-replicate` | Target baseline from the spec; translate APIs with `references/version-matrix.md`; behavior frozen by characterization tests first |

Read the source's conventions before writing anything: package layout, naming (`*JobConfig`, `*Step`, `*Reader`), config style (Java vs XML), DI style, logging, exception types, test style. New code must look like it was written by the same team. Record any deliberate departure as a `DEC-`.

## 2. Write PLAN.md

Use `assets/templates/plan.md`. Order tasks so each can be built and tested alone:

1. **Safety net** - characterization tests on the anchor if none cover the behavior being replicated or shared code you will touch (`extend-in-place`, `modernize-replicate`).
2. **Contracts** - DTOs/records, file layouts, SQL, API schemas.
3. **Read side** - reader / repository / client.
4. **Rules** - processor or service logic: one test per `RULE-` kept, one per `ADAPT` delta, one per `NEW` requirement.
5. **Write side** - writer, header/footer/trailer, file naming, upsert semantics.
6. **Wiring** - job/step flow and transitions, fault tolerance, restart, listeners, scopes.
7. **Triggers** - schedule, REST/CLI launch, launch properties, external scheduler scripts.
8. **Config** - properties per profile, no secrets in files (env / vault refs).
9. **Ops** - logging, metrics, alerts, runbook notes.
10. **Verification** - parity tasks for `../java-parity-verifier/SKILL.md`.

Each task: `T-##`, files touched, `REQ-`/`RULE-`/`D-` covered, how it is verified. Show the plan and wait for approval unless told to proceed.

## 3. Implement

Work task by task. After each, run its tests if build runs are approved, then tick it in `PLAN.md`.

- Copy rules **exactly** as the flow file records them: same comparison operators, rounding mode, scale, null handling, string padding, date pattern, time zone, charset, line separator, ordering. Re-read the cited `path:line` while writing, do not rely on the summary alone.
- Apply each `ADAPT` delta exactly as `D-##` states; nothing else changes.
- Bugs and smells flagged as `NOTE` in the flow: replicate unless the spec says fix (parity first); add a `TODO(<KEY>)` and a `DEC-` either way.
- Shared code in `extend-in-place`: prefer parameterizing over forking. If a shared class must change, the anchor's tests must still pass unchanged.
- No new dependencies, frameworks or patterns unless a `DEC-` justifies it and the user approved.
- Secrets: properties reference env vars or the existing secret mechanism; never literal values.
- Do not modify, disable or loosen existing tests to make the build pass.

Version-specific code recipes: `references/spring-batch-recipes.md` (Batch 4 and 5 APIs, readers/writers, trailer, fault tolerance, partitioning, tests) and `references/boot-recipes.md` (REST trigger, scheduler, listeners, config). Check the target version first with `references/version-matrix.md`.

## 4. Build and test

Ask once before the first build. Then use the project's wrapper (`./mvnw` or `./gradlew`) if present:

```bash
./mvnw -q -o test            # offline first; drop -o only if dependencies are missing and the user allows downloads
./gradlew test --offline
```

Report failures with the decisive error lines. Fix the code, not the test, unless the test encodes a requirement that the spec changed (then cite the `REQ-`).

## 5. Hand off

When all build tasks are ticked, run stage 5: read `../java-parity-verifier/SKILL.md`. Update `.replication/README.md` with status, and list deferred tasks with reasons.
