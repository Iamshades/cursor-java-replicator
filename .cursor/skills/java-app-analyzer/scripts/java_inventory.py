#!/usr/bin/env python3
"""java_inventory.py - read-only inventory of Java / Spring / batch codebases.

Usage:
    python3 java_inventory.py <root> [<root> ...] [--out .replication] [--stdout]

Writes <out>/inventory.json and <out>/inventory.md. Python 3.8+ stdlib only.
Reads files and runs `git rev-parse` / `git status`; never builds or runs the app.
Every item is a CANDIDATE (pattern match) until a human or agent reads the code.
Values of secret-looking configuration keys are redacted.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.0.0"

SKIP_DIRS = {
    ".git", "target", "build", "out", ".gradle", ".idea", ".vscode",
    "node_modules", ".replication", ".mvn", "dist", "__pycache__",
}
TEXT_EXT = {".java", ".kt", ".xml", ".yml", ".yaml", ".properties", ".sql",
            ".gradle", ".kts", ".sh", ".ksh", ".bat", ".cmd", ".jil", ".mf"}
MAX_FILE_BYTES = 2_000_000

SECRET_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[-_.]?key|credential|private[-_.]?key|"
    r"access[-_.]?key|client[-_.]?secret|passphrase|auth[-_.]?key)")
SECRET_IN_VALUE = re.compile(r"(?i)((?:password|pwd|secret|token)=)[^;&\s\"']+")
SQL_START = re.compile(r"^\s*(select|insert|update|delete|merge|call|with|truncate|upsert)\b", re.I)
JAVA_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "else",
                 "throw", "synchronized", "try", "do", "case", "assert", "super", "this"}

READER_TYPES = ("ItemReader", "ItemStreamReader", "FlatFileItemReader", "JdbcCursorItemReader",
                "JdbcPagingItemReader", "JpaPagingItemReader", "JpaCursorItemReader",
                "RepositoryItemReader", "StaxEventItemReader", "JsonItemReader",
                "MultiResourceItemReader", "KafkaItemReader", "HibernateCursorItemReader",
                "StoredProcedureItemReader", "MongoItemReader", "MongoCursorItemReader",
                "SynchronizedItemStreamReader", "AmqpItemReader", "JmsItemReader")
WRITER_TYPES = ("ItemWriter", "ItemStreamWriter", "FlatFileItemWriter", "JdbcBatchItemWriter",
                "JpaItemWriter", "RepositoryItemWriter", "StaxEventItemWriter", "JsonFileItemWriter",
                "CompositeItemWriter", "ClassifierCompositeItemWriter", "KafkaItemWriter",
                "MongoItemWriter", "HibernateItemWriter", "AmqpItemWriter", "JmsItemWriter",
                "MultiResourceItemWriter")
PROCESSOR_TYPES = ("ItemProcessor", "CompositeItemProcessor", "ClassifierCompositeItemProcessor",
                   "ValidatingItemProcessor", "BeanValidatingItemProcessor",
                   "FunctionItemProcessor", "ScriptItemProcessor")
ARTIFACT_IFACES = {
    "ItemReader": "reader", "ItemStreamReader": "reader", "AbstractItemCountingItemStreamItemReader": "reader",
    "ItemProcessor": "processor", "ItemWriter": "writer", "ItemStreamWriter": "writer",
    "Tasklet": "tasklet", "Partitioner": "partitioner", "JobExecutionDecider": "decider",
    "JobExecutionListener": "listener", "StepExecutionListener": "listener", "ChunkListener": "listener",
    "ItemReadListener": "listener", "ItemProcessListener": "listener", "ItemWriteListener": "listener",
    "SkipListener": "listener", "SkipPolicy": "skip-policy", "RetryListener": "listener",
    "JobExecutionListenerSupport": "listener", "StepExecutionListenerSupport": "listener",
    "LineMapper": "line-mapper", "FieldSetMapper": "field-set-mapper", "LineAggregator": "line-aggregator",
    "FlatFileHeaderCallback": "header-callback", "FlatFileFooterCallback": "footer-callback",
    "RowMapper": "row-mapper", "ItemPreparedStatementSetter": "statement-setter",
    # JSR-352
    "AbstractItemReader": "reader", "AbstractItemWriter": "writer", "Batchlet": "batchlet",
    "AbstractBatchlet": "batchlet", "PartitionMapper": "partitioner", "Decider": "decider",
    # Quartz
    "Job": "quartz-job", "QuartzJobBean": "quartz-job",
}

# --------------------------------------------------------------------------- text helpers


def strip_comments(src: str) -> str:
    """Blank out // and /* */ comments, keep strings, text blocks and line numbers."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        if src.startswith('"""', i):
            j = src.find('"""', i + 3)
            i = n if j < 0 else j + 3
        elif src[i] == '"' or src[i] == "'":
            q = src[i]
            i += 1
            while i < n and src[i] != q and src[i] != "\n":
                i += 2 if src[i] == "\\" else 1
            i += 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            end = n if j < 0 else j + 2
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        else:
            i += 1
    return "".join(out)


def balanced(text: str, open_idx: int, open_ch: str = "(", close_ch: str = ")"):
    """Return (inner_text, close_idx) for the bracket at open_idx; skips strings."""
    depth, i, n = 0, open_idx, len(text)
    while i < n:
        if text.startswith('"""', i):
            j = text.find('"""', i + 3)
            i = n if j < 0 else j + 3
            continue
        c = text[i]
        if c == '"' or c == "'":
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == "\\" else 1
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
        i += 1
    return text[open_idx + 1:], n - 1


STR_LIT = re.compile(r'"""(.*?)"""|"((?:[^"\\\n]|\\.)*)"', re.S)


def literals(expr: str) -> list:
    res = []
    for m in STR_LIT.finditer(expr or ""):
        if m.group(1) is not None:
            lines = m.group(1).strip("\n").splitlines()
            indent = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
            res.append("\n".join(x[indent:] for x in lines))
        else:
            res.append(bytes(m.group(2), "utf-8").decode("unicode_escape", errors="ignore"))
    return res


def joined_literal(expr: str) -> str:
    return "".join(literals(expr))


