# Version matrix and translation notes

Always generate code for the version the target actually uses. Read it from the build file; if this table and the official docs disagree, the docs win.

| Line | Java baseline | Namespace | Batch API style |
| --- | --- | --- | --- |
| Boot 2.x + Batch 4.x | 8 / 11 | `javax.*` | `JobBuilderFactory` / `StepBuilderFactory`; `@EnableBatchProcessing` required |
| Boot 3.x + Batch 5.x | 17 | `jakarta.*` | `new JobBuilder(name, jobRepository)`, `new StepBuilder(name, jobRepository)`, `.chunk(n, txManager)` |
| Boot 4.x + Batch 6.x | 17 | `jakarta.*` | Builders as in 5 plus relocated core packages, `JobOperator`-centric launching, `@EnableJdbcJobRepository` / `@EnableMongoJobRepository`; consult the 6.0 migration guide before writing code |

## Batch 4 -> 5 translation (most common modernize-replicate)

| Batch 4 / Boot 2 | Batch 5 / Boot 3 |
| --- | --- |
| `jobBuilderFactory.get("j")` | `new JobBuilder("j", jobRepository)` |
| `stepBuilderFactory.get("s").<I,O>chunk(n)` | `new StepBuilder("s", jobRepository).<I,O>chunk(n, transactionManager)` |
| `.tasklet(t)` | `.tasklet(t, transactionManager)` |
| `@EnableBatchProcessing` on a Boot app | remove it to keep Boot auto-config (keeping it switches Boot's batch auto-config off) |
| `spring.batch.job.names=a,b` | `spring.batch.job.name=a` (one job per run) |
| `spring.batch.initialize-schema` | `spring.batch.jdbc.initialize-schema` |
| `ItemWriter.write(List<? extends T>)` | `ItemWriter.write(Chunk<? extends T>)` |
| `JobParameters` limited to String/Long/Double/Date | any type with a converter; `addLocalDate`, etc. |
| `javax.persistence`, `javax.validation`, `javax.annotation` | `jakarta.*` |
| `JobExecutionListenerSupport`, `StepExecutionListenerSupport` | implement the interface directly (default methods) |
| `BATCH_*` metadata schema v4 | run the Spring Batch 5 migration SQL for the metadata tables before reusing a v4 repository |

## JSR-352 / XML -> Java config

See `../../java-app-analyzer/references/jakarta-batch.md` for the element mapping. Keep the same job and step names so ops dashboards and restart semantics stay recognizable, unless the spec renames them.

## Plain Java -> Spring Batch

See `../../java-app-analyzer/references/plain-java.md` mapping table. Preserve exit codes with an `ExitCodeGenerator` / `ExitCodeMapper` when an external scheduler reads them.
