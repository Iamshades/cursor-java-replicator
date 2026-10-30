#!/usr/bin/env python3
"""jira_to_spec.py - normalize a Jira issue (or pasted ticket text) into a requirements file.

Usage:
    python3 jira_to_spec.py --key ABC-123 [--api 3|2] [--with-links]   # REST, read-only GET
    python3 jira_to_spec.py --json issue.json                          # REST/MCP output or export
    python3 jira_to_spec.py --text ticket.md | --text -                # pasted text
    options: --out .replication/requirements  --stdout

REST credentials come only from env vars: JIRA_BASE_URL plus JIRA_EMAIL + JIRA_API_TOKEN (Cloud)
or JIRA_PAT (Server/Data Center bearer token). Tokens are never printed or written.
Writes <out>/<KEY>.md and <out>/<KEY>.json. Python 3.8+ stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "1.0.0"
AC_HEADING = re.compile(r"^\s*(?:#+\s*|h\d\.\s*|\*\*)?\s*(acceptance\s+criteria|ac|definition\s+of\s+done|dod)\b[\s:*]*$", re.I)
ANY_HEADING = re.compile(r"^\s*(#+\s+\S|h\d\.\s+\S|\*\*[^*]+\*\*\s*:?\s*$|[A-Z][\w /&-]{2,40}:\s*$)")
GWT = re.compile(r"^\s*(?:[-*\d.)]+\s*)?(given|when|then|and|but)\b\s+(.*)$", re.I)
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\[[ xX]\])\s+(.*)$")

# --------------------------------------------------------------------------- fetch


def http_get(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if os.environ.get("JIRA_PAT"):
        req.add_header("Authorization", "Bearer " + os.environ["JIRA_PAT"])
    elif os.environ.get("JIRA_EMAIL") and os.environ.get("JIRA_API_TOKEN"):
        raw = f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
        req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    else:
        raise SystemExit("error: set JIRA_PAT, or JIRA_EMAIL and JIRA_API_TOKEN (see references/jira-sources.md)")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error: GET {url} -> HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"error: GET {url} -> {e.reason}")


def fetch_issue(key: str, api: str) -> dict:
    base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit("error: JIRA_BASE_URL is not set")
    k = urllib.parse.quote(key)
    issue = http_get(f"{base}/rest/api/{api}/issue/{k}?expand=names,renderedFields")
    try:
        issue["_comments"] = http_get(f"{base}/rest/api/{api}/issue/{k}/comment?maxResults=50").get("comments", [])
    except SystemExit:
        issue["_comments"] = []
    issue["_base_url"] = base
    return issue

# --------------------------------------------------------------------------- converters


def adf_to_md(node, depth: int = 0) -> str:
    """Atlassian Document Format -> Markdown (best effort, keeps structure that matters)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_md(n, depth) for n in node)
    t, content = node.get("type"), node.get("content", [])
    attrs = node.get("attrs", {}) or {}
    inner = lambda: "".join(adf_to_md(c, depth) for c in content)
    if t == "doc":
        return inner().strip() + "\n"
    if t == "text":
        txt = node.get("text", "")
        for m in node.get("marks", []) or []:
            if m.get("type") == "code":
                txt = f"`{txt}`"
            elif m.get("type") == "strong":
                txt = f"**{txt}**"
            elif m.get("type") == "link":
                txt = f"[{txt}]({m.get('attrs', {}).get('href', '')})"
        return txt
    if t == "paragraph":
        return inner() + "\n\n"
    if t == "heading":
        return "#" * int(attrs.get("level", 2)) + " " + inner().strip() + "\n\n"
    if t in ("bulletList", "orderedList", "taskList"):
        out = []
        for i, item in enumerate(content, 1):
            mark = f"{i}." if t == "orderedList" else ("- [x]" if item.get("attrs", {}).get("state") == "DONE" else "- [ ]") if t == "taskList" else "-"
            body = adf_to_md(item.get("content", []), depth + 1).strip()
            lines = body.splitlines() or [""]
            out.append("  " * depth + f"{mark} {lines[0]}")
            out.extend(("  " * (depth + 1)) + ln for ln in lines[1:] if ln.strip())
        return "\n".join(out) + "\n\n"
    if t in ("listItem", "taskItem"):
        return inner()
    if t == "codeBlock":
        return f"```{attrs.get('language', '')}\n{inner()}\n```\n\n"
    if t == "blockquote":
        return "".join("> " + ln + "\n" for ln in inner().strip().splitlines()) + "\n"
    if t == "panel":
        return f"> [{attrs.get('panelType', 'note')}] " + inner().strip().replace("\n", "\n> ") + "\n\n"
    if t == "rule":
        return "---\n\n"
    if t == "hardBreak":
        return "\n"
    if t == "mention":
        return "@" + str(attrs.get("text", "user")).lstrip("@")
    if t in ("inlineCard", "blockCard"):
        return f"<{attrs.get('url', '')}>"
    if t == "emoji":
        return attrs.get("text", "")
    if t in ("mediaSingle", "mediaGroup", "media"):
        return f"[attachment: {attrs.get('alt') or attrs.get('id') or 'media'}]\n"
    if t == "table":
        rows = [[adf_to_md(cell.get("content", [])).strip().replace("\n", " ") for cell in row.get("content", [])]
                for row in content]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(out) + "\n\n"
    if t == "status":
        return f"[{attrs.get('text', '')}]"
    if t == "date":
        return str(attrs.get("timestamp", ""))
    return inner()


