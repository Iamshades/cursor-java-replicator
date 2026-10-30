# Jakarta Batch (JSR-352) analysis guide

Used in Java EE / Jakarta EE apps (WebSphere Liberty, WildFly/JBeret, Payara, TomEE) and sometimes alongside Spring Batch, which can run JSR-352 XML in 4.x (support removed in Spring Batch 5).

## Locate

- Job XML: `src/main/resources/META-INF/batch-jobs/<jobId>.xml` (or `WEB-INF/classes/META-INF/batch-jobs`).
- Artifacts: classes implementing `javax.batch.api.*` / `jakarta.batch.api.*` (`ItemReader`, `ItemProcessor`, `ItemWriter`, `Batchlet`, `AbstractItemReader`, `AbstractBatchlet`, `PartitionMapper`, `Decider`, listeners), usually `@Named` CDI beans. `ref="myReader"` resolves to the `@Named("myReader")` bean or default bean name (decapitalized class name), or `batch.xml` mappings in `META-INF/batch.xml`.
- Start: `BatchRuntime.getJobOperator().start("jobId", props)` in EJBs, servlets, REST resources, `@Schedule` timers.

## Job XML elements

| Element | Read |
| --- | --- |
| `<step id next=>` | order; `next` attribute or `<next on="..." to="..."/>` |
| `<chunk item-count= checkpoint-policy= time-limit= skip-limit= retry-limit=>` | commit interval and fault tolerance |
| `<reader ref>`, `<processor ref>`, `<writer ref>` + `<properties>` | artifact and its injected `@BatchProperty` values |
| `<skippable-exception-classes>`, `<retryable-exception-classes>`, `<no-rollback-exception-classes>` | include/exclude lists |
| `<batchlet ref>` | task-style step |
| `<partition>` with `<mapper>` or `<plan partitions= threads=>`, `<collector>`, `<analyzer>`, `<reducer>` | partitioning |
| `<decision ref>`, `<flow>`, `<split>` | branching and parallel |
| `<end on>`, `<fail on exit-status>`, `<stop on restart>` | transitions |
| `#{jobParameters['x']}`, `#{jobProperties['y']}`, `#{partitionPlan['z']}`, `?:default;` | substitution with defaults |

## Checkpoint semantics

`checkpointInfo()` on readers/writers defines restart position - record what is saved. Custom `CheckpointAlgorithm` changes commit behavior.

## Mapping to Spring Batch (for modernize-replicate)

| JSR-352 | Spring Batch 5 |
| --- | --- |
| `<chunk item-count="n">` | `.chunk(n, txManager)` |
| `ItemReader.readItem()` returning `null` at end | `ItemReader.read()` returning `null` at end |
| `open(Serializable checkpoint)` / `checkpointInfo()` | `ItemStream.open/update(ExecutionContext)` |
| `Batchlet.process()` returning exit status | `Tasklet.execute()` + `ExitStatus` via `StepContribution` |
| `PartitionMapper` | `Partitioner` |
| `Decider` | `JobExecutionDecider` |
| `@BatchProperty` / `jobParameters` | `@Value("#{jobParameters['x']}")` with `@StepScope` |
| `skip-limit` + exception classes | `.faultTolerant().skipLimit(n).skip(X.class)` |

Exit statuses and restart semantics differ in details; list the ones the source depends on and verify them in parity tests.
