package com.acme.settle;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class SettlementJobConfig {

    @Bean
    Job settlementJob(JobRepository jobRepository) {
        return new JobBuilder("settlementJob", jobRepository)
                .start(loadStep(jobRepository, null))
                .next(settleStep(jobRepository, null))
                .next(reportStep(jobRepository, null))
                .build();
    }

    @Bean
    Step loadStep(JobRepository jobRepository, PlatformTransactionManager tx) {
        return new StepBuilder("load", jobRepository)
                .<String, String>chunk(100, tx)
                .reader(() -> null)
                .writer(chunk -> { })
                .build();
    }

    @Bean
    Step settleStep(JobRepository jobRepository, PlatformTransactionManager tx) {
        return new StepBuilder("settle", jobRepository).tasklet((c, ctx) -> null, tx).build();
    }

    @Bean
    Step reportStep(JobRepository jobRepository, PlatformTransactionManager tx) {
        String url = "http://example.com/a//b"; // a comment with "quotes" and ( parens
        /* block ( comment */
        return new StepBuilder("report", jobRepository).tasklet((c, ctx) -> null, tx).build();
    }

    @KafkaListener(topics = "settlement-events", groupId = "settle")
    public void onEvent(String event) { }
}
