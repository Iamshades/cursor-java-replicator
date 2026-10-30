# cursor-java-replicator

Cursor IDE Agent Skills that **analyze existing Java applications** (Spring Batch, Spring Boot, Jakarta/JSR-352 batch, plain Java and Quartz) and **replicate their functionality** into new or changed code, driven by a **Jira ticket** and other user input. Every claim is backed by evidence, and the result is checked for parity.

```text
 existing app ──► 1 ANALYZE ──────► APP-MODEL.md + one flow file per job/endpoint
 Jira + input ──► 2 MAP ──────────► REPLICATION-SPEC.md  (REUSE / ADAPT / NEW / DROP / UNCLEAR)
                  3 PLAN ─────────► PLAN.md               (you approve)
                  4 REPLICATE ────► code + tests in your conventions
                  5 VERIFY ───────► PARITY-REPORT.md      (static, rule tests, output diff, contracts)
```

Five small skills share one artifact folder (`.replication/`), so they can run together through `/java-replicate`, one at a time, or across several chats.

## What's inside

| Skill | Slash command | Does | Bundled tools |
| --- | --- | --- | --- |
| `java-replicate` | `/java-replicate` | Runs the pipeline: framing, gates, resume | artifact contract |
| `java-app-analyzer` | `/java-app-analyzer` | Inventories and models the source app; one flow file per job/endpoint, with each rule cited by `path:line` | `java_inventory.py` (job graphs, steps, readers/writers, endpoints, SQL, config with secrets redacted, Mermaid) |
| `jira-requirement-mapper` | `/jira-requirement-mapper` | Ticket + other input -> numbered requirements -> two-way mapping against the model -> gap matrix and questions | `jira_to_spec.py` (REST GET or MCP JSON or pasted text; ADF and wiki markup to Markdown; AC, Given/When/Then, hints) |
| `java-app-replicator` | `/java-app-replicator` | Plan and implement the replica (extend in place, clone a new app, or modernize) | Spring Batch 4/5/6 and Boot recipes, version matrix |
| `java-parity-verifier` | `/java-parity-verifier` | Proves the replica matches the source apart from the approved deltas | `compare_outputs.py` (delimited, fixed-width, JSON, text; key matching, expected-diff columns, masks, tolerance) |

Rules (`.cursor/rules/*.mdc`, attached by glob, never always-on):

- `replication-guardrails.mdc` (`.replication/**`): evidence, secrets, ask before risky actions.
- `java-code-conventions.mdc` (`**/*.java`): the existing codebase's conventions win.
- `spring-batch-conventions.mdc` (job/step/reader/writer files): version-correct Batch APIs and batch pitfalls.

## Install

Requirements: Cursor with Agent Skills, and Python 3.8+ for the helper scripts (stdlib only, no `pip install`).

```bash
git clone <this-repo> cursor-java-replicator
```

```bash
./cursor-java-replicator/install.sh --project /path/to/your-java-app
```

Or install for every project (skills only; Cursor rules are per project):

```bash
./cursor-java-replicator/install.sh --global
```

Options: `--no-rules`, `--link` (symlink while developing skills), `--force`, `--dry-run`.

Cursor also discovers skills in `.agents/skills/` and `.claude/skills/`. To use the same skills in Claude Code, copy `.cursor/skills/*` to `.claude/skills/`.

### Jira access (pick one)

1. **Atlassian Rovo MCP server** (OAuth, no tokens in files): copy `mcp.json.example` to `.cursor/mcp.json` or `~/.cursor/mcp.json`, or install the Atlassian plugin from the Cursor Marketplace. Then click **Connect** in Cursor Settings -> MCP.
2. **REST**: export `JIRA_BASE_URL` with `JIRA_EMAIL` + `JIRA_API_TOKEN` (Cloud), or with `JIRA_PAT` (Server/DC). The script only sends GET requests.
3. **Offline**: paste the ticket into chat, or save it as a file. The script parses text, Jira JSON exports and MCP output.

## Use

In Cursor Agent chat:

```text
/java-replicate FIN-482 - build creditNoteExportJob like invoiceExportJob, extend in place
```

```text
/java-app-analyzer explain every batch job in this repo and how each is triggered
```

```text
/jira-requirement-mapper FIN-490 against the current app, analyze-only
```

