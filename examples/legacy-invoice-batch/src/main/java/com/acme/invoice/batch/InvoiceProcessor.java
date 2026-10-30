package com.acme.invoice.batch;

import com.acme.invoice.domain.Invoice;
import com.acme.invoice.domain.InvoiceLine;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Component
public class InvoiceProcessor implements ItemProcessor<Invoice, InvoiceLine> {

    @Override
    public InvoiceLine process(Invoice in) {
        if (in.getAmount().signum() == 0) {
            return null; // zero invoices are not exported
        }
        if (in.getCurrency() == null) {
            throw new IllegalArgumentException("currency missing for invoice " + in.getId());
        }
        long cents = in.getAmount().setScale(2, RoundingMode.HALF_UP).movePointRight(2).longValueExact();
        String customer = "C" + String.format("%08d", in.getCustomerId());
        return new InvoiceLine(in.getId(), customer, cents, in.getCurrency(), in.getIssuedOn().toString());
    }
}
