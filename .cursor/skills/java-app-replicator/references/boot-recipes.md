# Spring Boot recipes for replicas

Boot 3 syntax. Copy the anchor's style (constructor injection, records vs classes, response wrappers) over these defaults.

## REST trigger for a job

```java
@RestController
@RequestMapping("/api/jobs")
public class CreditNoteJobController {

    private final JobLauncher jobLauncher;
    private final Job creditNoteExportJob;

    public CreditNoteJobController(JobLauncher jobLauncher, @Qualifier("creditNoteExportJob") Job creditNoteExportJob) {
        this.jobLauncher = jobLauncher;
        this.creditNoteExportJob = creditNoteExportJob;
    }

    @PostMapping("/credit-note-export/{businessDate}")
    @PreAuthorize("hasRole('OPS_ADMIN')")          // requires @EnableMethodSecurity
    public String run(@PathVariable String businessDate) throws Exception {
        return jobLauncher.run(creditNoteExportJob, new JobParametersBuilder()
                .addString("businessDate", businessDate)
                .toJobParameters()).getStatus().name();
    }
}
```

Match the anchor: synchronous vs async launcher (`TaskExecutorJobLauncher` with a `TaskExecutor`), parameter names, identifying parameters (re-running with the same identifying parameters fails with `JobInstanceAlreadyCompleteException`), and the response body.

## Scheduled trigger

```java
@Scheduled(cron = "${credit-note.export.cron:0 0 3 * * *}", zone = "${credit-note.export.zone:Europe/Berlin}")
public void nightly() throws Exception { ... }
```

State the zone explicitly when the ticket gives one. In multi-instance deployments, keep the anchor's locking (ShedLock `@SchedulerLock`, Quartz clustering, or external scheduler); never add a second scheduler for a job an external scheduler already runs.

## Messaging listener replica

Copy: container factory, group id, concurrency, ack mode, error handler (`DefaultErrorHandler` + `DeadLetterPublishingRecoverer`, back-off), deserializer and trusted packages, idempotency check. New topic names come from config, not literals.

```java
@KafkaListener(topics = "${credit-note.events.topic}", groupId = "${credit-note.events.group}",
               containerFactory = "invoiceKafkaListenerContainerFactory")
public void onEvent(CreditNoteEvent event) { ... }
```

## Configuration

Keep keys parallel to the anchor (`invoice.export.*` -> `credit-note.export.*`) and add every profile file the anchor has. Typed config:

```java
@ConfigurationProperties(prefix = "credit-note.export")
public record CreditNoteExportProperties(String dir, String cron, String zone) { }
```

Register with `@EnableConfigurationProperties(CreditNoteExportProperties.class)` or `@ConfigurationPropertiesScan`.

## Persistence

- New tables: add a migration in the anchor's tool and folder (Flyway `V<n>__...sql` / Liquibase changeset), never edit applied migrations.
- Reuse entities and repositories when the replica reads the same table; add a derived query or `@Query` instead of a second entity for the same table.

## Error mapping

Reuse the existing `@ControllerAdvice`. New exceptions extend the anchor's base exception types so they map to the same error body.
