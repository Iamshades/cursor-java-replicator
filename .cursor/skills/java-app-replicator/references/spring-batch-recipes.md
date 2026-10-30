# Spring Batch recipes

Examples use Spring Batch 5 / Boot 3 (the most common target). Batch 4 differences are noted inline; for Batch 6 check the migration guide (package moves, `JobOperator`). Names follow a credit-note replica of an invoice export; rename to the anchor's conventions.

## Contents

1. Job with conditional flow
2. Chunk step with fault tolerance
3. Readers (JDBC cursor, paging, flat file)
4. Writers (flat file with header and trailer, JDBC)
5. Processor that replicates rules
6. Tasklet step
7. Partitioned step
8. Tests (processor unit, step-scoped bean, job, golden file)

## 1. Job with conditional flow

```java
@Configuration
public class CreditNoteExportJobConfig {

    @Bean
    public Job creditNoteExportJob(JobRepository jobRepository, Step exportCreditNotesStep,
                                   Step archiveCreditNoteFileStep, Step notifyCreditNoteFailureStep) {
        return new JobBuilder("creditNoteExportJob", jobRepository)
                .incrementer(new RunIdIncrementer())
                .start(exportCreditNotesStep)
                    .on("FAILED").to(notifyCreditNoteFailureStep)
                .from(exportCreditNotesStep)
                    .on("*").to(archiveCreditNoteFileStep)
                .end()
                .build();
    }
}
```

Batch 4: `jobBuilderFactory.get("creditNoteExportJob")` instead of `new JobBuilder(...)`. Keep the same transition patterns (`"FAILED"`, `"*"`, custom exit codes) as the anchor; they are behavior.

## 2. Chunk step with fault tolerance

```java
@Bean
public Step exportCreditNotesStep(JobRepository jobRepository, PlatformTransactionManager transactionManager,
                                  JdbcCursorItemReader<CreditNote> creditNoteReader,
                                  CreditNoteProcessor creditNoteProcessor,
                                  FlatFileItemWriter<CreditNoteLine> creditNoteFileWriter) {
    return new StepBuilder("exportCreditNotes", jobRepository)
            .<CreditNote, CreditNoteLine>chunk(500, transactionManager)   // same chunk size as anchor
            .reader(creditNoteReader)
            .processor(creditNoteProcessor)
            .writer(creditNoteFileWriter)
            .faultTolerant()
            .skip(IllegalArgumentException.class).skipLimit(25)
            .retry(DeadlockLoserDataAccessException.class).retryLimit(3)
            .build();
}
```

Batch 4: `stepBuilderFactory.get("exportCreditNotes").<A, B>chunk(500)`. Use the transaction manager bound to the same datasource the anchor uses (check `@Qualifier`s).

## 3. Readers

JDBC cursor, step-scoped, with a late-bound job parameter:

```java
@Bean
@StepScope
public JdbcCursorItemReader<CreditNote> creditNoteReader(DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    return new JdbcCursorItemReaderBuilder<CreditNote>()
            .name("creditNoteReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT i.id, i.customer_id, i.amount, i.currency, i.status, i.issued_on
                 FROM invoice i
                 WHERE i.type = 'CREDIT_NOTE' AND i.status = 'APPROVED' AND i.issued_on = ?
                 ORDER BY i.id
                 """)
            .queryArguments(businessDate)
            .rowMapper(new DataClassRowMapper<>(CreditNote.class))
            .fetchSize(1000)
            .build();
}
```

Add `ORDER BY` only if the anchor has one, or record a `DEC-` (ordering changes output files). Text blocks need Java 15+; use concatenation on Java 8/11 targets.

Paging (multi-threaded steps need a thread-safe reader):

```java
return new JdbcPagingItemReaderBuilder<CreditNote>()
        .name("creditNoteReader").dataSource(dataSource).pageSize(500)
        .selectClause("SELECT id, customer_id, amount, currency, issued_on")
        .fromClause("FROM invoice")
        .whereClause("WHERE type = 'CREDIT_NOTE' AND status = 'APPROVED' AND issued_on = :d")
        .parameterValues(Map.of("d", businessDate))
        .sortKeys(Map.of("id", Order.ASCENDING))          // must be unique
        .rowMapper(new DataClassRowMapper<>(CreditNote.class))
        .build();
```

Flat file (delimited and fixed width):

```java
return new FlatFileItemReaderBuilder<Payment>()
        .name("paymentReader")
        .resource(new FileSystemResource(inputFile))
        .encoding("UTF-8")
        .linesToSkip(1)
        .delimited().delimiter("|").names("id", "amount", "currency")
        // .fixedLength().columns(new Range(1, 10), new Range(11, 22)).names("id", "amount")
        .targetType(Payment.class)
        .build();
```

## 4. Writers

Flat file with the anchor's header and a record-count trailer:

```java
@Bean
@StepScope
public FlatFileItemWriter<CreditNoteLine> creditNoteFileWriter(
        @Value("${erp.export.dir}") String dir,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{stepExecution}") StepExecution stepExecution) {
    return new FlatFileItemWriterBuilder<CreditNoteLine>()
            .name("creditNoteFileWriter")
            .resource(new FileSystemResource(dir + "/CN_" + businessDate + ".txt"))
            .encoding("UTF-8")
            .lineSeparator("\n")                                   // match the anchor's file exactly
            .delimited().delimiter("|")
            .names("invoiceId", "customerCode", "amountCents", "currency", "issuedOn")
            .headerCallback(w -> w.write("H|CREDIT_NOTES|" + businessDate))
            .footerCallback(w -> w.write("T|" + stepExecution.getWriteCount()))
            .shouldDeleteIfEmpty(true)
            .build();
}
```

