#!/usr/bin/env python3
"""compare_outputs.py - compare batch outputs of an anchor job and its replica.

Usage:
    python3 compare_outputs.py OLD NEW [options]          # files or directories

Formats: delimited (--delimiter), fixed (--widths), json (array or object), jsonl, text, auto.
Key options:
    --columns a,b,c         column names (else --columns-from-header, else c1..cN)
    --header-lines N[,M]    lines compared separately as header (old[,new]; default 0)
    --trailer-lines N[,M]   lines compared separately as trailer (old[,new]; default 0)
    --key a[,b]             match rows by key instead of position
    --ignore-order          compare rows as multisets
    --ignore-cols a,b       drop columns before comparing
    --expect-diff a,b       columns (or 'header'/'trailer') allowed to differ (approved deltas)
    --mask REGEX            replace matches with <masked> in every line (repeatable)
    --strip                 trim whitespace in every cell
    --tolerance X           numeric cells equal when |old-new| <= X
    --ignore-format         do not fail on line-ending / BOM / final-newline differences
    --rename 'RE=REPL'      directory mode: map old file names to new names
    --report FILE.md        write a Markdown report
Exit: 0 = parity (only expected diffs), 1 = unexpected differences, 2 = usage/input error.
Python 3.8+ stdlib only. Reads files only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

VERSION = "1.0.0"


def per_side(value: str, side: int) -> int:
    parts = [int(x) for x in str(value).split(",")]
    return parts[min(side, len(parts) - 1)]


class Side:
    def __init__(self, path: Path, a, side: int = 0):
        self.header_lines = per_side(a.header_lines, side)
        self.trailer_lines = per_side(a.trailer_lines, side)
        raw = path.read_bytes()
        self.path = path
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode(a.encoding, errors="replace")
        if self.bom:
            text = text.lstrip("\ufeff")
        self.crlf = "\r\n" in text
        self.final_newline = text.endswith("\n")
        lines = text.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        for m in a.mask:
            lines = [re.sub(m, "<masked>", ln) for ln in lines]
        self.header = lines[: self.header_lines]
        body_end = len(lines) - self.trailer_lines if self.trailer_lines else len(lines)
        self.trailer = lines[body_end:] if self.trailer_lines else []
        self.body = lines[self.header_lines: body_end]
        self.columns, self.rows = parse(self.body, self.header, a, path)


def detect_format(path: Path, a) -> str:
    if a.format != "auto":
        return a.format
    suf = path.suffix.lower()
    if suf == ".json":
        return "json"
    if suf in (".jsonl", ".ndjson"):
        return "jsonl"
    if a.widths:
        return "fixed"
    if a.delimiter or suf in (".csv", ".psv", ".tsv"):
        return "delimited"
    return "text"


def flatten(obj, prefix=""):
    out = OrderedDict()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        out[prefix[:-1]] = json.dumps(obj, sort_keys=True)
    else:
        out[prefix[:-1]] = "" if obj is None else str(obj)
    return out


def parse(body, header, a, path):
    fmt = detect_format(path, a)
    if fmt in ("json", "jsonl"):
        if fmt == "json":
            data = json.loads("\n".join(body) or "[]")
            data = data if isinstance(data, list) else [data]
        else:
            data = [json.loads(ln) for ln in body if ln.strip()]
        rows = [flatten(d) for d in data]
        cols = list(OrderedDict.fromkeys(k for r in rows for k in r))
        return cols, [[r.get(c, "") for c in cols] for r in rows]
    if fmt == "delimited":
        delim = a.delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")
        reader = csv.reader(io.StringIO("\n".join(body)), delimiter=delim, quotechar=a.quotechar or '"')
        rows = [r for r in reader]
    elif fmt == "fixed":
        widths = [int(w) for w in a.widths.split(",")]
        rows = []
        for ln in body:
            pos, r = 0, []
            for w in widths:
                r.append(ln[pos:pos + w])
                pos += w
            if pos < len(ln):
                r.append(ln[pos:])
            rows.append(r)
    else:
        rows = [[ln] for ln in body]
    if a.strip:
        rows = [[c.strip() for c in r] for r in rows]
    if a.columns:
        cols = a.columns.split(",")
    elif a.columns_from_header and header:
        delim = a.delimiter or ","
        cols = next(csv.reader([header[-1]], delimiter=delim))
    elif fmt == "text":
        cols = ["line"]
    else:
        width = max((len(r) for r in rows), default=0)
        cols = [f"c{i + 1}" for i in range(width)]
    return cols, rows


def cells_equal(x: str, y: str, tol: float) -> bool:
    if x == y:
        return True
    if tol is not None:
        try:
            return abs(float(x) - float(y)) <= tol
        except ValueError:
            return False
    return False


def first_diff(x: str, y: str) -> str:
    i = next((k for k in range(min(len(x), len(y))) if x[k] != y[k]), min(len(x), len(y)))
    return f"at char {i}: {x[i:i + 12]!r} vs {y[i:i + 12]!r}"


def compare(old: Side, new: Side, a) -> dict:
    res = {"old": str(old.path), "new": str(new.path), "rows_old": len(old.rows), "rows_new": len(new.rows),
           "format": [], "header": None, "trailer": None, "column_diffs": Counter(), "samples": [],
           "missing": [], "extra": [], "duplicate_keys": [], "unexpected": 0, "expected": 0}
    expect = set(filter(None, (a.expect_diff or "").split(",")))
    ignore = set(filter(None, (a.ignore_cols or "").split(",")))
    for label, x, y in (("BOM", old.bom, new.bom), ("CRLF line endings", old.crlf, new.crlf),
                        ("final newline", old.final_newline, new.final_newline)):
        if x != y:
            res["format"].append(f"{label}: old={x} new={y}")
    if res["format"] and not a.ignore_format:
        res["unexpected"] += len(res["format"])
    for part in ("header", "trailer"):
        o, n = getattr(old, part), getattr(new, part)
        if o != n:
            res[part] = {"old": o, "new": n}
            res["expected" if part in expect else "unexpected"] += 1
    cols = old.columns if len(old.columns) >= len(new.columns) else new.columns
    keep = [i for i, c in enumerate(cols) if c not in ignore]
    def proj(r):
        return tuple(r[i] if i < len(r) else "<absent>" for i in keep)
    names = [cols[i] for i in keep]
    max_s = a.max_samples

    def diff_rows(ro, rn, ident):
        for j, name in enumerate(names):
            x, y = ro[j], rn[j]
            if not cells_equal(x, y, a.tolerance):
                res["column_diffs"][name] += 1
                kind = "expected" if name in expect else "unexpected"
                res[kind] += 1
                if sum(1 for s in res["samples"] if s["kind"] == kind) < max_s:
                    res["samples"].append({"row": ident, "column": name, "old": x, "new": y,
                                           "kind": kind, "where": first_diff(x, y)})

    if a.key:
        kcols = a.key.split(",")
        missing_cols = [k for k in kcols if k not in names]
        if missing_cols:
            raise SystemExit(f"error: key column(s) not found: {missing_cols}; columns are {names}")
        kidx = [names.index(k) for k in kcols]
        def index(rows):
            m, dup = OrderedDict(), []
            for r in rows:
                p = proj(r)
                k = tuple(p[i] for i in kidx)
                if k in m:
                    dup.append(k)
                m[k] = p
            return m, dup
        mo, do = index(old.rows)
        mn, dn = index(new.rows)
        res["duplicate_keys"] = [list(k) for k in (do + dn)][:max_s]
        for k, ro in mo.items():
            if k in mn:
                diff_rows(ro, mn[k], "key=" + "|".join(k))
            else:
                res["missing"].append("|".join(ro))
        res["extra"] = ["|".join(rn) for k, rn in mn.items() if k not in mo]
    elif a.ignore_order:
        co, cn = Counter(proj(r) for r in old.rows), Counter(proj(r) for r in new.rows)
        res["missing"] = ["|".join(r) for r in (co - cn).elements()]
        res["extra"] = ["|".join(r) for r in (cn - co).elements()]
    else:
        for i, (ro, rn) in enumerate(zip(old.rows, new.rows), start=old.header_lines + 1):
            diff_rows(proj(ro), proj(rn), f"line {i}")
        res["missing"] = ["|".join(proj(r)) for r in old.rows[len(new.rows):]]
        res["extra"] = ["|".join(proj(r)) for r in new.rows[len(old.rows):]]
    res["unexpected"] += len(res["missing"]) + len(res["extra"]) + len(res["duplicate_keys"])
    res["columns"] = names
    return res


def pair_files(old: Path, new: Path, a):
    if old.is_file() and new.is_file():
        return [(old, new)], [], []
    if not (old.is_dir() and new.is_dir()):
        raise SystemExit("error: OLD and NEW must both be files or both be directories")
    rx, repl = (a.rename.split("=", 1) if a.rename else (None, None))
    pairs, only_old = [], []
    new_files = {p.relative_to(new).as_posix(): p for p in new.rglob("*") if p.is_file()}
    used = set()
    for p in sorted(x for x in old.rglob("*") if x.is_file()):
        rel = p.relative_to(old).as_posix()
        target = re.sub(rx, repl, rel) if rx else rel
        if target in new_files:
            pairs.append((p, new_files[target]))
            used.add(target)
        else:
            only_old.append(rel)
    only_new = sorted(k for k in new_files if k not in used)
    return pairs, only_old, only_new


def md_cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def report_md(results, only_old, only_new, a, ok) -> str:
    o = [f"# Output parity report (compare_outputs {VERSION})", "",
         f"Verdict: **{'PASS' if ok else 'FAIL'}**" + (" (only expected differences)" if ok and any(r['expected'] for r in results) else ""),
         "", f"Options: `{' '.join(sys.argv[1:])}`", ""]
    if only_old or only_new:
        o += ["## Unpaired files", "", f"- only in OLD: {only_old or 'none'}", f"- only in NEW: {only_new or 'none'}", ""]
    for r in results:
        o += [f"## `{r['old']}` vs `{r['new']}`", "",
              f"| Rows old | Rows new | Unexpected diffs | Expected diffs | Missing rows | Extra rows |",
              "| --- | --- | --- | --- | --- | --- |",
              f"| {r['rows_old']} | {r['rows_new']} | {r['unexpected']} | {r['expected']} | {len(r['missing'])} | {len(r['extra'])} |", ""]
        if r["format"]:
            o += ["Format differences: " + "; ".join(r["format"]), ""]
        for part in ("header", "trailer"):
            if r[part]:
                o += [f"{part.title()} differs: old `{md_cell(r[part]['old'])}` new `{md_cell(r[part]['new'])}`", ""]
        if r["column_diffs"]:
            o += ["| Column | Rows differing |", "| --- | --- |"] + [f"| {c} | {n} |" for c, n in r["column_diffs"].most_common()] + [""]
        if r["samples"]:
            o += ["| Row | Column | Old | New | Kind | First difference |", "| --- | --- | --- | --- | --- | --- |"]
            o += [f"| {s['row']} | {s['column']} | `{md_cell(s['old'])}` | `{md_cell(s['new'])}` | {s['kind']} | {md_cell(s['where'])} |" for s in r["samples"]]
            o.append("")
        for label in ("missing", "extra"):
            if r[label]:
                o += [f"{label.title()} rows (first {a.max_samples}):", ""] + [f"- `{md_cell(x)}`" for x in r[label][: a.max_samples]] + [""]
        if r["duplicate_keys"]:
            o += ["Duplicate keys: " + ", ".join(map(str, r["duplicate_keys"])), ""]
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--format", default="auto", choices=["auto", "delimited", "fixed", "json", "jsonl", "text"])
    ap.add_argument("--delimiter")
    ap.add_argument("--quotechar")
    ap.add_argument("--widths")
    ap.add_argument("--columns")
    ap.add_argument("--columns-from-header", action="store_true")
    ap.add_argument("--header-lines", default="0", help="N or OLD,NEW")
    ap.add_argument("--trailer-lines", default="0", help="N or OLD,NEW")
    ap.add_argument("--key")
    ap.add_argument("--ignore-order", action="store_true")
    ap.add_argument("--ignore-cols")
    ap.add_argument("--expect-diff")
    ap.add_argument("--mask", action="append", default=[])
    ap.add_argument("--strip", action="store_true")
    ap.add_argument("--tolerance", type=float)
    ap.add_argument("--ignore-format", action="store_true")
    ap.add_argument("--rename")
    ap.add_argument("--encoding", default="utf-8")
    ap.add_argument("--max-samples", type=int, default=10)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    old, new = Path(a.old), Path(a.new)
    if not old.exists() or not new.exists():
        print("error: OLD or NEW does not exist", file=sys.stderr)
        return 2
    try:
        pairs, only_old, only_new = pair_files(old, new, a)
        results = [compare(Side(o, a, 0), Side(n, a, 1), a) for o, n in pairs]
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    unexpected = sum(r["unexpected"] for r in results) + len(only_old) + len(only_new)
    ok = unexpected == 0
    for r in results:
        cols = ", ".join(f"{c}={n}" for c, n in r["column_diffs"].most_common()) or "none"
        print(f"{'OK  ' if r['unexpected'] == 0 else 'DIFF'} {r['old']} vs {r['new']}: rows {r['rows_old']}/{r['rows_new']}, "
              f"unexpected={r['unexpected']} expected={r['expected']} missing={len(r['missing'])} extra={len(r['extra'])} "
              f"columns[{cols}]" + (f" format[{'; '.join(r['format'])}]" if r["format"] else ""))
    if only_old or only_new:
        print(f"DIFF unpaired files: only_old={only_old} only_new={only_new}")
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_md(results, only_old, only_new, a, ok), encoding="utf-8")
    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
