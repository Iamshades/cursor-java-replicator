"""Tests for the bundled skill scripts. Run: python3 -m unittest discover -s tests -v"""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".cursor" / "skills"
EXAMPLES = ROOT / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = load("java_inventory", "java-app-analyzer/scripts/java_inventory.py")
jira = load("jira_to_spec", "jira-requirement-mapper/scripts/jira_to_spec.py")
cmp = load("compare_outputs", "java-parity-verifier/scripts/compare_outputs.py")


def inventory(path):
    return inv.Inventory([path]).run()


class InventoryLegacyBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = inventory(EXAMPLES / "legacy-invoice-batch")

    def test_kinds(self):
        for k in ("spring-batch", "spring-boot", "spring-boot-web", "spring-boot-scheduler"):
            self.assertIn(k, self.d["kinds"])

    def test_build(self):
        b = self.d["build"][0]
        self.assertEqual(b["spring_boot"], "2.7.18")
        self.assertEqual(b["java"], "11")

    def test_job_graph(self):
        job = self.d["batch"]["jobs"][0]
        self.assertEqual(job["name"], "invoiceExportJob")
        self.assertEqual(job["api"], "factory (Batch <=4)")
        self.assertEqual(job["step_order"], ["exportInvoices", "notifyFailure", "archiveFile"])
        self.assertIn({"from": "exportInvoices", "on": "FAILED", "to": "notifyFailure"}, job["edges"])
        self.assertIn({"from": "exportInvoices", "on": "*", "to": "archiveFile"}, job["edges"])

    def test_chunk_step(self):
        st = next(s for s in self.d["batch"]["steps"] if s["name"] == "exportInvoices")
        self.assertEqual(st["chunk_size"], "500")
        self.assertEqual((st["reader"], st["processor"], st["writer"]), ("invoiceReader", "invoiceProcessor", "erpFileWriter"))
        self.assertEqual(st["skipLimit"], "25")
        self.assertEqual(st["retryLimit"], "3")

    def test_item_beans_and_sql(self):
        reader = next(b for b in self.d["batch"]["item_beans"] if b["bean"] == "invoiceReader")
        self.assertTrue(reader["step_scope"])
        self.assertIn("status = 'APPROVED'", reader["properties"]["sql"])

    def test_endpoints_with_prefix(self):
        paths = {(e["method"], e["path"]) for e in self.d["web"]["endpoints"]}
        self.assertIn(("POST", "/api/jobs/invoice-export/{businessDate}"), paths)
        self.assertIn(("GET", "/api/jobs/health"), paths)

    def test_secrets_redacted(self):
        dump = json.dumps(self.d)
        self.assertNotIn("SuperSecret123", dump)
        self.assertNotIn("devpass", dump)

    def test_script_entry(self):
        self.assertTrue(any("spring.batch.job.names" in s["command"] for s in self.d["entry_points"]["scripts"]))


class InventoryOtherKinds(unittest.TestCase):
    def test_jsr352(self):
        d = inventory(EXAMPLES / "jsr352-payroll")
        self.assertIn("jakarta-batch", d["kinds"])
        job = d["batch"]["xml_jobs"][0]
        self.assertEqual(job["name"], "payrollJob")
        first = job["steps"][0]
        self.assertEqual((first["chunk_size"], first["reader"]), ("200", "timesheetReader"))
        self.assertIn({"from": "calcDecision", "on": "BONUS", "to": "applyBonus"}, job["edges"])

    def test_plain_java(self):
        d = inventory(EXAMPLES / "plain-java-recon")
        self.assertIn("plain-java", d["kinds"])
        self.assertEqual(d["entry_points"]["main_classes"][0]["class"], "com.acme.recon.ReconMain")
        self.assertTrue(d["entry_points"]["scripts"])

    def test_batch5_and_spring_xml(self):
        d = inventory(FIXTURES / "batch5-app")
        self.assertEqual(d["build"][0]["spring_boot"], "3.3.4")
        self.assertEqual(d["build"][0]["java"], "17")
        job = next(j for j in d["batch"]["jobs"] if j["name"] == "settlementJob")
        self.assertEqual(job["api"], "builder (Batch >=5)")
        self.assertEqual(job["step_order"], ["load", "settle", "report"])
        load_step = next(s for s in d["batch"]["steps"] if s["name"] == "load")
        self.assertEqual(load_step["chunk_size"], "100")
        xml = next(j for j in d["batch"]["xml_jobs"] if j["name"] == "legacyXmlJob")
        self.assertEqual(xml["flavor"], "spring-batch-xml")
        self.assertIn({"from": "transform", "on": "FAILED", "to": "cleanup"}, xml["edges"])
        self.assertEqual(xml["steps"][0]["chunk_size"], "50")
        self.assertTrue(any(m["kind"] == "KafkaListener" for m in d["messaging"]))

    def test_comment_stripping_keeps_strings(self):
        src = 'String u = "http://x//y"; // tail\n/* a\n b */ int z;'
        out = inv.strip_comments(src)
        self.assertIn('"http://x//y"', out)
        self.assertNotIn("tail", out)
        self.assertEqual(out.count("\n"), src.count("\n"))

    def test_cli_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, str(SKILLS / "java-app-analyzer/scripts/java_inventory.py"),
                                str(EXAMPLES / "legacy-invoice-batch"), "--out", tmp], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            md = (Path(tmp) / "inventory.md").read_text()
            self.assertIn("JOB-invoiceExportJob", md)
            self.assertIn("```mermaid", md)