def wiki_to_md(s: str) -> str:
    """Jira wiki markup -> Markdown (headings, lists, code, tables, bold)."""
    if not s:
        return ""
    s = re.sub(r"\{code(?::([\w+-]+))?[^}]*\}(.*?)\{code\}", lambda m: f"```{m.group(1) or ''}\n{m.group(2).strip()}\n```", s, flags=re.S)
    s = re.sub(r"\{noformat\}(.*?)\{noformat\}", lambda m: f"```\n{m.group(1).strip()}\n```", s, flags=re.S)
    out = []
    for line in s.splitlines():
        m = re.match(r"^h([1-6])\.\s*(.*)", line)
        if m:
            out.append("#" * int(m.group(1)) + " " + m.group(2))
            continue
        m = re.match(r"^([*#]+)\s+(.*)", line)
        if m:
            lvl = len(m.group(1)) - 1
            out.append("  " * lvl + ("1." if m.group(1)[-1] == "#" else "-") + " " + m.group(2))
            continue
        if line.startswith("||"):
            cells = [c.strip() for c in line.strip("|").split("||")]
            out.append("| " + " | ".join(cells) + " |")
            out.append("|" + " --- |" * len(cells))
            continue
        out.append(line)
    md = "\n".join(out)
    md = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"**\1**", md)
    md = re.sub(r"\{\{([^}]+)\}\}", r"`\1`", md)
    return md


def to_md(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict) and value.get("type") == "doc":
        return adf_to_md(value)
    if isinstance(value, str):
        return wiki_to_md(value)
    if isinstance(value, list):
        return "\n".join(f"- {v.get('value') or v.get('name') if isinstance(v, dict) else v}" for v in value)
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or value.get("displayName") or json.dumps(value))
    return str(value)

# --------------------------------------------------------------------------- extraction


def section_after_heading(md: str, heading_re) -> list:
    lines, out, inside = md.splitlines(), [], False
    for line in lines:
        if heading_re.match(line):
            inside = True
            continue
        if inside and ANY_HEADING.match(line) and not BULLET.match(line) and not GWT.match(line):
            break
        if inside:
            out.append(line)
    return out


def criteria_from_lines(lines) -> list:
    items, cur = [], None
    for line in lines:
        if not line.strip():
            continue
        b = BULLET.match(line)
        g = GWT.match(line)
        if b:
            if cur:
                items.append(cur)
            cur = b.group(1).strip()
        elif g and cur and g.group(1).lower() in ("and", "but", "when", "then"):
            cur += " " + line.strip()
        elif cur and line.startswith(("  ", "\t")):
            cur += " " + line.strip()
        else:
            if cur:
                items.append(cur)
            cur = line.strip()
    if cur:
        items.append(cur)
    return [re.sub(r"\s+", " ", i) for i in items if len(i) > 2]


