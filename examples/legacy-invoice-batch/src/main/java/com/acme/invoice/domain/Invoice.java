package com.acme.invoice.domain;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
@Table(name = "INVOICE")
public class Invoice {
    @Id private Long id;
    private Long customerId;
    private BigDecimal amount;
    private String currency;
    private String status;
    private LocalDate issuedOn;
    public Long getId() { return id; }
    public Long getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }
    public LocalDate getIssuedOn() { return issuedOn; }
}