class JiraToSpec(unittest.TestCase):
    def test_adf_issue(self):
        raw = json.loads((EXAMPLES / "jira" / "FIN-482.json").read_text())
        d = jira.normalize_issue(raw)
        self.assertEqual(d["key"], "FIN-482")
        self.assertEqual(len(d["requirements"]), 5)
        self.assertEqual([r["priority"] for r in d["requirements"]], ["MUST", "MUST", "MUST", "SHOULD", "COULD"])
        self.assertIn("creditNoteExportJob", d["hints"]["jobs"])
        self.assertIn("erp.export.dir", d["hints"]["properties"])
        self.assertIn("| invoiceId | number |", d["description_md"])
        self.assertEqual(d["comments"][0]["body"], "Time zone is Europe/Berlin for the schedule.")

    def test_text_ticket(self):
        d = jira.normalize_text((EXAMPLES / "jira" / "FIN-490.txt").read_text(), None)
        self.assertEqual(d["key"], "FIN-490")
        self.assertEqual(d["summary"], "Expose credit note export trigger over REST")
        self.assertGreaterEqual(len(d["requirements"]), 3)
        self.assertIn("/api/jobs/credit-note-export/{businessDate}", d["hints"]["endpoints"])
        self.assertEqual(len(d["scenarios"]), 1)

    def test_wiki_markup(self):
        md = jira.wiki_to_md("h2. Acceptance Criteria\n* first\n* second\n{code:java}int x;{code}")
        self.assertIn("## Acceptance Criteria", md)
        self.assertIn("- first", md)
        self.assertIn("```java", md)

    def test_pipe_escaped_in_table(self):
        raw = json.loads((EXAMPLES / "jira" / "FIN-482.json").read_text())
        self.assertIn("T\\|<record count>", jira.to_markdown(jira.normalize_issue(raw)))


class CompareOutputs(unittest.TestCase):
    OLD = str(EXAMPLES / "parity" / "INV_2026-10-29.txt")
    NEW = str(EXAMPLES / "parity" / "CN_2026-10-29.txt")
    BASE = ["--delimiter", "|", "--header-lines", "1", "--columns",
            "invoiceId,customerCode,amountCents,currency,issuedOn"]

    def run_cmp(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmp.main(list(args))
        return code, buf.getvalue()

    def test_identical(self):
        code, out = self.run_cmp(self.OLD, self.OLD, *self.BASE)
        self.assertEqual(code, 0, out)

    def test_expected_deltas_pass(self):
        code, out = self.run_cmp(self.OLD, self.NEW, *self.BASE, "--trailer-lines", "0,1", "--key", "invoiceId",
                                 "--expect-diff", "amountCents,trailer")
        self.assertEqual(code, 0, out)

    def test_unexpected_delta_fails(self):
        code, out = self.run_cmp(self.OLD, self.NEW, *self.BASE, "--trailer-lines", "0,1", "--key", "invoiceId",
                                 "--expect-diff", "trailer")
        self.assertEqual(code, 1, out)
        self.assertIn("amountCents=3", out)

    def test_positional_order_change_fails(self):
        code, _ = self.run_cmp(self.OLD, self.NEW, *self.BASE, "--trailer-lines", "0,1",
                               "--expect-diff", "amountCents,trailer")
        self.assertEqual(code, 1)

    def test_tolerance_mask_and_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a.csv"), Path(tmp, "b.csv")
            a.write_text("1,10.000,2026-10-29T01:00:00\n")
            b.write_bytes(b"1,10.001,2026-10-30T02:00:00\r\n")
            args = [str(a), str(b), "--mask", r"\d{4}-\d\d-\d\dT[\d:]+", "--tolerance", "0.01"]
            self.assertEqual(self.run_cmp(*args)[0], 1)                      # CRLF differs
            self.assertEqual(self.run_cmp(*args, "--ignore-format")[0], 0)


if __name__ == "__main__":
    unittest.main()
