# AGENTS.md

Guidance for AI agents and contributors editing this repository (not for projects that install the skills).

## Layout

- `.cursor/skills/<name>/SKILL.md` - one skill per folder; `name` in frontmatter must equal the folder name.
- `.cursor/skills/<name>/{references,scripts,assets}/` - loaded on demand; keep `SKILL.md` short and move detail here.
- `.cursor/rules/*.mdc` - glob-scoped rules; do not make any rule `alwaysApply: true`.
- `tools/validate_skills.py` - lint; `tests/` - unittest suite for the scripts; `examples/` - sample inputs used by tests.

## Contracts that must stay in sync

- `.cursor/skills/java-replicate/references/artifact-contract.md` defines `.replication/` paths, ID prefixes and statuses. Any skill or template that names a file, ID or status must match it.
- Skill names are referenced across skills as `../<name>/SKILL.md` and in `install.sh` (`SKILLS=` list) and `README.md`.

## Script rules

- Python 3.8+ stdlib only; no network except `jira_to_spec.py --key` (HTTP GET with env-var credentials).
- Scripts read files and never execute project code or builds.
- Redact secret-looking values in any output.
- Add or update a test in `tests/test_scripts.py` with every behavior change, plus a fixture under `tests/fixtures/` or `examples/` when needed.

## Before committing

```bash
python3 tools/validate_skills.py && python3 -m unittest discover -s tests
```
