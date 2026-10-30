# Spring Batch analysis guide

## Identify the version first

The API differs sharply by version. Read it from the build file (`spring-batch-core` or the Boot parent) before interpreting config.

| Spring Batch | Spring Boot | Tell-tale code |
| --- | --- | --- |
| 3.x / 4.x | 1.x / 2.x | `JobBuilderFactory`, `StepBuilderFactory`, `@EnableBatchProcessing` required, `javax.*` |
| 5.x | 3.x | `new JobBuilder(name, jobRepository)`, `new StepBuilder(name, jobRepository)`, `.chunk(n, txManager)`, `jakarta.*`; `@EnableBatchProcessing` *disables* Boot auto-config |
| 6.x | 4.x | Core types moved to sub-packages (e.g. `...core.job`, `...core.step`), `JobOperator` replaces most `JobLauncher` use, `ChunkOrientedStep`, `@EnableJdbcJobRepository` / `@EnableMongoJobRepository`, resourceless infrastructure by default |

Check the official migration guide for the exact version before generating code that targets it.

## Where jobs are defined

- Java config: `@Bean Job ...` methods; `JobBuilder` / `jobBuilderFactory.get(...)`.
- XML: `<batch:job id=...>` / `<job id=...>` in `*.xml` under `resources` (often `jobs/`, `batch/`, `spring/`).
- Boot launch: `spring.batch.job.name` (Boot 3) or `spring.batch.job.names` (Boot 2), `spring.batch.job.enabled`.
- Programmatic: `jobLauncher.run(job, params)` / `jobOperator.start(...)` in controllers, schedulers, `CommandLineRunner`.

## Step graph

Read the flow exactly; order and conditions are behavior.

- Linear: `.start(a).next(b).next(c)`.
- Conditional: `.on("FAILED").to(x)`, `.on("*").to(y)`, `.from(a).on(...)`, `.end()`, `.fail()`, `.stopAndRestart(...)`.
- Deciders: `JobExecutionDecider` returning `FlowExecutionStatus` - read every branch.
- Parallel: `.split(taskExecutor).add(flow1, flow2)`.
- Partitioning: `.partitioner(name, partitioner)` + `gridSize`; read the `Partitioner` to see how data is sliced (ranges, files, keys) and what goes in each `ExecutionContext`.
- Remote chunking/partitioning: `@EnableBatchIntegration`, channels - note the broker dependency.

## Chunk step checklist

| Item | Look for |
| --- | --- |
| Chunk size | `.chunk(n...)`, `commit-interval` |
| Reader | `JdbcCursorItemReader`, `JdbcPagingItemReader` (+ `PagingQueryProvider`, sort keys), `JpaPagingItemReader`, `RepositoryItemReader`, `FlatFileItemReader` (+ `LineMapper`, `DelimitedLineTokenizer`/`FixedLengthTokenizer`, `linesToSkip`, `skippedLinesCallback`), `StaxEventItemReader`, `JsonItemReader`, `MultiResourceItemReader`, `KafkaItemReader`, custom `ItemReader` |
| Processor | `ItemProcessor` impls, `CompositeItemProcessor`, `ClassifierCompositeItemProcessor`, `ValidatingItemProcessor`, `BeanValidatingItemProcessor`. Returning `null` filters the item |
| Writer | `JdbcBatchItemWriter` (SQL + `ItemSqlParameterSourceProvider`/`beanMapped()`), `JpaItemWriter`, `RepositoryItemWriter`, `FlatFileItemWriter` (+ `LineAggregator`, header/footer callbacks, `append`, `shouldDeleteIfEmpty`), `StaxEventItemWriter`, `CompositeItemWriter`, `ClassifierCompositeItemWriter`, `KafkaItemWriter` |
| Fault tolerance | `.faultTolerant()`, `.skip(X.class)`, `.skipLimit(n)`, `.skipPolicy(...)`, `.retry(X.class)`, `.retryLimit(n)`, `.noRollback(...)`, `.backOffPolicy(...)` |
| Restart | `.allowStartIfComplete(...)`, `.startLimit(n)`, `.preventRestart()`, reader `saveState`, `ExecutionContext` keys written by listeners |
| Concurrency | `.taskExecutor(...)`, `throttleLimit`, thread-safety of reader (cursor readers are not thread-safe; `SynchronizedItemStreamReader`) |
| Listeners | `JobExecutionListener`, `StepExecutionListener`, `ChunkListener`, `ItemRead/Process/WriteListener`, `SkipListener`, `@BeforeStep`, `@AfterJob`, etc. Record what each does (counts, emails, audit rows, file moves) |
| Scope | `@StepScope` / `@JobScope` beans with `#{jobParameters[...]}`, `#{stepExecutionContext[...]}` |

## Tasklet steps

`.tasklet(t, txManager)` or `implements Tasklet`. Common jobs: file cleanup, archive/move, stored-procedure call, table truncate, FTP/SFTP transfer, sending a file. Record the exact command and `RepeatStatus` logic.

## Data and metadata

- Job repository: datasource used for `BATCH_*` tables, table prefix (`spring.batch.jdbc.table-prefix`), `initialize-schema`.
- Business datasources: may differ from the batch datasource; note which beans use which (`@Qualifier`).
- Determinism: paging readers need a unique sort key; cursor queries without `ORDER BY` give unstable output order - flag for parity.

## Output to record per job (flow file)

Step table with type, reader -> processor -> writer, chunk size, fault-tolerance settings; the full rule list; I/O formats with samples if fixtures exist; restart semantics; listeners' side effects; job parameters and how the job is triggered.
