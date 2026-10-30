# Examples

Inputs used by the tests and handy for trying the skills.

| Path | What | Try |
| --- | --- | --- |
| `legacy-invoice-batch/` | Boot 2.7 / Spring Batch 4 app: `invoiceExportJob` (JDBC cursor -> processor rules -> pipe-delimited file, conditional flow, skip/retry), REST + `@Scheduled` trigger, Control-M script | `/java-app-analyzer` |
| `jsr352-payroll/` | Java EE JSR-352 job XML with chunk, decision and batchlet | `/java-replicate modernize payrollJob to Spring Batch 5` |
| `plain-java-recon/` | `main()` program with JDBC commit-every-1000 loop and shell wrapper | `/java-app-analyzer` |
| `jira/FIN-482.json` | Jira Cloud issue (ADF) asking for a credit-note replica of `invoiceExportJob` | `jira_to_spec.py --json` |
| `jira/FIN-490.txt` | Pasted ticket text for a REST trigger | `jira_to_spec.py --text` |
| `parity/` | Anchor output and replica output with approved deltas (negative cents, trailer) | `compare_outputs.py` |

The sample apps are scanned, never built. They contain fake credentials on purpose, to test redaction.