Prove the trailer count with a test that includes skipped and filtered items.

JDBC upsert (keep the anchor's write semantics: insert-only, upsert, or delete+insert):

```java
return new JdbcBatchItemWriterBuilder<CreditNoteLine>()
        .dataSource(dataSource)
        .sql("INSERT INTO erp_credit_note (id, customer_code, amount_cents) VALUES (:invoiceId, :customerCode, :amountCents)")
        .beanMapped()
        .assertUpdates(true)
        .build();
```

`beanMapped()` reads getters; for Java records use `.itemSqlParameterSourceProvider(item -> new MapSqlParameterSource(...))` or record-style accessors supported by your Spring version.

Batch 5 custom writer signature: `void write(Chunk<? extends T> chunk)` (Batch 4: `List<? extends T>`).

## 5. Processor that replicates rules

```java
@Component
public class CreditNoteProcessor implements ItemProcessor<CreditNote, CreditNoteLine> {

    @Override
    public CreditNoteLine process(CreditNote in) {
        if (in.amount().signum() == 0) {                    // RULE-001 (InvoiceProcessor.java:15): filter zero
            return null;
        }
        if (in.currency() == null) {                        // RULE-002 (InvoiceProcessor.java:18): skip via exception
            throw new IllegalArgumentException("currency missing for credit note " + in.id());
        }
        long cents = in.amount().setScale(2, RoundingMode.HALF_UP)   // RULE-003: HALF_UP, scale 2
                .movePointRight(2).longValueExact();
        String customer = "C" + String.format("%08d", in.customerId()); // RULE-004: C + 8-digit zero pad
        return new CreditNoteLine(in.id(), customer, -Math.abs(cents),  // D-02 (FIN-482): negative cents
                in.currency(), in.issuedOn().toString());
    }
}
```

Keep rule order: a different order changes which exception/filter wins. Comment each rule with its ID only if the codebase already uses such comments; otherwise keep the mapping in the spec.

## 6. Tasklet step

```java
@Bean
public Step archiveCreditNoteFileStep(JobRepository jobRepository, PlatformTransactionManager tx,
                                      ArchiveFileTasklet archiveFileTasklet) {
    return new StepBuilder("archiveCreditNoteFile", jobRepository)
            .tasklet(archiveFileTasklet, tx)        // Batch 4: .tasklet(archiveFileTasklet)
            .build();
}
```

Reuse the anchor's tasklet if it is parameterized; otherwise parameterize it (with regression test) rather than copy it.

## 7. Partitioned step

```java
return new StepBuilder("exportCreditNotes.manager", jobRepository)
        .partitioner("exportCreditNotes", rangePartitioner)   // same slicing as anchor
        .step(exportCreditNotesStep)
        .gridSize(8)
        .taskExecutor(batchTaskExecutor)
        .build();
```

Partitioned output is usually one file per partition or unordered; parity comparison then needs `--ignore-order` or a merge step.

## 8. Tests

Processor rules (plain JUnit 5 + AssertJ, one test per rule and delta):

```java
class CreditNoteProcessorTest {
    private final CreditNoteProcessor processor = new CreditNoteProcessor();

    @Test
    void filtersZeroAmount() {                                     // RULE-001
        assertThat(processor.process(note("0.00", "EUR"))).isNull();
    }

    @Test
    void exportsNegativeCentsRoundedHalfUp() {                     // RULE-003 + D-02
        assertThat(processor.process(note("12.345", "EUR")).amountCents()).isEqualTo(-1235L);
    }
}
```

Step-scoped bean:

```java
StepExecution execution = MetaDataInstanceFactory.createStepExecution(
        new JobParametersBuilder().addString("businessDate", "2026-10-29").toJobParameters());
List<CreditNote> read = StepScopeTestUtils.doInStepScope(execution, () -> {
    reader.open(execution.getExecutionContext());
    List<CreditNote> items = new ArrayList<>();
    for (CreditNote n; (n = reader.read()) != null; ) items.add(n);
    reader.close();
    return items;
});
```

Whole job against a golden file:

```java
@SpringBatchTest
@SpringBootTest
@TestPropertySource(properties = "erp.export.dir=target/test-out")
class CreditNoteExportJobTest {

    @Autowired JobLauncherTestUtils jobLauncherTestUtils;
    @Autowired JobRepositoryTestUtils jobRepositoryTestUtils;
    @Autowired @Qualifier("creditNoteExportJob") Job creditNoteExportJob;

    @BeforeEach
    void setUp() {
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(creditNoteExportJob);   // needed when the context has several jobs
    }

    @Test
    void writesExpectedFile() throws Exception {
        JobExecution run = jobLauncherTestUtils.launchJob(new JobParametersBuilder()
                .addString("businessDate", "2026-10-29").toJobParameters());

        assertThat(run.getExitStatus().getExitCode()).isEqualTo("COMPLETED");
        assertThat(Path.of("target/test-out/CN_2026-10-29.txt"))
                .hasSameTextualContentAs(Path.of("src/test/resources/golden/CN_2026-10-29.txt"));
    }
}
```

Seed data with `@Sql` scripts or Testcontainers matching the production database family when SQL dialect matters (Oracle `DATE`, `ROWNUM`, `MERGE`).
