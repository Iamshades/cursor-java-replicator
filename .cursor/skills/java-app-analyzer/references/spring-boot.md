# Spring Boot service analysis guide

## Identity

- Boot version (parent POM, `org.springframework.boot` plugin, BOM), Java release (`maven.compiler.release`, `java.toolchain`), `javax` vs `jakarta`.
- Main class: `@SpringBootApplication`; note `scanBasePackages`, `exclude=` auto-configs, `@EnableScheduling`, `@EnableAsync`, `@EnableCaching`, `@EnableFeignClients`, `@EnableKafka`, etc.
- Modules: Maven `<modules>` / Gradle `settings.gradle` `include`. Which module is deployable (has the Boot plugin repackage).

## Entry points (each becomes an `EP-` flow)

| Kind | Look for |
| --- | --- |
| REST | `@RestController`/`@Controller` + `@RequestMapping` family; class-level prefix + method path; `server.servlet.context-path`; `@RequestBody`/`@PathVariable`/`@RequestParam`; validation `@Valid` + constraint annotations; response type and status; `@ControllerAdvice` error mapping |
| Reactive | `RouterFunction` beans, `WebFlux` handlers |
| Messaging | `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener`, Spring Cloud Stream `Consumer<>`/`Function<>` beans + `spring.cloud.stream.bindings.*` |
| Scheduled | `@Scheduled(cron/fixedRate/fixedDelay)`, `SchedulingConfigurer`, ShedLock `@SchedulerLock` |
| Startup | `CommandLineRunner`, `ApplicationRunner`, `@EventListener(ApplicationReadyEvent)` |
| Internal events | `ApplicationEventPublisher.publishEvent` + `@EventListener`/`@TransactionalEventListener` |

## Trace each entry point

Controller -> service -> repository / client, recording:

- Business rules as `RULE-###` with `path:line`.
- Transactions: `@Transactional` placement, propagation, readOnly, rollbackFor; self-invocation that bypasses the proxy.
- Persistence: entity mappings (`@Table`, `@Column`, relationships, fetch type, `@Version`), repository derived queries, `@Query` (JPQL/native), `JdbcTemplate`/`JdbcClient` SQL, MyBatis mappers (XML + interfaces), Flyway/Liquibase migrations as the schema truth.
- Outbound calls: `RestTemplate`, `RestClient`, `WebClient`, `@FeignClient`, SOAP (`WebServiceTemplate`); base URL property, timeouts, retries (`@Retryable`, Resilience4j), auth headers.
- Messaging out: `KafkaTemplate.send`, `RabbitTemplate`, `JmsTemplate`, `StreamBridge`; topic/queue, key, payload type, headers.
- Caching: `@Cacheable` keys and eviction.
- Security: `SecurityFilterChain`, method security (`@PreAuthorize`), which roles reach each endpoint.
- Errors: exception -> HTTP status mapping, error body shape.

## Configuration

Collect keys from `application*.yml|properties`, `@ConfigurationProperties` classes, `@Value`. Record per-profile values (`application-<profile>.yml`, `spring.config.activate.on-profile`). Redact values of keys matching password/secret/token/key/credential. Note env-var overrides found in Dockerfiles, Helm charts, `manifest.yml`, or k8s manifests.

## Contract capture for replication

For each endpoint/listener, record request and response schema (DTO fields, types, nullability, JSON naming via `@JsonProperty`/naming strategy, date formats), status codes, headers, and idempotency. If an OpenAPI spec exists, compare it with code and note drift. These contracts must be byte-compatible in the replica unless the ticket changes them.
