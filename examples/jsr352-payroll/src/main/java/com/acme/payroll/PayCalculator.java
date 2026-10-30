package com.acme.payroll;

import javax.batch.api.chunk.ItemProcessor;
import javax.inject.Named;

@Named("payCalculator")
public class PayCalculator implements ItemProcessor {
    @Override
    public Object processItem(Object item) {
        Timesheet t = (Timesheet) item;
        double hours = t.hours > 40 ? 40 + (t.hours - 40) * 1.5 : t.hours;
        return new Payslip(t.employeeId, hours * t.rate);
    }
}