def scenarios(md: str) -> list:
    out, cur = [], []
    for line in md.splitlines():
        m = GWT.match(line)
        if m and m.group(1).lower() == "given":
            if cur:
                out.append(cur)
            cur = [line.strip(" -*")]
        elif m and cur:
            cur.append(line.strip(" -*"))
        elif cur and line.strip().lower().startswith("scenario"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [" / ".join(s) for s in out if any(x.lower().startswith("then") for x in s) or len(s) > 1]


def priority_of(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(could|nice to have|optional|if possible|later)\b", t):
        return "COULD"
    if re.search(r"\b(should|ideally|expected)\b", t) and not re.search(r"\b(must|shall|required)\b", t):
        return "SHOULD"
    return "MUST"


def kind_of(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(csv|delimit|column|field|format|header|trailer|footer|layout|xml|json|fixed[- ]width|padding|decimal|date format)\b", t):
        return "data-format"
    if re.search(r"\b(cron|schedul|daily|nightly|hourly|weekly|run at|alert|monitor|archive|retention|restart)\b", t):
        return "operational"
    if re.search(r"\b(api|endpoint|kafka|queue|topic|sftp|ftp|folder|bucket|s3|call|send to|erp|service)\b", t):
        return "integration"
    if re.search(r"\b(performance|within \d|sla|throughput|volume|seconds|minutes|secure|encrypt|pii|gdpr|audit)\b", t):
        return "non-functional"
    return "functional"


HINT_PATTERNS = {
    "classes": r"\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+(?:Job|Step|Reader|Writer|Processor|Tasklet|Service|Controller|Config|Listener|Repository|Client|Mapper)?)\b",
    "jobs": r"\b([a-z][A-Za-z0-9]*Job|[A-Z][A-Za-z0-9]*Job)\b",
    "endpoints": r"(?<![\w/])(/(?:api|v\d|rest|internal|public)[\w/{}.-]*)",
    "upper_identifiers": r"\b([A-Z][A-Z0-9]*_[A-Z0-9_]+|[A-Z]{4,})\b",
    "files": r"\b([\w.*{}-]+\.(?:csv|txt|dat|xml|json|xlsx?|zip|gz|ctl|psv|fixed))\b",
    "properties": r"\b([a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*){2,})\b",
    "cron": r"((?:[\d*/,?-]+\s+){4,6}[\d*/,?A-Z-]+)",
}
HINT_STOP = {"JSON", "HTTP", "HTTPS", "TODO", "NULL", "TRUE", "FALSE", "UTF8", "UUID", "JIRA", "NOTE", "WHEN",
             "THEN", "GIVEN", "MUST", "SHOULD", "COULD", "WITH", "FROM", "WHERE", "SELECT", "INTO", "DATE",
             "POST", "REST", "PATCH", "DELETE", "HEAD", "STARTED", "COMPLETED", "FAILED", "ALSO", "THIS", "THAT"}


def hints(text: str) -> dict:
    res = {}
    for k, pat in HINT_PATTERNS.items():
        vals = []
        for m in re.finditer(pat, text):
            v = m.group(1).strip()
            if v.upper() in HINT_STOP or (k == "properties" and re.match(r"^(www|e\.g|i\.e)\.", v)):
                continue
            if k == "classes" and len(v) < 6:
                continue
            vals.append(v)
        res[k] = sorted(set(vals))[:40]
    return {k: v for k, v in res.items() if v}

# --------------------------------------------------------------------------- normalize


def normalize_issue(issue: dict) -> dict:
    f = issue.get("fields", {}) or {}
    names = issue.get("names", {}) or {}
    key = issue.get("key") or "ISSUE"
    desc = to_md(f.get("description"))
    ac_fields = []
    for fid, val in f.items():
        label = names.get(fid, fid)
        if fid.startswith("customfield_") and val and re.search(r"acceptance|criteria|definition of done", str(label), re.I):
            ac_fields.append((label, to_md(val)))
    comments = []
    for c in issue.get("_comments") or (f.get("comment") or {}).get("comments", []) or []:
        comments.append({"author": (c.get("author") or {}).get("displayName", "?"),
                         "created": (c.get("created") or "")[:10], "body": to_md(c.get("body")).strip()})
    links = []
    for l in f.get("issuelinks", []) or []:
        other = l.get("outwardIssue") or l.get("inwardIssue") or {}
        rel = (l.get("type") or {}).get("outward" if l.get("outwardIssue") else "inward", "relates to")
        links.append({"relation": rel, "key": other.get("key"), "summary": (other.get("fields") or {}).get("summary")})
    parent = f.get("parent") or {}
    base = issue.get("_base_url")
    data = {
        "key": key, "url": f"{base}/browse/{key}" if base else None,
        "summary": f.get("summary") or "", "type": to_md(f.get("issuetype")), "status": to_md(f.get("status")),
        "priority": to_md(f.get("priority")), "labels": f.get("labels") or [],
        "components": [c.get("name") for c in f.get("components") or []],
        "fix_versions": [v.get("name") for v in f.get("fixVersions") or []],
        "parent": {"key": parent.get("key"), "summary": (parent.get("fields") or {}).get("summary")} if parent else None,
        "subtasks": [{"key": s.get("key"), "summary": (s.get("fields") or {}).get("summary")} for s in f.get("subtasks") or []],
        "links": links,
        "attachments": [{"filename": a.get("filename"), "size": a.get("size"), "mime": a.get("mimeType")}
                        for a in f.get("attachment") or []],
        "description_md": desc, "ac_fields": ac_fields, "comments": comments,
        "linked_issues": issue.get("_linked", []),
    }
    return finish(data)


def normalize_text(text: str, key: str) -> dict:
    title = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
    m = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", text)
    key = key or (m.group(1) if m else "TICKET")
    title = re.sub(r"^" + re.escape(key) + r"[\s:-]*", "", title)
    return finish({"key": key, "url": None, "summary": title, "type": "", "status": "", "priority": "",
                   "labels": [], "components": [], "fix_versions": [], "parent": None, "subtasks": [],
                   "links": [], "attachments": [], "description_md": text, "ac_fields": [], "comments": [],
                   "linked_issues": []})


def finish(d: dict) -> dict:
    criteria, origin = [], None
    for label, val in d["ac_fields"]:
        criteria += criteria_from_lines(val.splitlines())
        origin = f"field:{label}"
    if not criteria:
        criteria = criteria_from_lines(section_after_heading(d["description_md"], AC_HEADING))
        origin = "description:Acceptance Criteria" if criteria else None
    all_text = "\n".join([d["summary"], d["description_md"]] + [v for _, v in d["ac_fields"]] +
                         [c["body"] for c in d["comments"]])
    scen = scenarios(all_text)
    if not criteria and scen:
        criteria, origin = scen, "description:Given/When/Then"
    reqs = []
    for i, c in enumerate(criteria, 1):
        reqs.append({"id": f"REQ-{d['key']}-{i:02d}", "text": c, "type": kind_of(c), "priority": priority_of(c),
                     "source": origin})
    d["requirements"] = reqs
    d["scenarios"] = scen
    d["hints"] = hints(all_text)
    d["needs_review"] = [] if reqs else ["No acceptance criteria found: derive REQ- items from the description by hand."]
    d["tool"] = {"name": "jira_to_spec", "version": VERSION}
    return d


def to_markdown(d: dict) -> str:
    o = [f"# {d['key']}: {d['summary']}", ""]
    meta = [("URL", d.get("url")), ("Type", d["type"]), ("Status", d["status"]), ("Priority", d["priority"]),
            ("Labels", ", ".join(d["labels"])), ("Components", ", ".join(d["components"])),
            ("Fix versions", ", ".join(d["fix_versions"])),
            ("Parent", f"{d['parent']['key']} {d['parent']['summary'] or ''}" if d.get("parent") else "")]
    o += ["| Field | Value |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in meta if v] + [""]
    o += ["## Requirements (draft - review, split, and add implicit anchor behavior)", ""]
    if d["requirements"]:
        o += ["| ID | Requirement | Type | Priority | Source |", "| --- | --- | --- | --- | --- |"]
        for r in d["requirements"]:
            o.append(f"| {r['id']} | {r['text'].replace('|', chr(92) + '|')} | {r['type']} | {r['priority']} | {r['source']} |")
    for n in d["needs_review"]:
        o.append(f"> NEEDS REVIEW: {n}")
    o.append("")
    if d["scenarios"]:
        o += ["## Scenarios found", ""] + [f"- {s}" for s in d["scenarios"]] + [""]
    o += ["## Description", "", d["description_md"].strip() or "_empty_", ""]
    for label, val in d["ac_fields"]:
        o += [f"## {label}", "", val.strip(), ""]
    if d["subtasks"] or d["links"]:
        o += ["## Related issues", ""]
        o += [f"- subtask {s['key']}: {s['summary']}" for s in d["subtasks"]]
        o += [f"- {l['relation']} {l['key']}: {l['summary']}" for l in d["links"]]
        o.append("")
    for li in d.get("linked_issues", []):
        o += [f"### Linked {li['key']}: {li['summary']}", "", li["description_md"].strip()[:4000], ""]
    if d["attachments"]:
        o += ["## Attachments (not downloaded)", ""] + [f"- {a['filename']} ({a['mime']}, {a['size']} bytes)" for a in d["attachments"]] + [""]
    if d["comments"]:
        o += ["## Comments (oldest first; later ones may override)", ""]
        for c in d["comments"]:
            o += [f"**{c['author']}** {c['created']}:", "", c["body"], ""]
    if d["hints"]:
        o += ["## Hints (search terms for mapping; not requirements)", ""]
        o += [f"- **{k}**: " + ", ".join(f"`{v}`" for v in vals) for k, vals in d["hints"].items()] + [""]
    o += ["## Additional input", "", "_Add chat instructions, Confluence pages, emails and sample files here, labeled by source._", ""]
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--key", help="Jira issue key to fetch over REST (GET only)")
    src.add_argument("--json", help="issue JSON file (REST/MCP output or export)")
    src.add_argument("--text", help="ticket text file, or - for stdin")
    ap.add_argument("--api", default="3", choices=["2", "3"], help="REST API version (default 3; use 2 for Server/DC)")
    ap.add_argument("--with-links", action="store_true", help="also fetch linked issues and subtasks (one level)")
    ap.add_argument("--issue-key", help="key to use with --text when the text has none")
    ap.add_argument("--out", default=".replication/requirements")
    ap.add_argument("--stdout", action="store_true", help="print Markdown to stdout instead of writing files")
    a = ap.parse_args(argv)

    if a.key:
        issue = fetch_issue(a.key, a.api)
        if a.with_links:
            f = issue.get("fields", {})
            keys = [s.get("key") for s in f.get("subtasks") or []]
            keys += [(l.get("outwardIssue") or l.get("inwardIssue") or {}).get("key") for l in f.get("issuelinks") or []]
            issue["_linked"] = []
            for k in [k for k in keys if k][:15]:
                li = normalize_issue(fetch_issue(k, a.api))
                issue["_linked"].append({"key": k, "summary": li["summary"], "description_md": li["description_md"]})
        data = normalize_issue(issue)
    elif a.json:
        raw = json.loads(Path(a.json).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "issues" in raw and raw["issues"]:
            raw = raw["issues"][0]
        data = normalize_issue(raw)
    else:
        text = sys.stdin.read() if a.text == "-" else Path(a.text).read_text(encoding="utf-8")
        data = normalize_text(text, a.issue_key)

    md = to_markdown(data)
    if a.stdout:
        print(md)
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{data['key']}.md").write_text(md, encoding="utf-8")
    (out / f"{data['key']}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"{data['key']}: {len(data['requirements'])} requirements, {len(data['scenarios'])} scenarios, "
          f"hints={sum(len(v) for v in data['hints'].values())} -> {out}/{data['key']}.(md|json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
