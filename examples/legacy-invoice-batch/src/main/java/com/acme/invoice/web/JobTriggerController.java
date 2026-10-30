package com.acme.invoice.web;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/jobs")
public class JobTriggerController {
    private final JobLauncher jobLauncher;
    private final Job invoiceExportJob;

    public JobTriggerController(JobLauncher jobLauncher, Job invoiceExportJob) {
        this.jobLauncher = jobLauncher;
        this.invoiceExportJob = invoiceExportJob;
    }

    @PostMapping("/invoice-export/{businessDate}")
    public String run(@PathVariable String businessDate) throws Exception {
        return jobLauncher.run(invoiceExportJob, new JobParametersBuilder()
                .addString("businessDate", businessDate).toJobParameters()).getStatus().name();
    }

    @GetMapping(value = "/health", produces = "text/plain")
    public String health() { return "OK"; }

    @Scheduled(cron = "${invoice.export.cron:0 0 2 * * *}")
    public void nightly() throws Exception {
        run(java.time.LocalDate.now().minusDays(1).toString());
    }
}
