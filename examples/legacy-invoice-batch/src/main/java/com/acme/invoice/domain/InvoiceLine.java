package com.acme.invoice.domain;

public record InvoiceLine(Long invoiceId, String customerCode, long amountCents, String currency, String issuedOn) { }
