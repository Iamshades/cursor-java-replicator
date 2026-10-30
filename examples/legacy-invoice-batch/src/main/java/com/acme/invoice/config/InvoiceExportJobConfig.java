package com.acme.invoice.config;

import com.acme.invoice.batch.InvoiceProcessor;
import com.acme.invoice.batch.ArchiveFileTasklet;
import com.acme.invoice.domain.Invoice;
import com.acme.invoice.domain.InvoiceLine;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.JobBuilderFactory;
import org.springframework.batch.core.configuration.annotation.StepBuilderFactory;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.launch.support.RunIdIncrementer;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.dao.DeadlockLoserDataAccessException;

import javax.sql.DataSource;

/**
 * Nightly export of approved invoices to the ERP flat file.
 * // not a comment inside javadoc: "quoted"
 */
@Configuration
public class InvoiceExportJobConfig {

    private final JobBuilderFactory jobs;
    private final StepBuilderFactory steps;

    public InvoiceExportJobConfig(JobBuilderFactory jobs, StepBuilderFactory steps) {
        this.jobs = jobs;
        this.steps = steps;
    }

    @Bean
    public Job invoiceExportJob(Step exportInvoicesStep, Step archiveStep, Step notifyFailureStep) {
        return jobs.get("invoiceExportJob")
                .incrementer(new RunIdIncrementer())
                .listener(new com.acme.invoice.batch.JobAuditListener())
                .start(exportInvoicesStep)
                .on("FAILED").to(notifyFailureStep)
                .from(exportInvoicesStep).on("*").to(archiveStep)
                .end()
                .build();
    }

    @Bean
    public Step exportInvoicesStep(JdbcCursorItemReader<Invoice> invoiceReader,
                                   InvoiceProcessor invoiceProcessor,
                                   FlatFileItemWriter<InvoiceLine> erpFileWriter) {
        return steps.get("exportInvoices")
                .<Invoice, InvoiceLine>chunk(500)
                .reader(invoiceReader)
                .processor(invoiceProcessor)
                .writer(erpFileWriter)
                .faultTolerant()
                .skip(IllegalArgumentException.class)
                .skipLimit(25)
                .retry(DeadlockLoserDataAccessException.class)
                .retryLimit(3)
                .build();
    }

    @Bean
    public Step archiveStep(ArchiveFileTasklet archiveFileTasklet) {
        return steps.get("archiveFile").tasklet(archiveFileTasklet).build();
    }

    @Bean
    public Step notifyFailureStep() {
        return steps.get("notifyFailure").tasklet((contribution, ctx) -> null).build();
    }

    @Bean
    @StepScope
    public JdbcCursorItemReader<Invoice> invoiceReader(DataSource dataSource,
                                                       @Value("#{jobParameters['businessDate']}") String businessDate) {
        return new JdbcCursorItemReaderBuilder<Invoice>()
                .name("invoiceReader")
                .dataSource(dataSource)
                .sql("SELECT i.id, i.customer_id, i.amount, i.currency, i.status, i.issued_on " +
                     "FROM invoice i WHERE i.status = 'APPROVED' AND i.issued_on = ?")
                .queryArguments(businessDate)
                .rowMapper(new com.acme.invoice.batch.InvoiceRowMapper())
                .fetchSize(1000)
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemWriter<InvoiceLine> erpFileWriter(@Value("${erp.export.dir}") String dir,
                                                         @Value("#{jobParameters['businessDate']}") String businessDate) {
        return new FlatFileItemWriterBuilder<InvoiceLine>()
                .name("erpFileWriter")
                .resource(new FileSystemResource(dir + "/INV_" + businessDate + ".txt"))
                .delimited().delimiter("|")
                .names("invoiceId", "customerCode", "amountCents", "currency", "issuedOn")
                .headerCallback(w -> w.write("H|INVOICES|" + businessDate))
                .shouldDeleteIfEmpty(true)
                .build();
    }
}
