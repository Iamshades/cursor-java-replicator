package com.acme.invoice.batch;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobAuditListener implements JobExecutionListener {
    @Override public void beforeJob(JobExecution e) { }
    @Override public void afterJob(JobExecution e) { }
}