```text
/java-replicate modernize the JSR-352 payrollJob to Spring Boot 3 / Spring Batch 5 with identical output
```

```text
/java-parity-verifier compare target/old/INV_2026-10-29.txt with target/new/CN_2026-10-29.txt
```

The agent stops for approval after the gap matrix and again after the plan. It asks before the first build, before any download, and before touching databases or Jira.

You can also run the scripts directly:

```bash
python3 .cursor/skills/java-app-analyzer/scripts/java_inventory.py . --out .replication
```

```bash
python3 .cursor/skills/jira-requirement-mapper/scripts/jira_to_spec.py --json FIN-482.json --out .replication/requirements
```

```bash
python3 .cursor/skills/java-parity-verifier/scripts/compare_outputs.py old.txt new.txt --delimiter '|' --header-lines 1 --trailer-lines 0,1 --key invoiceId --columns invoiceId,customerCode,amountCents,currency,issuedOn --expect-diff amountCents,trailer
```

## The `.replication/` workspace

```text
.replication/
├── README.md              scope, mode, assumptions, source commit
├── inventory.json|md      scanner output (CANDIDATE items)
├── APP-MODEL.md           verified model of the source
├── flows/JOB-*.md EP-*.md one per job / entry point: steps, I/O layouts, RULE-### with path:line
├── requirements/<KEY>.md  normalized ticket + additional input
├── REPLICATION-SPEC.md    requirements x behaviors, exact deltas, contracts, open questions
├── PLAN.md                ordered tasks T-## with verification
├── decisions.md           DEC-### records
├── open-questions.md      OQ-### records
├── parity/                fixtures, outputs, diff reports
└── PARITY-REPORT.md       verdict with commands and NOT RUN items
```

Commit it with the change; it is the design record for the ticket. The full contract (IDs, evidence statuses, gap statuses, hand-off checks) is in [artifact-contract.md](.cursor/skills/java-replicate/references/artifact-contract.md).

## Design choices

These come from reviewing public skill collections: [jabrena/cursor-rules-java](https://github.com/jabrena/cursor-rules-java), [github/awesome-copilot](https://github.com/github/awesome-copilot) `java-springboot`, [spencerpauly/awesome-cursor-skills](https://github.com/spencerpauly/awesome-cursor-skills), and evidence-driven Spring repository analysis skills. None of them covers Spring Batch analysis or ticket-driven replication. This repo adds both and keeps the parts that worked:

- **Small skills with one job each, plus an orchestrator.** Cursor cannot load one skill from another, so the orchestrator tells the agent which sibling `SKILL.md` to read at each stage.
- **Progressive disclosure.** Each `SKILL.md` is short (under ~110 lines). Version-specific detail sits in `references/` and is read only when the detected app kind or version needs it.
- **Scripts for deterministic work.** The scripts handle inventory, ticket parsing and output diffs. That saves tokens and gives the same result on every run. The model's judgment goes to reading code and mapping behavior.
- **Evidence statuses and three registers** (Current / Requested / Proposed). These stop a guess from turning into a "fact".
- **Backward mapping.** Every behavior of the anchor job is in the matrix even when the ticket does not mention it. Missing implicit behavior is the main reason replicas drift from the original.
- **Parity with expected deltas.** Diffs in approved columns are reported and do not fail the run. Any other diff fails.
- **No always-on rules.** Rules attach by glob, so they cost no context in unrelated work.
- **Safe by default.** Scripts only read files. The agent asks before builds, downloads, database access or Jira writes. Secrets are redacted in all output.

## Develop

```bash
python3 tools/validate_skills.py
```

```bash
python3 -m unittest discover -s tests -v
```

The validator checks frontmatter (name matches folder, lowercase-hyphen, description ≤ 1024 chars), body size, and that every referenced file exists. CI runs both on push. `examples/` holds three sample source apps (legacy Boot 2 Spring Batch, JSR-352, plain Java), two sample tickets and parity files. See [examples/README.md](examples/README.md).

## Limits

- `java_inventory.py` uses pattern matching, not a compiler. Its output is a list of candidates for the agent to confirm by reading the code. It does not resolve generics, inheritance chains or beans created conditionally.
- Kotlin files are scanned with the Java patterns. This is good enough for annotations, weak for Kotlin DSL configuration.
- Spring Batch 6 recipes are deliberately brief. Check the official 6.x migration guide when you target it.

## License

MIT
