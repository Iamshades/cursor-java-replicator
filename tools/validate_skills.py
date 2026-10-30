#!/usr/bin/env python3
"""validate_skills.py - lint the Cursor skills and rules in this repo.

Checks: SKILL.md frontmatter (name format, name == folder, description length), body size,
referenced files exist (references/, assets/, scripts/, ../<skill>/...), rule frontmatter,
and that bundled Python scripts compile. Exit 1 on any error.
"""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".cursor" / "skills"
RULES = ROOT / ".cursor" / "rules"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REF_RE = re.compile(r"`((?:\.\./[\w-]+/)?(?:references|assets|scripts)/[\w./-]+|\.\./[\w-]+/SKILL\.md)`")
MAX_DESC, MAX_LINES = 1024, 500


def frontmatter(text: str):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([\w-]+):\s*(.*)$", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip().strip('"')
    return fm, text[m.end():]


def main() -> int:
    errors, warnings = [], []
    skill_dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    for d in skill_dirs:
        f = d / "SKILL.md"
        if not f.exists():
            errors.append(f"{d.name}: missing SKILL.md")
            continue
        text = f.read_text(encoding="utf-8")
        fm, body = frontmatter(text)
        if fm is None:
            errors.append(f"{d.name}: no YAML frontmatter")
            continue
        name, desc = fm.get("name", ""), fm.get("description", "")
        if not NAME_RE.match(name):
            errors.append(f"{d.name}: name '{name}' must be lowercase letters, digits and hyphens")
        if name != d.name:
            errors.append(f"{d.name}: name '{name}' must equal folder name")
        if not desc:
            errors.append(f"{d.name}: description missing")
        elif len(desc) > MAX_DESC:
            errors.append(f"{d.name}: description {len(desc)} chars > {MAX_DESC}")
        n = body.count("\n")
        if n > MAX_LINES:
            warnings.append(f"{d.name}: SKILL.md body {n} lines > {MAX_LINES}; move detail to references/")
        for doc in sorted(d.rglob("*.md")):
            for ref in REF_RE.findall(doc.read_text(encoding="utf-8")):
                if "<" in ref:
                    continue
                base = doc.parent if doc != f else d
                candidates = [(base / ref).resolve(), (d / ref).resolve()]
                if not any(c.exists() for c in candidates):
                    errors.append(f"{doc.relative_to(ROOT)}: broken reference `{ref}`")
        for py in d.rglob("*.py"):
            try:
                py_compile.compile(str(py), doraise=True, cfile=None)
            except py_compile.PyCompileError as e:
                errors.append(f"{py.relative_to(ROOT)}: does not compile: {e.msg}")
    for r in sorted(RULES.glob("*.mdc")):
        fm, _ = frontmatter(r.read_text(encoding="utf-8"))
        if fm is None or not fm.get("description"):
            errors.append(f"{r.name}: rule needs frontmatter with description")
        elif "alwaysApply" not in fm:
            warnings.append(f"{r.name}: alwaysApply not set")
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(skill_dirs)} skills, {len(list(RULES.glob('*.mdc')))} rules: "
          f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