def short(s: str, n: int = 160) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def line_at(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def redact(key: str, value: str) -> str:
    if value is None:
        return value
    if SECRET_KEY.search(key or ""):
        return "<redacted>" if value not in ("", "null") else value
    return SECRET_IN_VALUE.sub(r"\1<redacted>", value)


def simple_name(expr: str) -> str:
    """'loadStep()' / 'this.loadStep(null)' / 'loadStep' -> 'loadStep'."""
    expr = expr.strip()
    m = re.match(r"(?:this\.)?(\w+)\s*(\(.*\))?$", expr, re.S)
    return m.group(1) if m else short(expr, 60)


CHAIN_CALL = re.compile(r"\s*\.\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>\s*)?(\w+)\s*\(")


def parse_chain(text: str, start: int, base_line: int = 0):
    calls, i = [], start
    while True:
        m = CHAIN_CALL.match(text, i)
        if not m:
            break
        args, end = balanced(text, m.end() - 1)
        calls.append({"call": m.group(1), "args": args.strip(),
                      "line": base_line + line_at(text, m.start(1)) - 1 if base_line else None})
        i = end + 1
    return calls

# --------------------------------------------------------------------------- java model


METHOD_SIG = re.compile(
    r"(?m)^[ \t]*((?:@[\w.]+(?:\s*\([^;{}]*?\))?\s*)*)"
    r"((?:(?:public|protected|private|static|final|synchronized|default|abstract)\s+)*)"
    r"(?:<[^>]+>\s+)?([\w<>\[\],.?]+(?:\s*<[^;{}()]*>)?)\s+(\w+)\s*\(")
CLASS_DECL = re.compile(
    r"\b(class|interface|record|enum)\s+(\w+)(\s*<[^{]*?>)?([^{;]*)\{")
ANNOTATION = re.compile(r"@([\w.]+)\s*(\()?")


def annotations_in(region: str):
    res, i = [], 0
    while True:
        m = ANNOTATION.search(region, i)
        if not m:
            break
        args = ""
        i = m.end()
        if m.group(2):
            args, close = balanced(region, m.end() - 1)
            i = close + 1
        res.append((m.group(1).split(".")[-1], args, m.start()))
    return res


def preceding_region(text: str, idx: int) -> tuple:
    """Text between the previous statement/block boundary and idx (holds annotations)."""
    j = idx - 1
    depth = 0
    while j >= 0:
        c = text[j]
        if c == ")":
            depth += 1
        elif c == "(":
            depth -= 1
        elif depth == 0 and c in ";{}":
            break
        j -= 1
    return text[j + 1:idx], j + 1


class JavaFile:
    def __init__(self, rel: str, raw: str):
        self.rel = rel
        self.raw = raw
        self.src = strip_comments(raw)
        m = re.search(r"^\s*package\s+([\w.]+)\s*;", self.src, re.M)
        self.package = m.group(1) if m else ""
        self.imports = re.findall(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", self.src, re.M)
        self.classes = self._classes()
        self.methods = self._methods()

    def ln(self, idx: int) -> int:
        return line_at(self.src, idx)

    def _classes(self):
        res = []
        for m in CLASS_DECL.finditer(self.src):
            before = self.src[max(0, m.start() - 1):m.start()]
            if before and (before.isalnum() or before == "."):
                continue
            region, _ = preceding_region(self.src, m.start())
            anns = annotations_in(region)
            _, close = balanced(self.src, m.end() - 1, "{", "}")
            heritage = m.group(4) or ""
            res.append({
                "kind": m.group(1), "name": m.group(2), "line": self.ln(m.start()),
                "annotations": {a: args for a, args, _ in anns},
                "extends": re.findall(r"extends\s+([\w.<>, ?]+?)(?:\s+implements|$)", heritage.strip()),
                "implements": re.findall(r"implements\s+(.+)$", heritage.strip()),
                "heritage": short(heritage, 300),
                "start": m.start(), "end": close,
            })
        return res

    def _methods(self):
        res = []
        for m in METHOD_SIG.finditer(self.src):
            rtype, name = m.group(3), m.group(4)
            if name in JAVA_KEYWORDS or rtype in JAVA_KEYWORDS or rtype in ("return", "new", "else", "throw"):
                continue
            popen = m.end() - 1
            params, pclose = balanced(self.src, popen)
            tail = re.match(r"\s*(?:throws\s+[\w.,\s]+)?\{", self.src[pclose + 1:])
            if not tail:
                continue
            bopen = pclose + 1 + tail.end() - 1
            body, bclose = balanced(self.src, bopen, "{", "}")
            region = m.group(1) or ""
            pre, _ = preceding_region(self.src, m.start(2) if m.group(2) else m.start(3))
            anns = annotations_in(pre + region)
            res.append({
                "name": name, "returns": re.sub(r"\s+", "", rtype), "params": short(params, 200),
                "line": self.ln(m.start(4)), "annotations": {a: args for a, args, _ in anns},
                "body": body, "body_start": bopen + 1, "end": bclose,
            })
        return res

    def class_at(self, idx: int):
        best = None
        for c in self.classes:
            if c["start"] <= idx <= c["end"] and (best is None or c["start"] > best["start"]):
                best = c
        return best

    def fqcn(self, cls) -> str:
        return f"{self.package}.{cls['name']}" if self.package else cls["name"]

# --------------------------------------------------------------------------- scanners


class Inventory:
    def __init__(self, roots):
        self.roots = [Path(r).resolve() for r in roots]
        self.data = {
            "tool": {"name": "java_inventory", "version": VERSION},
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "status_note": "All items are CANDIDATE until confirmed by reading the cited file:line.",
            "roots": [], "build": [], "kinds": [],
            "batch": {"jobs": [], "steps": [], "item_beans": [], "artifacts": [],
                      "xml_jobs": [], "launchers": [], "launch_properties": []},
            "web": {"endpoints": [], "controllers": []},
            "messaging": [], "scheduling": [],
            "persistence": {"entities": [], "repositories": [], "sql": [], "migrations": [], "sql_files": []},
            "integrations": [],
            "config": {"files": [], "keys": [], "value_injections": [], "properties_classes": []},
            "entry_points": {"spring_boot_apps": [], "main_classes": [], "scripts": [], "cli_runners": []},
            "tests": {"files": 0, "test_methods": 0, "batch_tests": [], "boot_tests": 0, "testcontainers": False},
            "summary": {},
        }
        self.jsr352_imports = False
        self.kafka_or_mq_dep = False

    # ---- walk
    def files(self, root: Path):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for f in filenames:
                p = Path(dirpath) / f
                if p.suffix.lower() in TEXT_EXT or f in ("pom.xml", "MANIFEST.MF", "Dockerfile", "crontab"):
                    try:
                        if p.stat().st_size <= MAX_FILE_BYTES:
                            yield p
                    except OSError:
                        continue

    def run(self):
        for root in self.roots:
            self.data["roots"].append({"path": str(root), **git_info(root)})
            for p in self.files(root):
                rel = str(p.relative_to(root.parent if len(self.roots) > 1 else root))
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.dispatch(p, rel, raw)
        self.link_jobs()
        self.classify()
        self.summarize()
        return self.data

    def dispatch(self, p: Path, rel: str, raw: str):
        name, suf = p.name, p.suffix.lower()
        is_test = "/src/test/" in "/" + rel.replace(os.sep, "/")
        if name == "pom.xml":
            self.scan_pom(rel, raw)
        elif name.endswith((".gradle", ".gradle.kts")) and "settings" not in name:
            self.scan_gradle(rel, raw)
        elif suf in (".java", ".kt"):
            if is_test:
                self.scan_test(rel, raw)
            else:
                self.scan_java(rel, raw)
        elif suf == ".xml":
            self.scan_xml(rel, raw)
        elif suf in (".yml", ".yaml", ".properties") and not is_test:
            self.scan_config(rel, raw, suf)
        elif suf == ".sql":
            self.scan_sql_file(rel)
        elif suf in (".sh", ".ksh", ".bat", ".cmd", ".jil") or name in ("crontab", "Dockerfile"):
            self.scan_script(rel, raw)

    # ---- build files
    def scan_pom(self, rel, raw):
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return
        def strip(t):
            return t.split("}", 1)[-1]
        def child(el, tag):
            for c in el:
                if strip(c.tag) == tag:
                    return c
            return None
        def text(el, tag):
            c = child(el, tag) if el is not None else None
            return (c.text or "").strip() if c is not None and c.text else None
        props = {}
        pe = child(root, "properties")
        if pe is not None:
            for c in pe:
                props[strip(c.tag)] = (c.text or "").strip()
        parent = child(root, "parent")
        deps = []
        for section in ("dependencies",):
            de = child(root, section)
            if de is None:
                continue
            for d in de:
                g, a, v = text(d, "groupId"), text(d, "artifactId"), text(d, "version")
                deps.append(":".join(x for x in (g, a, v) if x))
        modules = []
        me = child(root, "modules")
        if me is not None:
            modules = [(m.text or "").strip() for m in me]
        parent_coord = None
        if parent is not None:
            parent_coord = f"{text(parent, 'groupId')}:{text(parent, 'artifactId')}:{text(parent, 'version')}"
        boot = None
        if parent_coord and "spring-boot" in parent_coord:
            boot = text(parent, "version")
        boot = boot or props.get("spring-boot.version") or props.get("spring.boot.version")
        java = (props.get("java.version") or props.get("maven.compiler.release")
                or props.get("maven.compiler.source") or props.get("maven.compiler.target"))
        packaging = text(root, "packaging") or "jar"
        self.data["build"].append({
            "file": rel, "tool": "maven",
            "coordinates": f"{text(root, 'groupId') or (text(parent, 'groupId') if parent is not None else '')}:"
                           f"{text(root, 'artifactId')}:{text(root, 'version') or ''}",
            "packaging": packaging, "parent": parent_coord, "spring_boot": boot, "java": java,
            "spring_batch": props.get("spring-batch.version"), "modules": modules,
            "dependencies": deps, "boot_plugin": "spring-boot-maven-plugin" in raw,
        })

    def scan_gradle(self, rel, raw):
        boot = re.search(r"org\.springframework\.boot['\"]?\)?\s*version\s*['\"]([^'\"]+)", raw)
        java = (re.search(r"JavaLanguageVersion\.of\(\s*(\d+)", raw)
                or re.search(r"sourceCompatibility\s*=\s*['\"]?(?:JavaVersion\.VERSION_)?([\d_.]+)", raw))
        deps = re.findall(r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(?\s*['\"]([^'\"]+)['\"]", raw)
        self.data["build"].append({
            "file": rel, "tool": "gradle", "spring_boot": boot.group(1) if boot else None,
            "java": java.group(1).replace("_", ".") if java else None, "dependencies": deps,
            "boot_plugin": "org.springframework.boot" in raw, "modules": [],
        })

    # ---- java
    def scan_java(self, rel, raw):
        jf = JavaFile(rel, raw)
        s = jf.src
        if any(i.startswith(("javax.batch", "jakarta.batch")) for i in jf.imports):
            self.jsr352_imports = True
        for c in jf.classes:
            self.scan_class(jf, c)
        self.scan_batch_builders(jf)
        self.scan_methods(jf)
        self.scan_sql_literals(jf)
        for m in re.finditer(r"\b(\w*[Jj]ob(?:Launcher|Operator))\s*\.\s*(run|start|startNextInstance|restart)\s*\(", s):
            args, _ = balanced(s, m.end() - 1)
            self.data["batch"]["launchers"].append({
                "file": rel, "line": jf.ln(m.start()), "call": f"{m.group(1)}.{m.group(2)}",
                "args": short(args, 120), "status": "CANDIDATE"})
        for m in re.finditer(r"@Value\(\s*\"\$\{([^}:]+)(?::([^}]*))?\}", s):
            key, default = m.group(1), m.group(2)
            self.data["config"]["value_injections"].append({
                "file": rel, "line": jf.ln(m.start()), "key": key,
                "default": redact(key, default) if default is not None else None})
        for m in re.finditer(r"#\{\s*(jobParameters|stepExecutionContext|jobExecutionContext)\s*\[\s*'([^']+)'\s*\]", s):
            self.data["config"]["value_injections"].append({
                "file": rel, "line": jf.ln(m.start()), "key": f"{m.group(1)}[{m.group(2)}]", "default": None})
        for m in re.finditer(r"\b(RestTemplate|RestClient|WebClient|WebServiceTemplate)\b[^;]*?\.\s*"
                             r"(getForObject|getForEntity|postForObject|postForEntity|exchange|put|delete|"
                             r"uri|get|post|marshalSendAndReceive)\s*\(", s):
            args, _ = balanced(s, m.end() - 1)
            self.data["integrations"].append({
                "file": rel, "line": jf.ln(m.start()), "kind": m.group(1), "call": m.group(2),
                "target": short(joined_literal(args) or args, 120), "status": "CANDIDATE"})
        for m in re.finditer(r"\b(kafkaTemplate|rabbitTemplate|jmsTemplate|streamBridge)\s*\.\s*(send|convertAndSend|sendDefault)\s*\(", s, re.I):
            args, _ = balanced(s, m.end() - 1)
            self.data["messaging"].append({
                "file": rel, "line": jf.ln(m.start()), "direction": "out", "kind": m.group(1),
                "destination": short(args.split(",")[0], 100), "status": "CANDIDATE"})

    def scan_class(self, jf: JavaFile, c):
        rel, anns = jf.rel, c["annotations"]
        fq = jf.fqcn(c)
        if "SpringBootApplication" in anns:
            self.data["entry_points"]["spring_boot_apps"].append({
                "file": rel, "line": c["line"], "class": fq, "args": short(anns["SpringBootApplication"], 200),
                "enables": [a for a in anns if a.startswith("Enable")]})
        if "Entity" in anns or "Document" in anns:
            tbl = anns.get("Table") or anns.get("Document") or ""
            name = re.search(r"name\s*=\s*\"([^\"]+)\"", tbl) or re.search(r"\"([^\"]+)\"", tbl)
            self.data["persistence"]["entities"].append({
                "file": rel, "line": c["line"], "class": fq, "table": name.group(1) if name else None,
                "status": "CANDIDATE"})
        if c["kind"] == "interface":
            m = re.search(r"extends\s+(\w*Repository|\w*Mapper)\s*<\s*([\w.]+)", c["heritage"])
            if m:
                self.data["persistence"]["repositories"].append({
                    "file": rel, "line": c["line"], "interface": fq, "base": m.group(1),
                    "entity": m.group(2), "status": "CANDIDATE"})
        if "Mapper" in anns and c["kind"] == "interface":
            self.data["persistence"]["repositories"].append({
                "file": rel, "line": c["line"], "interface": fq, "base": "MyBatis @Mapper",
                "entity": None, "status": "CANDIDATE"})
        if "FeignClient" in anns:
            self.data["integrations"].append({
                "file": rel, "line": c["line"], "kind": "FeignClient", "call": c["name"],
                "target": short(anns["FeignClient"], 160), "status": "CANDIDATE"})
        if "ConfigurationProperties" in anns:
            lit = literals(anns["ConfigurationProperties"])
            self.data["config"]["properties_classes"].append({
                "file": rel, "line": c["line"], "class": fq, "prefix": lit[0] if lit else None})
        if "RestController" in anns or "Controller" in anns:
            self.data["web"]["controllers"].append({"file": rel, "line": c["line"], "class": fq})
        heritage = c["heritage"]
        for iface, role in ARTIFACT_IFACES.items():
            if re.search(r"\b" + iface + r"\b", heritage):
                if iface == "Job" and "org.quartz" not in " ".join(jf.imports) and "quartz" not in heritage.lower():
                    continue
                generics = re.search(r"\b" + iface + r"\s*<([^{]*?)>(?:\s*[,{]|\s*$|\s+implements)", heritage + " ")
                self.data["batch"]["artifacts"].append({
                    "file": rel, "line": c["line"], "class": fq, "role": role, "interface": iface,
                    "types": short(generics.group(1), 120) if generics else None,
                    "named": literals(anns.get("Named", "")) or None,
                    "component": any(a in anns for a in ("Component", "Named", "Service")),
                    "status": "CANDIDATE"})

    def scan_methods(self, jf: JavaFile):
        rel, s = jf.rel, jf.src
        for mth in jf.methods:
            anns = mth["annotations"]
            cls = jf.class_at(mth["body_start"])
            if mth["name"] == "main" and "String" in mth["params"] and "static" in s[max(0, mth["body_start"] - 400):mth["body_start"]]:
                self.data["entry_points"]["main_classes"].append({
                    "file": rel, "line": mth["line"], "class": jf.fqcn(cls) if cls else rel,
                    "spring": "SpringApplication.run" in mth["body"] or "SpringApplicationBuilder" in mth["body"]})
            if mth["name"] == "run" and cls and re.search(r"\b(CommandLineRunner|ApplicationRunner)\b", cls["heritage"]):
                self.data["entry_points"]["cli_runners"].append({"file": rel, "line": mth["line"], "class": jf.fqcn(cls)})
            # endpoints
            for a, args in anns.items():
                if a in ("GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping") and cls \
                        and ("RestController" in cls["annotations"] or "Controller" in cls["annotations"]):
                    prefix = mapping_paths(cls["annotations"].get("RequestMapping", "")) or [""]
                    verb = a.replace("Mapping", "").upper()
                    if a == "RequestMapping":
                        vm = re.findall(r"RequestMethod\.(\w+)", args)
                        verb = ",".join(vm) if vm else "ANY"
                    for pre in prefix:
                        for path in mapping_paths(args) or [""]:
                            self.data["web"]["endpoints"].append({
                                "file": rel, "line": mth["line"], "method": verb,
                                "path": ("/" + "/".join(x.strip("/") for x in (pre, path) if x.strip("/"))) or "/",
                                "handler": f"{cls['name']}.{mth['name']}", "params": mth["params"],
                                "returns": mth["returns"], "status": "CANDIDATE"})
                if a in ("KafkaListener", "RabbitListener", "JmsListener", "SqsListener", "StreamListener"):
                    self.data["messaging"].append({
                        "file": rel, "line": mth["line"], "direction": "in", "kind": a,
                        "destination": short(args, 160),
                        "handler": f"{cls['name'] if cls else '?'}.{mth['name']}", "status": "CANDIDATE"})
                if a in ("Scheduled", "Schedule", "SchedulerLock"):
                    self.data["scheduling"].append({
                        "file": rel, "line": mth["line"], "kind": a, "spec": short(args, 160),
                        "handler": f"{cls['name'] if cls else '?'}.{mth['name']}", "status": "CANDIDATE"})
                if a == "Query":
                    q = joined_literal(args)
                    if q:
                        self.data["persistence"]["sql"].append({
                            "file": rel, "line": mth["line"], "origin": "@Query",
                            "native": "nativeQuery" in args and "true" in args, "sql": short(q, 400),
                            "method": mth["name"]})
            if "Bean" in anns:
                self.scan_item_bean(jf, mth)

    def scan_item_bean(self, jf: JavaFile, mth):
        rtype, body = mth["returns"], mth["body"]
        role = None
        for typ, r in ((READER_TYPES, "reader"), (PROCESSOR_TYPES, "processor"), (WRITER_TYPES, "writer")):
            if any(t in rtype for t in typ) or any(f"new {t}Builder" in body or f"new {t}<" in body or f"new {t}(" in body
                                                   for t in typ if t not in ("ItemReader", "ItemWriter", "ItemProcessor")):
                role = r
                break
        if not role:
            if "Tasklet" in rtype:
                role = "tasklet"
            elif "Partitioner" in rtype:
                role = "partitioner"
            elif "Listener" in rtype:
                role = "listener"
            elif "JobExecutionDecider" in rtype:
                role = "decider"
        if not role:
            return
        impl = re.findall(r"new\s+(\w+?)(?:Builder)?\s*(?:<[^>]*>)?\s*\(", body)
        impl = [i for i in impl if i not in ("ArrayList", "HashMap", "Date", "BigDecimal", "String")]
        props = {}
        for m in re.finditer(r"\.\s*(\w+)\s*\(", body):
            name = m.group(1)
            if name in ("sql", "selectClause", "fromClause", "whereClause", "queryString", "resource", "resources",
                        "names", "columns", "delimiter", "linesToSkip", "pageSize", "fetchSize", "sortKeys",
                        "encoding", "append", "headerCallback", "footerCallback", "lineAggregator",
                        "fieldSetMapper", "targetType", "rowMapper", "beanMapped", "itemPreparedStatementSetter",
                        "methodName", "repository", "arguments", "saveState", "name", "strict", "delimited",
                        "fixedLength", "formatted", "format", "shouldDeleteIfEmpty", "shouldDeleteIfExists",
                        "dataSource", "entityManagerFactory", "rootTagName", "addFragmentRootElements",
                        "topic", "partitions", "lineSeparator", "quoteCharacter", "comments", "includedFields",
                        "maxItemCount", "currentItemCount", "transactional", "forceSync", "delegates", "classifier"):
                args, _ = balanced(body, m.end() - 1)
                lit = joined_literal(args)
                if name in ("sql", "selectClause", "fromClause", "whereClause", "queryString"):
                    val = short(lit or args, 400)
                else:
                    val = short(lit if lit and len(literals(args)) == 1 else args, 200)
                props.setdefault(name, val if val != "" else True)
        self.data["batch"]["item_beans"].append({
            "file": jf.rel, "line": mth["line"], "bean": mth["name"], "role": role, "returns": rtype,
            "implementation": impl[0] if impl else rtype, "step_scope": "StepScope" in mth["annotations"],
            "job_scope": "JobScope" in mth["annotations"], "properties": props, "status": "CANDIDATE"})

    def scan_batch_builders(self, jf: JavaFile):
        s, rel = jf.src, jf.rel
        job_fac = set(re.findall(r"JobBuilderFactory\s+(\w+)", s)) | {"jobBuilderFactory"}
        step_fac = set(re.findall(r"StepBuilderFactory\s+(\w+)", s)) | {"stepBuilderFactory"}
        starts = []
        for m in re.finditer(r"new\s+(JobBuilder|StepBuilder)\s*\(", s):
            args, close = balanced(s, m.end() - 1)
            starts.append((m.group(1), args, m.start(), close + 1))
        for fac, kind in ((job_fac, "JobBuilder"), (step_fac, "StepBuilder")):
            for v in fac:
                for m in re.finditer(r"\b" + re.escape(v) + r"\s*\.\s*get\s*\(", s):
                    args, close = balanced(s, m.end() - 1)
                    starts.append((kind, args, m.start(), close + 1))
        for kind, args, at, chain_from in starts:
            name_lit = literals(args)
            name = name_lit[0] if name_lit else short(args.split(",")[0], 60)
            calls = parse_chain(s, chain_from)
            for c in calls:
                c["line"] = jf.ln(s.find(c["call"] + "(", chain_from)) if c["line"] is None else c["line"]
            enclosing = None
            for mth in jf.methods:
                if mth["body_start"] <= at <= mth["end"] and (enclosing is None or mth["body_start"] > enclosing["body_start"]):
                    enclosing = mth
            base = {"file": rel, "line": jf.ln(at), "name": name, "status": "CANDIDATE",
                    "bean_method": enclosing["name"] if enclosing else None,
                    "api": "factory (Batch <=4)" if ".get" in s[at:chain_from] else "builder (Batch >=5)"}
            if kind == "JobBuilder":
                self.data["batch"]["jobs"].append({**base, "calls": [
                    {"call": c["call"], "args": short(c["args"], 160)} for c in calls]})
            else:
                self.data["batch"]["steps"].append({**base, **summarize_step(calls)})

    def scan_sql_literals(self, jf: JavaFile):
        for m in re.finditer(r'(?:"""(.*?)"""|"((?:[^"\\\n]|\\.)*)"(?:\s*\+\s*"(?:[^"\\\n]|\\.)*")*)', jf.src, re.S):
            text = joined_literal(m.group(0))
            if SQL_START.match(text) and len(text) > 15:
                ctx = jf.src[max(0, m.start() - 80):m.start()]
                if "@Query" in ctx[-20:]:
                    continue
                self.data["persistence"]["sql"].append({
                    "file": jf.rel, "line": jf.ln(m.start()), "origin": "literal", "sql": short(text, 400)})

    def scan_test(self, rel, raw):
        t = self.data["tests"]
        t["files"] += 1
        t["test_methods"] += len(re.findall(r"@(?:Test|ParameterizedTest|RepeatedTest)\b", raw))
        if re.search(r"@SpringBatchTest|JobLauncherTestUtils|JobOperatorTestUtils", raw):
            t["batch_tests"].append(rel)
        if "@SpringBootTest" in raw:
            t["boot_tests"] += 1
        if "testcontainers" in raw.lower():
            t["testcontainers"] = True

    # ---- xml
    def scan_xml(self, rel, raw):
        if "<job" not in raw and "batch:job" not in raw:
            return
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return
        ns_jsr = ("xmlns.jcp.org/xml/ns/javaee" in raw or "jakarta.ee/xml/ns/jakartaee" in raw
                  or "/META-INF/batch-jobs/" in "/" + rel.replace(os.sep, "/"))
        flavor = "jakarta-batch" if ns_jsr else "spring-batch-xml"
        def tag(el):
            return el.tag.split("}", 1)[-1]
        def find_line(attr_val):
            i = raw.find(f'id="{attr_val}"')
            return line_at(raw, i) if i >= 0 else None
        jobs = [root] if tag(root) == "job" else [e for e in root.iter() if tag(e) == "job"]
        for job in jobs:
            steps, edges = [], []
            def walk(container, parent_flow=None):
                for el in container:
                    t = tag(el)
                    if t == "step":
                        sid = el.get("id")
                        st = {"id": sid, "line": find_line(sid), "next": el.get("next"), "parent": el.get("parent")}
                        for sub in el.iter():
                            tt = tag(sub)
                            if tt == "chunk":
                                st["type"] = "chunk"
                                st["chunk_size"] = sub.get("commit-interval") or sub.get("item-count")
                                for k in ("reader", "processor", "writer", "skip-limit", "retry-limit",
                                          "checkpoint-policy", "processor-transactional"):
                                    if sub.get(k):
                                        st[k] = sub.get(k)
                            elif tt in ("reader", "processor", "writer") and sub.get("ref"):
                                st[tt] = sub.get("ref")
                            elif tt == "tasklet" and sub.get("ref"):
                                st["type"], st["tasklet"] = "tasklet", sub.get("ref")
                            elif tt == "batchlet":
                                st["type"], st["batchlet"] = "batchlet", sub.get("ref")
                            elif tt in ("partition", "partitioner"):
                                st["partitioned"] = True
                            elif tt in ("include", "exclude") and sub.get("class"):
                                st.setdefault("exception_classes", []).append(f"{tt}:{sub.get('class')}")
                            elif tt in ("next", "end", "fail", "stop") and sub.get("on") is not None:
                                edges.append({"from": sid, "on": sub.get("on"),
                                              "to": sub.get("to") or sub.get("restart") or tt.upper()})
                        if st.get("next"):
                            edges.append({"from": sid, "on": "COMPLETED", "to": st["next"]})
                        steps.append(st)
                    elif t in ("flow", "split", "decision"):
                        if t == "decision":
                            steps.append({"id": el.get("id"), "type": "decision", "decider": el.get("decider") or el.get("ref"),
                                          "line": find_line(el.get("id"))})
                            for sub in el:
                                if tag(sub) in ("next", "end", "fail", "stop"):
                                    edges.append({"from": el.get("id"), "on": sub.get("on"),
                                                  "to": sub.get("to") or tag(sub).upper()})
                        if el.get("next"):
                            edges.append({"from": el.get("id"), "on": "COMPLETED", "to": el.get("next")})
                        walk(el, el.get("id"))
            walk(job)
            self.data["batch"]["xml_jobs"].append({
                "file": rel, "line": find_line(job.get("id")), "name": job.get("id"), "flavor": flavor,
                "restartable": job.get("restartable"), "steps": steps, "edges": edges, "status": "CANDIDATE"})

    # ---- config
    def scan_config(self, rel, raw, suf):
        base = os.path.basename(rel)
        if not re.match(r"(application|bootstrap|batch|job|quartz|config)", base) and "/config/" not in rel:
            return
        prof = re.match(r"(?:application|bootstrap)-([\w.-]+)\.(?:ya?ml|properties)$", base)
        profile = prof.group(1) if prof else "default"
        pairs = flatten_yaml(raw) if suf in (".yml", ".yaml") else flatten_properties(raw)
        self.data["config"]["files"].append({"file": rel, "profile": profile, "keys": len(pairs)})
        for key, value, line in pairs:
            item = {"file": rel, "line": line, "profile": profile, "key": key, "value": redact(key, value)}
            self.data["config"]["keys"].append(item)
            if key.startswith("spring.batch."):
                self.data["batch"]["launch_properties"].append(item)

    def scan_sql_file(self, rel):
        r = rel.replace(os.sep, "/")
        if re.search(r"db/(migration|changelog)|flyway|liquibase", r):
            self.data["persistence"]["migrations"].append(r)
        else:
            self.data["persistence"]["sql_files"].append(r)

    def scan_script(self, rel, raw):
        for i, line in enumerate(raw.splitlines(), 1):
            if re.search(r"\bjava\b.*(-jar|-cp|-classpath|\s[\w.]+\.[A-Z]\w+)", line) or "spring.batch.job" in line \
                    or re.search(r"\b(insert_job|command:)\b", line):
                self.data["entry_points"]["scripts"].append({
                    "file": rel, "line": i, "command": short(SECRET_IN_VALUE.sub(r"\1<redacted>", line), 200)})

    # ---- post-processing
    def link_jobs(self):
        steps_by_method = {s["bean_method"]: s for s in self.data["batch"]["steps"] if s.get("bean_method")}
        steps_by_name = {s["name"]: s for s in self.data["batch"]["steps"]}
        def resolve(expr):
            n = simple_name(expr)
            if n in steps_by_method:
                return steps_by_method[n]["name"]
            if n in steps_by_name:
                return n
            return n
        for job in self.data["batch"]["jobs"]:
            edges, nodes, current, pending = [], [], None, None
            for c in job["calls"]:
                call, args = c["call"], c["args"]
                if call in ("start", "flow"):
                    current = resolve(args)
                    nodes.append(current)
                elif call == "next":
                    tgt = resolve(args)
                    if current is not None:
                        edges.append({"from": current, "on": pending or "COMPLETED", "to": tgt})
                    pending, current = None, tgt
                    nodes.append(tgt)
                elif call == "from":
                    current = resolve(args)
                elif call == "on":
                    pending = (literals(args) or [args])[0]
                elif call == "to":
                    tgt = resolve(args)
                    edges.append({"from": current, "on": pending or "*", "to": tgt})
                    pending, current = None, tgt
                    nodes.append(tgt)
                elif call in ("end", "fail", "stopAndRestart") and pending is not None:
                    edges.append({"from": current, "on": pending, "to": call.upper() if call != "stopAndRestart" else f"STOP->{resolve(args)}"})
                    pending = None
                elif call == "split":
                    job.setdefault("parallel", True)
                elif call == "add":
                    for part in split_args(args):
                        edges.append({"from": current, "on": "SPLIT", "to": resolve(part)})
                elif call == "incrementer":
                    job["incrementer"] = short(args, 80)
                elif call == "listener":
                    job.setdefault("listeners", []).append(short(args, 80))
                elif call == "preventRestart":
                    job["restartable"] = False
            job["step_order"] = list(dict.fromkeys(n for n in nodes if n))
            job["edges"] = edges

    def classify(self):
        d, kinds = self.data, set()
        deps = " ".join(" ".join(b.get("dependencies", [])) for b in d["build"])
        parents = " ".join(str(b.get("parent")) for b in d["build"])
        if d["entry_points"]["spring_boot_apps"] or "spring-boot" in deps + parents or any(b.get("boot_plugin") for b in d["build"]):
            kinds.add("spring-boot")
        if d["batch"]["jobs"] or d["batch"]["steps"] or "spring-batch" in deps or "starter-batch" in deps \
                or any(j["flavor"] == "spring-batch-xml" for j in d["batch"]["xml_jobs"]):
            kinds.add("spring-batch")
        if self.jsr352_imports or any(j["flavor"] == "jakarta-batch" for j in d["batch"]["xml_jobs"]) \
                or "jakarta.batch" in deps or "javax.batch" in deps or "jberet" in deps:
            kinds.add("jakarta-batch")
        if d["web"]["endpoints"] or "starter-web" in deps:
            kinds.add("spring-boot-web" if "spring-boot" in kinds else "web")
        if [m for m in d["messaging"] if m["direction"] == "in"]:
            kinds.add("spring-boot-messaging" if "spring-boot" in kinds else "messaging")
        if [s for s in d["scheduling"] if s["kind"] in ("Scheduled", "SchedulerLock")]:
            kinds.add("spring-boot-scheduler")
        if "quartz" in deps or [a for a in d["batch"]["artifacts"] if a["role"] == "quartz-job"]:
            kinds.add("quartz")
        plain_mains = [m for m in d["entry_points"]["main_classes"] if not m["spring"]]
        if plain_mains and "spring-boot" not in kinds:
            kinds.add("plain-java")
        elif plain_mains:
            kinds.add("plain-java-mains")
        d["kinds"] = sorted(kinds) or ["unknown"]

    def summarize(self):
        d = self.data
        b = d["batch"]
        d["summary"] = {
            "batch_jobs_java": len(b["jobs"]), "batch_steps_java": len(b["steps"]),
            "batch_jobs_xml": len(b["xml_jobs"]), "item_beans": len(b["item_beans"]),
            "batch_artifact_classes": len(b["artifacts"]), "endpoints": len(d["web"]["endpoints"]),
            "messaging": len(d["messaging"]), "scheduled": len(d["scheduling"]),
            "entities": len(d["persistence"]["entities"]), "repositories": len(d["persistence"]["repositories"]),
            "sql_statements": len(d["persistence"]["sql"]), "migrations": len(d["persistence"]["migrations"]),
            "integrations": len(d["integrations"]), "config_keys": len(d["config"]["keys"]),
            "main_classes": len(d["entry_points"]["main_classes"]), "test_files": d["tests"]["files"],
            "test_methods": d["tests"]["test_methods"],
        }


def mapping_paths(args: str) -> list:
    if not args:
        return []
    m = re.search(r"\b(?:value|path)\s*=\s*(\{[^}]*\}|\"[^\"]*\")", args)
    if m:
        return literals(m.group(1))
    if "=" in args.split('"')[0]:
        return []
    return literals(args.split(",")[0] if not args.strip().startswith("{") else args[: args.find("}") + 1])


def split_args(args: str) -> list:
    parts, depth, cur = [], 0, ""
    for ch in args:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


def summarize_step(calls) -> dict:
    st = {"type": "unknown"}
    for c in calls:
        n, a = c["call"], c["args"]
        if n == "chunk":
            st["type"] = "chunk"
            st["chunk_size"] = split_args(a)[0] if a else None
        elif n == "tasklet":
            st["type"] = "tasklet"
            st["tasklet"] = simple_name(split_args(a)[0]) if a else None
        elif n in ("reader", "processor", "writer"):
            st[n] = simple_name(a)
        elif n == "partitioner":
            st["type"] = "partitioned"
            st["partitioner"] = short(a, 120)
        elif n in ("step", "gridSize", "taskExecutor", "throttleLimit", "skipLimit", "retryLimit",
                   "skipPolicy", "retryPolicy", "backOffPolicy", "startLimit", "allowStartIfComplete",
                   "transactionManager", "flow", "job", "partitionHandler"):
            st[n] = short(a, 120)
        elif n in ("skip", "retry", "noSkip", "noRetry", "noRollback"):
            st.setdefault(n, []).append(short(a, 100))
        elif n == "faultTolerant":
            st["fault_tolerant"] = True
        elif n == "listener":
            st.setdefault("listeners", []).append(short(a, 100))
    return st


def flatten_yaml(raw: str):
    """Minimal YAML flattener for config files (maps, scalars, simple lists, --- documents)."""
    out, stack = [], []
    for i, line in enumerate(raw.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.strip() == "---":
            stack = []
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if body.startswith("- "):
            parent = ".".join(k for _, k in stack)
            val = body[2:].strip()
            if ":" in val and not val.startswith(("'", '"')):
                k, _, v = val.partition(":")
                out.append((f"{parent}[].{k.strip()}", clean_yaml_value(v), i))
            else:
                out.append((f"{parent}[]", clean_yaml_value(val), i))
            continue
        m = re.match(r"^([^:#][^:]*?)\s*:(\s+(.*))?$", body)
        if not m:
            continue
        key, val = m.group(1).strip().strip("'\""), (m.group(3) or "").strip()
        full = ".".join([k for _, k in stack] + [key])
        if val and not val.startswith(("|", ">")):
            out.append((full, clean_yaml_value(val), i))
        else:
            stack.append((indent, key))
    return out


def clean_yaml_value(v: str) -> str:
    v = re.sub(r"\s+#.*$", "", v.strip())
    return v.strip("'\"")


def flatten_properties(raw: str):
    out = []
    for i, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", "!")):
            continue
        m = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)$", s)
        if m:
            out.append((m.group(1), m.group(2), i))
    return out


def git_info(root: Path) -> dict:
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True,
                               text=True, timeout=20).stdout.strip()
        return {"git_commit": commit or None, "git_dirty": bool(dirty) if commit else None}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_dirty": None}

# --------------------------------------------------------------------------- markdown


def md_escape(s) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def table(rows, cols) -> str:
    if not rows:
        return "_none found_\n"
    out = ["| " + " | ".join(c for c, _ in cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join(md_escape(f(r)) for _, f in cols) + " |")
    return "\n".join(out) + "\n"


def mermaid_id(s: str) -> str:
    return re.sub(r"\W", "_", s or "x")


def job_mermaid(nodes, edges) -> str:
    lines = ["```mermaid", "flowchart TD"]
    seen = set()
    for n in nodes:
        if n and n not in seen:
            lines.append(f'  {mermaid_id(n)}["{n}"]')
            seen.add(n)
    for e in edges:
        lab = e.get("on") or ""
        lines.append(f'  {mermaid_id(e["from"])} -->|"{lab}"| {mermaid_id(e["to"])}')
    lines.append("```")
    return "\n".join(lines)


def to_markdown(d: dict) -> str:
    loc = lambda r: f"{r['file']}:{r.get('line') or ''}"
    o = [f"# Inventory (generated by java_inventory {VERSION})", "",
         f"Generated: {d['generated_at']}  ", "All rows are **CANDIDATE** until confirmed by reading `file:line`.", ""]
    o.append("## Roots\n")
    o.append(table(d["roots"], [("Path", lambda r: r["path"]), ("Commit", lambda r: r["git_commit"]),
                                ("Dirty", lambda r: r["git_dirty"])]))
    o.append(f"## Kinds\n\n`{', '.join(d['kinds'])}`\n")
    o.append("## Summary\n")
    o.append(table([d["summary"]], [(k, (lambda k: lambda r: r[k])(k)) for k in d["summary"]]))
    o.append("## Build\n")
    o.append(table(d["build"], [("File", lambda r: r["file"]), ("Tool", lambda r: r["tool"]),
                                ("Coordinates", lambda r: r.get("coordinates")), ("Boot", lambda r: r.get("spring_boot")),
                                ("Java", lambda r: r.get("java")), ("Modules", lambda r: ", ".join(r.get("modules") or [])),
                                ("Key deps", lambda r: ", ".join(x.split(":")[1] if ":" in x else x for x in r.get("dependencies", [])
                                                                 if re.search(r"batch|web|kafka|jms|amqp|jpa|jdbc|mybatis|quartz|feign|oracle|postgres|mysql|db2|mssql|h2", x))[:300])]))
    o.append("## Entry points\n")
    if not (d["entry_points"]["spring_boot_apps"] or d["entry_points"]["main_classes"]):
        o.append("_none found_\n")
    if d["entry_points"]["spring_boot_apps"]:
        o.append(table(d["entry_points"]["spring_boot_apps"], [("Boot app", lambda r: r["class"]), ("Enables", lambda r: ", ".join(r["enables"])), ("At", loc)]))
    if d["entry_points"]["main_classes"]:
        o.append(table(d["entry_points"]["main_classes"], [("Main class", lambda r: r["class"]), ("Spring", lambda r: r["spring"]), ("At", loc)]))
    if d["entry_points"]["cli_runners"]:
        o.append(table(d["entry_points"]["cli_runners"], [("Runner", lambda r: r["class"]), ("At", loc)]))
    if d["entry_points"]["scripts"]:
        o.append(table(d["entry_points"]["scripts"], [("Script command", lambda r: r["command"]), ("At", loc)]))
    b = d["batch"]
    o.append("## Batch jobs (Java config)\n")
    steps = {s["name"]: s for s in b["steps"]}
    for j in b["jobs"]:
        o.append(f"### JOB-{j['name']}  \n`{loc(j)}` - bean `{j.get('bean_method')}` - {j['api']}\n")
        if j.get("incrementer"):
            o.append(f"- incrementer: `{j['incrementer']}`")
        if j.get("listeners"):
            o.append(f"- listeners: `{', '.join(j['listeners'])}`")
        o.append(f"- step order (declared): {' -> '.join(j['step_order']) or '?'}\n")
        o.append(job_mermaid(j["step_order"], j["edges"]) + "\n")
        rows = [steps[n] for n in j["step_order"] if n in steps]
        o.append(table(rows, [("Step", lambda r: r["name"]), ("Type", lambda r: r.get("type")),
                              ("Chunk", lambda r: r.get("chunk_size")), ("Reader", lambda r: r.get("reader")),
                              ("Processor", lambda r: r.get("processor")), ("Writer", lambda r: r.get("writer")),
                              ("Tasklet", lambda r: r.get("tasklet")),
                              ("Fault tolerance", lambda r: "; ".join(f"{k}={v}" for k, v in r.items() if k in ("skip", "skipLimit", "retry", "retryLimit", "noRollback", "skipPolicy"))),
                              ("At", loc)]))
    orphan = [s for s in b["steps"] if not any(s["name"] in j["step_order"] for j in b["jobs"])]
    if orphan:
        o.append("### Steps not linked to a Java job (may be used in XML or by partition handlers)\n")
        o.append(table(orphan, [("Step", lambda r: r["name"]), ("Type", lambda r: r.get("type")), ("At", loc)]))
    o.append("## Batch jobs (XML: Spring Batch XML / JSR-352)\n")
    for j in b["xml_jobs"]:
        o.append(f"### JOB-{j['name']} ({j['flavor']})  \n`{loc(j)}`\n")
        o.append(job_mermaid([s["id"] for s in j["steps"]], j["edges"]) + "\n")
        o.append(table(j["steps"], [("Step", lambda r: r["id"]), ("Type", lambda r: r.get("type")),
                                    ("Chunk", lambda r: r.get("chunk_size")), ("Reader", lambda r: r.get("reader")),
                                    ("Processor", lambda r: r.get("processor")), ("Writer", lambda r: r.get("writer")),
                                    ("Tasklet/Batchlet", lambda r: r.get("tasklet") or r.get("batchlet") or r.get("decider")),
                                    ("Line", lambda r: r.get("line"))]))
    if not b["xml_jobs"]:
        o.append("_none found_\n")
    o.append("## Item beans (readers / processors / writers / tasklets)\n")
    o.append(table(b["item_beans"], [("Bean", lambda r: r["bean"]), ("Role", lambda r: r["role"]),
                                     ("Impl", lambda r: r["implementation"]), ("StepScope", lambda r: r["step_scope"]),
                                     ("Key properties", lambda r: "; ".join(f"{k}={v}" for k, v in r["properties"].items())[:400]),
                                     ("At", loc)]))
    o.append("## Batch artifact classes\n")
    o.append(table(b["artifacts"], [("Class", lambda r: r["class"]), ("Role", lambda r: r["role"]),
                                    ("Interface", lambda r: r["interface"]), ("Types", lambda r: r.get("types")), ("At", loc)]))
    o.append("## Job launch points and properties\n")
    o.append(table(b["launchers"], [("Call", lambda r: r["call"]), ("Args", lambda r: r["args"]), ("At", loc)]))
    o.append(table(b["launch_properties"], [("Key", lambda r: r["key"]), ("Value", lambda r: r["value"]),
                                            ("Profile", lambda r: r["profile"]), ("At", loc)]))
    o.append("## HTTP endpoints\n")
    o.append(table(d["web"]["endpoints"], [("Method", lambda r: r["method"]), ("Path", lambda r: r["path"]),
                                           ("Handler", lambda r: r["handler"]), ("Returns", lambda r: r["returns"]), ("At", loc)]))
    o.append("## Messaging\n")
    o.append(table(d["messaging"], [("Dir", lambda r: r["direction"]), ("Kind", lambda r: r["kind"]),
                                    ("Destination", lambda r: r["destination"]), ("Handler", lambda r: r.get("handler")), ("At", loc)]))
    o.append("## Scheduling\n")
    o.append(table(d["scheduling"], [("Kind", lambda r: r["kind"]), ("Spec", lambda r: r["spec"]),
                                     ("Handler", lambda r: r["handler"]), ("At", loc)]))
    p = d["persistence"]
    o.append("## Persistence\n")
    o.append(table(p["entities"], [("Entity", lambda r: r["class"]), ("Table", lambda r: r["table"]), ("At", loc)]))
    o.append(table(p["repositories"], [("Repository", lambda r: r["interface"]), ("Base", lambda r: r["base"]),
                                       ("Entity", lambda r: r["entity"]), ("At", loc)]))
    o.append("### SQL statements\n")
    o.append(table(p["sql"], [("Origin", lambda r: r["origin"]), ("SQL", lambda r: r["sql"]), ("At", loc)]))
    if p["migrations"] or p["sql_files"]:
        o.append("Migrations: " + (", ".join(f"`{x}`" for x in p["migrations"]) or "none") + "  ")
        o.append("Other SQL files: " + (", ".join(f"`{x}`" for x in p["sql_files"]) or "none") + "\n")
    o.append("## Outbound integrations\n")
    o.append(table(d["integrations"], [("Kind", lambda r: r["kind"]), ("Call", lambda r: r["call"]),
                                       ("Target", lambda r: r["target"]), ("At", loc)]))
    c = d["config"]
    o.append("## Configuration\n")
    o.append(table(c["files"], [("File", lambda r: r["file"]), ("Profile", lambda r: r["profile"]), ("Keys", lambda r: r["keys"])]))
    o.append("### Keys (secret values redacted)\n")
    o.append(table(c["keys"], [("Key", lambda r: r["key"]), ("Value", lambda r: r["value"]),
                               ("Profile", lambda r: r["profile"]), ("At", loc)]))
    o.append("### Injected values\n")
    o.append(table(c["value_injections"], [("Key", lambda r: r["key"]), ("Default", lambda r: r["default"]), ("At", loc)]))
    if c["properties_classes"]:
        o.append(table(c["properties_classes"], [("@ConfigurationProperties", lambda r: r["class"]),
                                                 ("Prefix", lambda r: r["prefix"]), ("At", loc)]))
    t = d["tests"]
    o.append("## Tests\n")
    o.append(f"- test files: {t['files']}, test methods: {t['test_methods']}, @SpringBootTest classes: {t['boot_tests']}, "
             f"Testcontainers: {t['testcontainers']}")
    o.append(f"- batch tests: {', '.join(f'`{x}`' for x in t['batch_tests']) or 'none'}\n")
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", help="source root(s) to scan")
    ap.add_argument("--out", default=".replication", help="output directory (default: .replication)")
    ap.add_argument("--stdout", action="store_true", help="print JSON to stdout instead of writing files")
    args = ap.parse_args(argv)
    for r in args.roots:
        if not Path(r).is_dir():
            print(f"error: not a directory: {r}", file=sys.stderr)
            return 2
    data = Inventory(args.roots).run()
    if args.stdout:
        json.dump(data, sys.stdout, indent=2)
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "inventory.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (out / "inventory.md").write_text(to_markdown(data), encoding="utf-8")
    s = data["summary"]
    print(f"kinds={','.join(data['kinds'])} jobs={s['batch_jobs_java']}+{s['batch_jobs_xml']}xml "
          f"steps={s['batch_steps_java']} endpoints={s['endpoints']} entities={s['entities']} "
          f"sql={s['sql_statements']} config_keys={s['config_keys']} -> {out}/inventory.(json|md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
