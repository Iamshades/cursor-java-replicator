# Plain Java / Quartz / script-driven batch analysis guide

Covers apps without Spring Batch: `main()` programs run by cron or an enterprise scheduler, Quartz jobs, EJB timers, and shell-wrapped jars.

## Find how it runs

- `public static void main(String[] args)` classes; `Main-Class` in `MANIFEST.MF`, `maven-jar-plugin`/`maven-shade-plugin`/`maven-assembly-plugin` config, Gradle `application { mainClass }`.
- Wrapper scripts: `*.sh`, `*.ksh`, `*.bat`, `*.cmd`, `run*.sh`, Control-M/Autosys JIL, crontab files, Jenkins/Airflow definitions in repo. Record arguments, env vars, `-D` system properties, classpath, JVM options, exit-code handling.
- Quartz: `implements Job` / `QuartzJobBean`, `JobDetail` + `Trigger` (cron), `quartz.properties`, clustered `JobStore`.
- EJB: `@Schedule`, `@Timeout`, `TimerService`.

## Trace the program

1. Argument parsing (`args[i]`, Commons CLI, picocli, JCommander) - list every option and default.
2. Configuration loading (`Properties`, `ResourceBundle`, files under `conf/`) - keys and defaults; redact secrets.
3. Input: JDBC (`DriverManager`, `DataSource`, raw SQL strings), files (`BufferedReader`, `Files.lines`, Apache Commons CSV, OpenCSV, POI for Excel), MQ (`javax.jms`, IBM MQ), FTP/SFTP (JSch, Commons Net).
4. Processing loops - every rule as `RULE-###`. Watch commit frequency inside loops (`conn.commit()` every N rows) - that is the chunk size.
5. Output: SQL writes, files (naming pattern, timestamps, encoding, line endings), reports, emails.
6. Error handling: per-record catch-and-continue (= skip), retries, exit codes (`System.exit(n)`) that the scheduler interprets.
7. Restart: does it resume (marker files, status tables) or rerun from scratch? Is it idempotent?

## Mapping hints for modernize-replicate into Spring Batch

| Plain Java pattern | Spring Batch equivalent |
| --- | --- |
| loop + `commit()` every N | chunk step, `chunk(N)` |
| try/catch per row, log and continue | `.faultTolerant().skip(...)` + `SkipListener` |
| `System.exit(2)` on partial failure | custom `ExitStatus` + `ExitCodeMapper` |
| status table for restart | `JobRepository` restart + `ItemStream` state |
| several phases in sequence | several steps; tasklets for non-item phases |
| per-file loop | `MultiResourceItemReader` or partitioning by file |

Exit codes are part of the contract when an external scheduler reads them. Record them.
