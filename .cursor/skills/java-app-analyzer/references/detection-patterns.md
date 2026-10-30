# Detection patterns (fallback when the scanner cannot run)

Use with `rg -n` (or Cursor search). Exclude `target/`, `build/`, `.git/`, `node_modules/`. Hits are `CANDIDATE` until read.

| Signal | Pattern | Files |
| --- | --- | --- |
| Boot app | `@SpringBootApplication` | `*.java`, `*.kt` |
| Spring Batch dep | `spring-boot-starter-batch\|spring-batch-core` | `pom.xml`, `*.gradle*` |
| Job bean (Java) | `new JobBuilder\(\|jobBuilderFactory\.get\(\|JobBuilderFactory` | `*.java` |
| Step bean (Java) | `new StepBuilder\(\|stepBuilderFactory\.get\(` | `*.java` |
| Step order | `\.start\(\|\.next\(\|\.on\("\|\.split\(\|\.partitioner\(` | `*.java` |
| Job (XML) | `<(batch:)?job\s+id=` | `*.xml` |
| JSR-352 job | any file | `META-INF/batch-jobs/*.xml` |
| Item artifacts | `implements\s+(ItemReader\|ItemProcessor\|ItemWriter\|Tasklet\|Partitioner\|JobExecutionDecider\|Batchlet)` | `*.java` |
| Chunk size | `\.chunk\(\|commit-interval=\|item-count=` | `*.java`, `*.xml` |
| Fault tolerance | `faultTolerant\(\|skipLimit\(\|retryLimit\(\|skip-limit=` | `*.java`, `*.xml` |
| REST | `@(Get\|Post\|Put\|Delete\|Patch\|Request)Mapping` | `*.java` |
| Messaging | `@(Kafka\|Rabbit\|Jms\|Sqs)Listener` | `*.java` |
| Scheduling | `@Scheduled\|implements\s+Job\b\|QuartzJobBean\|@Schedule\(` | `*.java` |
| Main | `public\s+static\s+void\s+main\s*\(` | `*.java` |
| Entities | `@Entity\|@Table\(` | `*.java` |
| Repositories | `extends\s+(Jpa\|Crud\|PagingAndSorting\|Mongo)Repository\|@Mapper` | `*.java` |
| SQL | `@Query\(\|jdbcTemplate\.\|JdbcClient\|\.sql\(` | `*.java` |
| Migrations | any | `db/migration/*.sql`, `db/changelog/**` |
| HTTP out | `RestTemplate\|RestClient\|WebClient\|@FeignClient\|WebServiceTemplate` | `*.java` |
| Config keys | `@Value\("\$\{\|@ConfigurationProperties` | `*.java` |
| Launch property | `spring\.batch\.job\.(name\|names\|enabled)` | `application*.yml`, `*.properties` |
| Tests | `@SpringBatchTest\|JobLauncherTestUtils\|@SpringBootTest\|@Test` | `src/test/**` |
